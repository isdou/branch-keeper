#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createInterface } from "node:readline";
import { mkdir, readFile } from "node:fs/promises";
import { execFile, spawn } from "node:child_process";
import { homedir, tmpdir } from "node:os";
import { basename, join } from "node:path";

const COMPANION_DIR = new URL(".", import.meta.url).pathname;
const INJECTION_FILE = join(COMPANION_DIR, "codex-inject.user.js");
const SERVER_FILE = join(COMPANION_DIR, "branch_keeper_server.py");
const PYTHON_LAUNCHER = join(COMPANION_DIR, "..", "scripts", "branch_keeper_launcher.mjs");
const PLUGIN_ROOT = join(COMPANION_DIR, "..");
const DEFAULT_PORT = 9232;
const INJECTOR_VERSION = "0.2.0";

function log(message) {
  console.error(`[branch-keeper] ${message}`);
}

function parseArgs(argv) {
  const options = { port: DEFAULT_PORT, serverPort: 0, watch: true, launch: false, open: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--port") options.port = Number(argv[++index]);
    else if (arg === "--server-port") options.serverPort = Number(argv[++index]);
    else if (arg === "--codex-path") options.codexPath = argv[++index];
    else if (arg === "--profile") options.profile = argv[++index];
    else if (arg === "--launch") options.launch = true;
    else if (arg === "--open") options.open = true;
    else if (arg === "--once") options.watch = false;
    else if (arg === "--watch") options.watch = true;
    else if (arg === "--help" || arg === "-h") options.help = true;
    else throw new Error(`unknown option: ${arg}`);
  }
  if (!Number.isInteger(options.port) || options.port < 1 || options.port > 65535) {
    throw new Error("--port must be between 1 and 65535");
  }
  if (!Number.isInteger(options.serverPort) || options.serverPort < 0 || options.serverPort > 65535) {
    throw new Error("--server-port must be between 0 and 65535");
  }
  return options;
}

function printHelp() {
  console.log(`Branch Keeper Codex Companion ${INJECTOR_VERSION}

Usage:
  node companion/codex-injector.mjs --port 9232 --watch
  node companion/codex-injector.mjs --launch --watch

Options:
  --port <n>          Existing Codex CDP port (default: ${DEFAULT_PORT})
  --server-port <n>   Local board port; 0 chooses a free port
  --launch            Launch a separate Codex window with CDP enabled
  --codex-path <p>    Codex executable or .app path when using --launch
  --profile <p>       Persistent profile directory for a launched Codex
  --open              Open the local board in the default browser too
  --once              Inject once and exit (useful for tests)
  --watch             Keep the server and injector alive (default)
`);
}

function randomToken() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function getText(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.text();
}

class CdpClient {
  constructor(webSocketUrl) {
    this.webSocketUrl = webSocketUrl;
    this.socket = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.webSocketUrl);
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("CDP connection timed out")), 8000);
      this.socket.addEventListener("open", () => {
        clearTimeout(timeout);
        resolve();
      }, { once: true });
      this.socket.addEventListener("error", (event) => {
        clearTimeout(timeout);
        reject(event.error || new Error("CDP connection failed"));
      }, { once: true });
    });
    this.socket.addEventListener("message", (event) => this.handleMessage(event.data));
    this.socket.addEventListener("close", () => {
      for (const pending of this.pending.values()) pending.reject(new Error("CDP connection closed"));
      this.pending.clear();
    });
  }

  handleMessage(raw) {
    try {
      const message = JSON.parse(typeof raw === "string" ? raw : Buffer.from(raw).toString("utf8"));
      if (!message.id || !this.pending.has(message.id)) return;
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message || "CDP request failed"));
      else pending.resolve(message.result || {});
    } catch {
      // Ignore non-JSON protocol noise.
    }
  }

  call(method, params = {}) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error("CDP socket is not open"));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP request timed out: ${method}`));
      }, 12000);
      this.pending.set(id, {
        resolve: (value) => { clearTimeout(timeout); resolve(value); },
        reject: (error) => { clearTimeout(timeout); reject(error); },
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.call("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
      userGesture: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text || "Runtime evaluation failed");
    }
    return result.result?.value;
  }

  close() {
    try { this.socket?.close(); } catch { /* best effort */ }
  }
}

async function listCodexTargets(port) {
  const targets = await getJson(`http://127.0.0.1:${port}/json/list`);
  return (Array.isArray(targets) ? targets : []).filter((target) => {
    if (target.type !== "page" || !target.webSocketDebuggerUrl) return false;
    const url = String(target.url || "");
    const title = String(target.title || "").toLowerCase();
    return url.startsWith("app://") || url.startsWith("codex://") || title.includes("codex");
  });
}

