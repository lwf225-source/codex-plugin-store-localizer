(() => {
  "use strict";

  const data = globalThis.__CODEX_PLUGIN_STORE_ZH_DATA__;
  delete globalThis.__CODEX_PLUGIN_STORE_ZH_DATA__;
  if (!data || data.schema_version !== 3 || typeof data.locale !== "string") return;
  if (globalThis.location?.protocol !== "app:") return;
  if (document.documentElement) {
    document.documentElement.lang = data.locale;
    document.documentElement.dir = data.locale === "ar" ? "rtl" : "ltr";
  }

  const stateKey = Symbol.for("codex.plugin-store-zh.injector");
  const previous = globalThis[stateKey];
  if (previous?.observer && typeof previous.observer.disconnect === "function") {
    previous.observer.disconnect();
  }
  if (previous?.reportTimer) clearTimeout(previous.reportTimer);
  if (previous?.scanTimer) clearTimeout(previous.scanTimer);

  const state = {
    version: 3,
    observer: null,
    reportTimer: null,
    scanTimer: null,
    pendingRoots: new Set(),
    directoryContext: null,
    translatedNodes: 0,
    scannedTextNodes: 0,
    scanBatches: 0,
    unmatchedSources: new Set(),
    unmatchedDetailSources: new Set(),
    unmatchedPluginTextSources: new Set(),
  };
  globalThis[stateKey] = state;

  const descriptionsBySource = new Map();
  for (const item of data.plugin_descriptions || []) {
    if (!item || typeof item.display_name !== "string" || typeof item.target_short !== "string") continue;
    if (!Array.isArray(item.source_short)) continue;
    for (const source of item.source_short) {
      if (typeof source !== "string" || source.length === 0) continue;
      const entries = descriptionsBySource.get(source) || [];
      entries.push({displayName: item.display_name, target: item.target_short});
      descriptionsBySource.set(source, entries);
    }
  }

  const detailsBySource = new Map();
  for (const item of data.plugin_details || []) {
    if (!item || typeof item.display_name !== "string" || typeof item.target_long !== "string") continue;
    if (!Array.isArray(item.source_long)) continue;
    for (const source of item.source_long) {
      if (typeof source !== "string" || source.length === 0) continue;
      const entries = detailsBySource.get(source) || [];
      entries.push({displayName: item.display_name, target: item.target_long});
      detailsBySource.set(source, entries);
    }
  }

  const pluginTextsBySource = new Map();
  for (const item of data.plugin_texts || []) {
    if (!item || typeof item.display_name !== "string" || typeof item.target !== "string") continue;
    if (typeof item.source !== "string" || item.source.length === 0) continue;
    const entries = pluginTextsBySource.get(item.source) || [];
    entries.push({displayName: item.display_name, kind: item.kind, target: item.target});
    pluginTextsBySource.set(item.source, entries);
  }

  const hostStrings = new Map();
  for (const item of data.host_strings || []) {
    if (item && typeof item.source === "string" && typeof item.target === "string") {
      hostStrings.set(item.source, item.target);
    }
  }

  const knownDisplayNames = [...new Set([
    ...(data.plugin_descriptions || []),
    ...(data.plugin_details || []),
    ...(data.plugin_texts || []),
  ].map((item) => item?.display_name)
    .filter((name) => typeof name === "string" && name.length > 0))];
  const knownDisplayNameSet = new Set(knownDisplayNames);

  function reportSoon() {
    if (state.reportTimer) clearTimeout(state.reportTimer);
    state.reportTimer = setTimeout(() => {
      state.reportTimer = null;
      const binding = globalThis.__codexPluginStoreZhReport;
      if (typeof binding !== "function") return;
      binding(JSON.stringify({
        version: 3,
        translated_nodes: state.translatedNodes,
        scanned_text_nodes: state.scannedTextNodes,
        scan_batches: state.scanBatches,
        unmatched_sources: state.unmatchedSources.size,
        unmatched_detail_sources: state.unmatchedDetailSources.size,
        unmatched_plugin_text_sources: state.unmatchedPluginTextSources.size,
      }));
    }, 80);
  }

  function replaceTrimmedText(node, source, target) {
    const raw = node.nodeValue;
    if (typeof raw !== "string") return false;
    const start = raw.indexOf(source);
    if (start < 0 || raw.trim() !== source) return false;
    node.nodeValue = raw.slice(0, start) + target + raw.slice(start + source.length);
    state.translatedNodes += 1;
    state.unmatchedSources.delete(source);
    reportSoon();
    return true;
  }

  function subtreeHasExactText(root, value) {
    if (!root) return false;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (typeof node.nodeValue === "string" && node.nodeValue.trim() === value) return true;
      node = walker.nextNode();
    }
    return false;
  }

  function exactNamesFromSet(root, allowedNames, limit = 2) {
    const result = new Set();
    if (!root || !(allowedNames instanceof Set) || allowedNames.size === 0) return result;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const value = typeof node.nodeValue === "string" ? node.nodeValue.trim() : "";
      if (value && allowedNames.has(value)) {
        result.add(value);
        if (result.size >= limit) break;
      }
      node = walker.nextNode();
    }
    return result;
  }

  function ancestorContainsDisplayName(node, displayName) {
    const descriptionElement = node.parentElement;
    if (!descriptionElement?.classList?.contains("line-clamp-1")) return false;
    let element = node.parentElement;
    for (let depth = 0; element && depth < 10; depth += 1, element = element.parentElement) {
      const nestedDescriptions = element.querySelectorAll?.(".line-clamp-1")?.length || 0;
      const includesSelf = element.matches?.(".line-clamp-1") ? 1 : 0;
      const descriptionCount = nestedDescriptions + includesSelf;
      if (descriptionCount > 1) return false;
      if (!subtreeHasExactText(element, displayName)) continue;
      // Current official plugin cards render their short description in a
      // single `.line-clamp-1` element. A section/grid ancestor contains one
      // such element per card, so it is rejected instead of enabling a
      // cross-card match. If this host structure changes, fail closed.
      return descriptionCount === 1;
    }
    return false;
  }

  function selectDetailCandidate(node, candidates) {
    const detailElement = node.parentElement;
    if (detailElement?.classList?.contains("line-clamp-1")) return null;
    const candidatesByName = new Map(candidates.map((candidate) => [candidate.displayName, candidate]));
    const candidateNames = new Set(candidatesByName.keys());
    let element = node.parentElement;
    for (let depth = 0; element && depth < 32; depth += 1, element = element.parentElement) {
      const matchingNames = exactNamesFromSet(element, candidateNames);
      if (matchingNames.size === 0) continue;
      if (matchingNames.size !== 1) return null;
      return candidatesByName.get([...matchingNames][0]) || null;
    }
    const body = document.body;
    const bodyNames = exactNamesFromSet(body, candidateNames);
    if (bodyNames.size !== 1) return null;
    return candidatesByName.get([...bodyNames][0]) || null;
  }

  function documentHasExactText(value) {
    return subtreeHasExactText(document.body, value);
  }

  function looksLikePluginDirectory() {
    if (typeof state.directoryContext === "boolean") return state.directoryContext;
    const content = document.body?.textContent;
    if (typeof content !== "string") return false;
    const hasDirectoryMarker = ["安装", "Install", "立即试用", "Try now", "复制链接", "Copy link"]
      .some((marker) => content.includes(marker));
    state.directoryContext = hasDirectoryMarker
      && exactNamesFromSet(document.body, knownDisplayNameSet, 1).size === 1;
    return state.directoryContext;
  }

  function translateTextNode(node) {
    if (!node || node.nodeType !== 3 || typeof node.nodeValue !== "string") return;
    const source = node.nodeValue.trim();
    if (!source) return;

    const isCatalogSource = descriptionsBySource.has(source)
      || detailsBySource.has(source)
      || pluginTextsBySource.has(source)
      || hostStrings.has(source);
    if (isCatalogSource && !looksLikePluginDirectory()) return;

    const candidates = descriptionsBySource.get(source);
    if (candidates) {
      const selected = candidates.find((candidate) => ancestorContainsDisplayName(node, candidate.displayName));
      if (selected) {
        replaceTrimmedText(node, source, selected.target);
      } else {
        state.unmatchedSources.add(source);
        reportSoon();
      }
      if (selected) return;
    }

    const detailCandidates = detailsBySource.get(source);
    if (detailCandidates) {
      const selected = selectDetailCandidate(node, detailCandidates);
      if (selected) {
        replaceTrimmedText(node, source, selected.target);
      } else {
        state.unmatchedDetailSources.add(source);
        reportSoon();
      }
      return;
    }

    const pluginTextCandidates = pluginTextsBySource.get(source);
    if (pluginTextCandidates) {
      const selected = selectDetailCandidate(node, pluginTextCandidates);
      if (selected) {
        replaceTrimmedText(node, source, selected.target);
        state.unmatchedPluginTextSources.delete(source);
      } else {
        state.unmatchedPluginTextSources.add(source);
        reportSoon();
      }
      return;
    }

    const hostTarget = hostStrings.get(source);
    if (hostTarget && looksLikePluginDirectory()) {
      replaceTrimmedText(node, source, hostTarget);
    }
  }

  function scan(root) {
    if (!root) return;
    if (root.nodeType === 3) {
      translateTextNode(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      state.scannedTextNodes += 1;
      translateTextNode(node);
      node = walker.nextNode();
    }
  }

  function scheduleScan(root) {
    if (!root) return;
    state.directoryContext = null;
    state.pendingRoots.add(root);
    if (state.scanTimer) return;
    state.scanTimer = setTimeout(() => {
      state.scanTimer = null;
      const roots = [...state.pendingRoots];
      state.pendingRoots.clear();
      state.scanBatches += 1;
      for (const pendingRoot of roots) scan(pendingRoot);
      reportSoon();
    }, 0);
  }

  function start() {
    if (!document.documentElement) return;
    scan(document);
    state.observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          scheduleScan(mutation.target);
        }
        for (const added of mutation.addedNodes || []) scheduleScan(added);
      }
    });
    state.observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    reportSoon();
  }

  if (document.documentElement) {
    start();
  } else {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  }
})();
