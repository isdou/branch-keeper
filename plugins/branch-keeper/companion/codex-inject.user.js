(() => {
  "use strict";

  const VERSION = "0.2.0";
  const BOARD_URL = __BRANCH_KEEPER_BOARD_URL__;
  const CAPABILITY = __BRANCH_KEEPER_CAPABILITY__;
  const SOURCE_HASH = __BRANCH_KEEPER_SOURCE_HASH__;
  const SENTINEL = "__branchKeeperInjection__";
  const ENTRY_ID = "branch-keeper-codex-entry";
  const FALLBACK_ID = "branch-keeper-codex-fallback";
  const SURFACE_ID = "branch-keeper-codex-surface";
  const PLUGIN_LABELS = new Set(["插件", "plugins", "plugin"]);
  const NEW_TASK_LABELS = new Set(["新建任务", "新对话", "new task", "new chat", "new conversation"]);

  const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  const exactLabel = (value, labels) => labels.has(normalize(value));
  const visible = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };

  const previous = window[SENTINEL];
  if (previous && previous.version === VERSION && previous.sourceHash === SOURCE_HASH && previous.capability === CAPABILITY) return;
  try { previous?.cleanup?.(); } catch { /* stale injection cleanup is best effort */ }

  const state = {
    version: VERSION,
    sourceHash: SOURCE_HASH,
    capability: CAPABILITY,
    boardUrl: BOARD_URL,
    entryMounted: false,
    active: false,
    entry: null,
    fallback: null,
    surface: null,
    frame: null,
    refreshing: false,
    observer: null,
    interval: null,
  };
  window[SENTINEL] = state;

  function findReferenceButton() {
    const candidates = [...document.querySelectorAll("button, [role=button], [data-app-action-sidebar-section]")]
      .filter((element) => !element.closest(`#${ENTRY_ID}`) && visible(element));
    const exact = candidates.find((element) => {
      const label = element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent;
      return exactLabel(label, PLUGIN_LABELS);
    });
    if (exact) return exact;
    return candidates.find((element) => {
      const text = normalize(element.textContent);
      return text === "插件" || text === "plugins" || text.includes("插件") && text.length < 20;
    }) || null;
  }

  function findMainHost() {
    const layout = document.querySelector("[data-app-shell-main-content-layout]");
    if (layout) return layout;
    return document.querySelector(".app-shell-main-content-frame")?.parentElement || document.body;
  }

  function setLabel(entry) {
    entry.setAttribute("aria-label", "Branch Keeper");
    entry.setAttribute("title", "Branch Keeper");
    entry.removeAttribute("id");
    entry.id = ENTRY_ID;
    entry.innerHTML = `<svg aria-hidden="true" class="branch-keeper-entry-icon" viewBox="0 0 16 16" fill="none"><path d="M5 2.5v4.25m0 0v1.5m0-1.5h4a3 3 0 0 1 3 3v3.75M5 8.25a3 3 0 0 0-3 3v.25" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/><circle cx="5" cy="2.5" r="1.35" fill="currentColor"/><circle cx="12" cy="13.5" r="1.35" fill="currentColor"/><circle cx="2" cy="13.5" r="1.35" fill="currentColor"/></svg><span>Branch Keeper</span>`;
    entry.style.cursor = "pointer";
    entry.classList.add("branch-keeper-entry");
  }

  function openBoard(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    state.active = true;
    state.entry?.classList.add("branch-keeper-selected");
    state.fallback?.classList.add("branch-keeper-selected");
    mountSurface();
  }

  function closeBoard() {
    state.active = false;
    state.entry?.classList.remove("branch-keeper-selected");
    state.fallback?.classList.remove("branch-keeper-selected");
    state.surface?.remove();
    state.surface = null;
    state.frame = null;
  }

  function createEntry(reference) {
    const entry = reference.cloneNode(true);
    setLabel(entry);
    entry.addEventListener("click", openBoard);
    return entry;
  }

  function createFallback() {
    if (state.fallback?.isConnected) return;
    const button = document.createElement("button");
    button.id = FALLBACK_ID;
    button.type = "button";
    button.innerHTML = `<svg aria-hidden="true" class="branch-keeper-entry-icon" viewBox="0 0 16 16" fill="none"><path d="M5 2.5v4.25m0 0v1.5m0-1.5h4a3 3 0 0 1 3 3v3.75M5 8.25a3 3 0 0 0-3 3v.25" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/><circle cx="5" cy="2.5" r="1.35" fill="currentColor"/><circle cx="12" cy="13.5" r="1.35" fill="currentColor"/><circle cx="2" cy="13.5" r="1.35" fill="currentColor"/></svg><span>Branch Keeper</span>`;
    button.setAttribute("aria-label", "Branch Keeper");
    button.addEventListener("click", openBoard);
    document.body.appendChild(button);
    state.fallback = button;
  }

  function ensureEntry() {
    if (state.refreshing) return;
    state.refreshing = true;
    try {
      const existing = document.getElementById(ENTRY_ID);
      if (existing) {
        state.entry = existing;
        state.entryMounted = true;
        state.fallback?.remove();
        state.fallback = null;
        return;
      }
      const reference = findReferenceButton();
      if (!reference) {
        createFallback();
        state.entryMounted = true;
        return;
      }
      const entry = createEntry(reference);
      reference.insertAdjacentElement("afterend", entry);
      state.entry = entry;
      state.entryMounted = true;
      state.fallback?.remove();
      state.fallback = null;
    } finally {
      state.refreshing = false;
    }
  }

  function mountSurface() {
    if (state.surface?.isConnected) return;
    const host = findMainHost();
    if (!host) return;
    const originalPosition = host.style.position;
    if (!originalPosition) host.style.position = "relative";
    const surface = document.createElement("section");
    surface.id = SURFACE_ID;
    surface.setAttribute("aria-label", "Branch Keeper taskboard");
    surface.style.cssText = "position:absolute;inset:0;z-index:2147483000;background:#f7f7f8;overflow:hidden;";
    const frame = document.createElement("iframe");
    frame.title = "Branch Keeper";
    frame.name = `branch-keeper-${CAPABILITY}`;
    frame.sandbox.add("allow-scripts", "allow-forms", "allow-modals", "allow-downloads");
    frame.allow = "clipboard-read; clipboard-write";
    frame.style.cssText = "display:block;width:100%;height:100%;border:0;background:#f7f7f8;";
    // Codex may block a direct app:// -> loopback navigation. The companion
    // fills this about:blank frame through Page.setDocumentContent over CDP.
    frame.src = "about:blank";
    frame.dataset.branchKeeperBoard = BOARD_URL;
    surface.appendChild(frame);
    host.appendChild(surface);
    state.surface = surface;
    state.frame = frame;
    state.originalHostPosition = originalPosition;
  }

  function clickNewTask() {
    const candidates = [...document.querySelectorAll("button, [role=button], a")].filter(visible);
    const button = candidates.find((element) => {
      const label = element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent;
      return exactLabel(label, NEW_TASK_LABELS);
    });
    if (button) {
      try { button.click(); return true; } catch { /* continue to composer */ }
    }
    return false;
  }

  function composer() {
    const candidates = [...document.querySelectorAll(
      '[data-codex-composer="true"], textarea, [contenteditable="true"]'
    )].filter(visible);
    return candidates.find((element) => element.matches('[data-codex-composer="true"]')) || candidates[0] || null;
  }

  function putText(element, value) {
    element.focus();
    if (element.matches("[contenteditable=\"true\"]")) {
      element.textContent = value;
      element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    } else {
      const prototype = Object.getPrototypeOf(element);
      const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
      if (descriptor?.set) descriptor.set.call(element, value);
      else element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function prepareComposer(prompt) {
    return new Promise((resolve) => {
      closeBoard();
      clickNewTask();
      let attempts = 0;
      const tryFill = () => {
        const target = composer();
        if (target) {
          putText(target, prompt);
          resolve(true);
          return;
        }
        attempts += 1;
        if (attempts < 30) {
          window.setTimeout(tryFill, 250);
        } else {
          resolve(false);
        }
      };
      window.setTimeout(tryFill, 160);
    });
  }

  function openSource(sourceUrl, threadId) {
    closeBoard();
    if (threadId) {
      const thread = [...document.querySelectorAll("[data-app-action-sidebar-thread-id]")]
        .find((element) => element.getAttribute("data-app-action-sidebar-thread-id") === threadId);
      if (thread) {
        thread.click();
        return;
      }
      try { window.location.assign(`codex://threads/${encodeURIComponent(threadId)}`); return; } catch { /* fallback */ }
    }
    if (sourceUrl) {
      try { window.open(sourceUrl, "_blank", "noopener"); } catch { /* best effort */ }
    }
  }

  async function handleFrameMessage(event) {
    if (!state.frame || event.source !== state.frame.contentWindow) return;
    const data = event.data || {};
    if (data.capability !== CAPABILITY) return;
    if (data.type === "branch-keeper:resume" && data.continuation_prompt) {
      const prepared = await prepareComposer(data.continuation_prompt);
      if (data.resume_id) {
        const endpoint = String(BOARD_URL).replace(/\/$/, "") + "/api/resumes/" + encodeURIComponent(data.resume_id) + "/result";
        try {
          await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              result_status: prepared ? "succeeded" : "failed",
              result_summary: prepared ? "Codex composer prepared" : "Codex composer not found"
            })
          });
        } catch {
          // The composer handoff is already complete; a local result write is best effort.
        }
      }
    } else if (data.type === "branch-keeper:open-source") {
      openSource(data.source_url, data.thread_id);
    }
  }

  function handleNativeNavigation(event) {
    if (!state.active) return;
    const target = event.target?.closest?.("button, [role=button], a");
    if (!target || target.closest(`#${ENTRY_ID}`) || target.closest(`#${FALLBACK_ID}`) || target.closest(`#${SURFACE_ID}`)) return;
    closeBoard();
  }

  function addStyles() {
    if (document.getElementById("branch-keeper-codex-style")) return;
    const style = document.createElement("style");
    style.id = "branch-keeper-codex-style";
    style.textContent = `
      #${ENTRY_ID}, #${FALLBACK_ID} { transition: background .15s ease, color .15s ease; }
      #${ENTRY_ID}.branch-keeper-selected, #${FALLBACK_ID}.branch-keeper-selected { background: rgba(240,164,60,.18) !important; color: #f0a43c !important; }
      #${ENTRY_ID} .branch-keeper-entry-icon, #${FALLBACK_ID} .branch-keeper-entry-icon { flex:none;display:block;width:16px;height:16px;margin-right:8px;color:currentColor; }
      #${FALLBACK_ID} { position:fixed;left:16px;bottom:18px;z-index:2147483646;display:flex;align-items:center;padding:5px 8px;border:0;border-radius:12.5px;background:rgba(255,255,255,.96);color:#4c4f69;box-shadow:0 4px 16px rgba(40,44,55,.14);font:500 13px -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;cursor:pointer; }
    `;
    document.head.appendChild(style);
  }

  function cleanup() {
    state.observer?.disconnect();
    if (state.interval) window.clearInterval(state.interval);
    window.removeEventListener("message", handleFrameMessage);
    document.removeEventListener("click", handleNativeNavigation, true);
    state.entry?.remove();
    state.fallback?.remove();
    state.surface?.remove();
    document.getElementById("branch-keeper-codex-style")?.remove();
    delete window[SENTINEL];
  }

  state.cleanup = cleanup;
  addStyles();
  ensureEntry();
  window.addEventListener("message", handleFrameMessage);
  document.addEventListener("click", handleNativeNavigation, true);
  state.observer = new MutationObserver(() => window.setTimeout(ensureEntry, 0));
  state.observer.observe(document.documentElement, { childList: true, subtree: true });
  state.interval = window.setInterval(ensureEntry, 1200);
})();