async function waitForTargets(port, timeoutMs = 30000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      const targets = await listCodexTargets(port);
      if (targets.length) return targets;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`没有找到 Codex CDP 页面（端口 ${port}）${lastError ? `：${lastError.message}` : ""}`);
}

function resolveCodexExecutable(input) {
  const candidates = input ? [input] : [
    "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT",
    "/Applications/Codex.app/Contents/MacOS/Codex",
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (!candidate.endsWith(".app")) return candidate;
    const executableDir = join(candidate, "Contents", "MacOS");
    const executableName = basename(candidate, ".app");
    return join(executableDir, executableName);
  }
  throw new Error("找不到 Codex。请使用 --codex-path 指定 Codex.app 或可执行文件。");
}

async function launchCodex(options) {
  const executable = resolveCodexExecutable(options.codexPath);
  const profile = options.profile || join(homedir(), ".branch-keeper", "codex-profile");
  await mkdir(profile, { recursive: true });
  const args = [
    `--user-data-dir=${profile}`,
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${options.port}`,
    `--remote-allow-origins=http://127.0.0.1:${options.port}`,
  ];
  log(`启动 Codex CDP 窗口：${executable}`);
  const child = spawn(executable, args, {
    detached: false,
    stdio: "ignore",
    env: { ...process.env, ELECTRON_RUN_AS_NODE: undefined },
  });
  child.once("error", (error) => log(`Codex 进程错误：${error.message}`));
  return child;
}

async function startBoardServer(serverPort) {
  const child = spawn(
    process.execPath,
    [PYTHON_LAUNCHER, SERVER_FILE, "--host", "127.0.0.1", "--port", String(serverPort)],
    {
      cwd: PLUGIN_ROOT,
      stdio: ["ignore", "pipe", "inherit"],
      env: process.env,
    },
  );
  const reader = createInterface({ input: child.stdout });
  const ready = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("本地 Branch Keeper 看板服务启动超时")), 10000);
    reader.on("line", (line) => {
      try {
        const payload = JSON.parse(line);
        if (!payload.ready) return;
        clearTimeout(timeout);
        resolve(payload);
      } catch {
        log(line);
      }
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.once("exit", (code) => {
      if (code && code !== 0) reject(new Error(`看板服务退出：${code}`));
    });
  });
  const payload = await ready;
  reader.close();
  return { child, url: payload.url };
}

async function renderInjectionSource(boardUrl, capability) {
  const template = await readFile(INJECTION_FILE, "utf8");
  const sourceHash = createHash("sha256").update(`${template}\n${boardUrl}`).digest("hex").slice(0, 16);
  const source = template
    .replaceAll("__BRANCH_KEEPER_BOARD_URL__", JSON.stringify(boardUrl))
    .replaceAll("__BRANCH_KEEPER_CAPABILITY__", JSON.stringify(capability))
    .replaceAll("__BRANCH_KEEPER_SOURCE_HASH__", JSON.stringify(sourceHash));
  return { source, sourceHash };
}

function frameNodes(node, result = []) {
  result.push(node.frame);
  for (const child of node.childFrames || []) frameNodes(child, result);
  return result;
}

async function loadBoardFrames(client, targetId, boardDocument, capability, loadedFrames) {
  const tree = await client.call("Page.getFrameTree");
  const frameName = `branch-keeper-${capability}`;
  const frame = frameNodes(tree.frameTree).find((item) => item.name === frameName);
  if (!frame) return false;
  const key = `${targetId}:${frame.id}`;
  if (loadedFrames.has(key)) return true;
  await client.call("Page.setDocumentContent", { frameId: frame.id, html: boardDocument });
  loadedFrames.add(key);
  return true;
}

