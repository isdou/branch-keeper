#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SCRIPT = resolve(PLUGIN_ROOT, "scripts", "branch_keeper_mcp.py");

function supportedPythonVersion(output) {
  const match = String(output || "").match(/Python\s+(\d+)\.(\d+)/i);
  if (!match) return false;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return major > 3 || (major === 3 && minor >= 10);
}

function canRun(candidate) {
  try {
    const result = spawnSync(
      candidate.command,
      [...candidate.args, "--version"],
      {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      },
    );
    if (result.error || result.status !== 0) return false;
    return supportedPythonVersion(`${result.stdout}\n${result.stderr}`);
  } catch {
    return false;
  }
}

function pythonCandidates() {
  const configured = process.env.BRANCH_KEEPER_PYTHON?.trim();
  if (configured) return [{ command: configured, args: [] }];

  if (process.platform === "win32") {
    return [
      { command: "py", args: ["-3"] },
      { command: "python", args: [] },
      { command: "python3", args: [] },
    ];
  }

  return [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ];
}

function resolveScript(scriptArgument) {
  if (!scriptArgument) return DEFAULT_SCRIPT;
  if (isAbsolute(scriptArgument)) return scriptArgument;
  const workingDirectoryPath = resolve(process.cwd(), scriptArgument);
  return existsSync(workingDirectoryPath) ? workingDirectoryPath : resolve(PLUGIN_ROOT, scriptArgument);
}

const [scriptArgument, ...scriptArguments] = process.argv.slice(2);
const scriptFile = resolveScript(scriptArgument);

if (!existsSync(scriptFile)) {
  console.error(`[branch-keeper] Python entrypoint not found: ${scriptFile}`);
  process.exit(1);
}

const python = pythonCandidates().find(canRun);
if (!python) {
  console.error("[branch-keeper] Python 3.10+ is required to run Branch Keeper.");
  console.error("Install Python or set BRANCH_KEEPER_PYTHON to its executable path.");
  process.exit(1);
}

const child = spawn(
  python.command,
  [...python.args, scriptFile, ...scriptArguments],
  {
    cwd: PLUGIN_ROOT,
    env: process.env,
    stdio: "inherit",
    windowsHide: true,
  },
);

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.once(signal, () => {
    if (!child.killed) child.kill(signal);
  });
}

child.once("error", (error) => {
  console.error(`[branch-keeper] Unable to start Python: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code) => {
  process.exitCode = code ?? 1;
});