async function injectTarget(target, source, sourceHash, boardDocument, capability, loadedFrames) {
  const client = new CdpClient(target.webSocketDebuggerUrl);
  try {
    await client.connect();
    await client.call("Page.enable");
    try { await client.call("Page.setBypassCSP", { enabled: true }); } catch { /* older Codex builds */ }
    const status = await client.evaluate(`(() => {
      const value = window.__branchKeeperInjection__;
      return value ? { version: value.version, sourceHash: value.sourceHash, capability: value.capability } : null;
    })()`);
    if (!status || status.sourceHash !== sourceHash) {
      await client.call("Page.addScriptToEvaluateOnNewDocument", { source });
    }
    await client.evaluate(source);
    let confirmed = null;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      confirmed = await client.evaluate(`(() => {
        const value = window.__branchKeeperInjection__;
        return value ? { version: value.version, sourceHash: value.sourceHash, entryMounted: value.entryMounted } : null;
      })()`);
      if (confirmed?.entryMounted) break;
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    await loadBoardFrames(client, target.id, boardDocument, capability, loadedFrames);
    return confirmed;
  } finally {
    client.close();
  }
}

async function injectAll(port, source, sourceHash, boardDocument, capability, loadedFrames) {
  const targets = await listCodexTargets(port);
  if (!targets.length) return 0;
  let success = 0;
  for (const target of targets) {
    try {
      const status = await injectTarget(target, source, sourceHash, boardDocument, capability, loadedFrames);
      success += 1;
      const marker = `${status?.sourceHash || "unknown"}:${status?.entryMounted ? "ready" : "waiting"}`;
      if (injectAll.lastReports?.get(target.id) !== marker) {
        log(`已注入 ${target.title || target.url}${status?.entryMounted ? "（侧栏入口已挂载）" : ""}`);
        injectAll.lastReports ||= new Map();
        injectAll.lastReports.set(target.id, marker);
      }
    } catch (error) {
      log(`注入失败 ${target.title || target.url}：${error.message}`);
    }
  }
  return success;
}

function openExternal(url) {
  execFile("open", [url], (error) => {
    if (error) log(`打开看板失败：${error.message}`);
  });
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  const capability = randomToken();
  const server = await startBoardServer(options.serverPort);
  const { source, sourceHash } = await renderInjectionSource(server.url, capability);
  const boardHtml = await getText(server.url);
  const boardDocument = boardHtml.replace(
    "</head>",
    `<script>window.__BRANCH_KEEPER_API_BASE__=${JSON.stringify(server.url.replace(/\/$/, ""))};window.__BRANCH_KEEPER_CAPABILITY__=${JSON.stringify(capability)};</script></head>`,
  );
  const loadedFrames = new Set();
  log(`本地看板：${server.url}`);
  if (options.open) openExternal(server.url);

  let codexProcess;
  if (options.launch) {
    codexProcess = await launchCodex(options);
  }

  try {
    await waitForTargets(options.port);
    await injectAll(options.port, source, sourceHash, boardDocument, capability, loadedFrames);
  } catch (error) {
    server.child.kill();
    throw error;
  }

  if (!options.watch) {
    server.child.kill();
    server.child.unref();
    codexProcess?.unref();
    return;
  }

  const timer = setInterval(async () => {
    try { await injectAll(options.port, source, sourceHash, boardDocument, capability, loadedFrames); } catch { /* Codex may be restarting */ }
  }, 2000);

  const shutdown = () => {
    clearInterval(timer);
    server.child.kill();
    if (codexProcess && !codexProcess.killed) codexProcess.kill();
  };
  process.once("SIGINT", () => { shutdown(); process.exit(0); });
  process.once("SIGTERM", () => { shutdown(); process.exit(0); });
  await new Promise(() => {});
}

main().catch((error) => {
  console.error(`[branch-keeper] ${error.message}`);
  process.exitCode = 1;
});
