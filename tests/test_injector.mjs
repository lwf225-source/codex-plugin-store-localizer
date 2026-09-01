import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import {fileURLToPath} from "node:url";
import path from "node:path";


const testDir = path.dirname(fileURLToPath(import.meta.url));
const injectorSource = fs.readFileSync(path.join(testDir, "..", "scripts", "injector.js"), "utf8");
const fullDictionaryPath = path.join(testDir, "..", "assets", "dom-translations.zh-Hans.json");


class TextNode {
  constructor(value) {
    this.nodeType = 3;
    this.nodeValue = value;
    this.parentElement = null;
  }
  get textContent() {
    return this.nodeValue;
  }
}


class Element {
  constructor(...children) {
    this.nodeType = 1;
    this.childNodes = [];
    this.parentElement = null;
    this.className = "";
    this.classList = {contains: (name) => this.className.split(/\s+/).includes(name)};
    for (const child of children) this.append(child);
  }
  append(child) {
    child.parentElement = this;
    this.childNodes.push(child);
  }
  get textContent() {
    return this.childNodes.map((child) => child.textContent).join(" ");
  }
  matches(selector) {
    return selector === ".line-clamp-1" && this.classList.contains("line-clamp-1");
  }
  querySelectorAll(selector) {
    const matches = [];
    const visit = (node) => {
      for (const child of node.childNodes || []) {
        if (child.nodeType === 1 && child.matches(selector)) matches.push(child);
        visit(child);
      }
    };
    visit(this);
    return matches;
  }
}


function withClass(element, className) {
  element.className = className;
  return element;
}


class FakeDocument {
  constructor(body) {
    this.nodeType = 9;
    this.body = body;
    this.documentElement = new Element(body);
    this.childNodes = [this.documentElement];
  }
  createTreeWalker(root) {
    const nodes = [];
    const visit = (node) => {
      if (node.nodeType === 3) nodes.push(node);
      for (const child of node.childNodes || []) visit(child);
    };
    visit(root);
    let index = 0;
    return {nextNode: () => nodes[index++] || null};
  }
  addEventListener() {}
}


class FakeMutationObserver {
  constructor(callback) {
    this.callback = callback;
    this.disconnected = false;
  }
  observe() {}
  disconnect() {
    this.disconnected = true;
  }
}


function makeData() {
  return {
    schema_version: 3,
    locale: "zh-Hans",
    plugin_descriptions: [
      {
        display_name: "Gmail",
        source_short: ["Read and manage Gmail"],
        target_short: "读取和管理 Gmail",
      },
      {
        display_name: "Product Design",
        source_short: ["Explore and prototype ideas"],
        target_short: "探索创意并制作原型",
      },
    ],
    plugin_details: [
      {
        display_name: "Gmail",
        source_long: ["Use Gmail to summarize inbox activity."],
        target_long: "使用 Gmail 汇总收件箱动态。",
      },
    ],
    plugin_texts: [
      {
        display_name: "Product Design",
        kind: "detail_short",
        source: "Explore and prototype ideas",
        target: "探索创意并制作原型",
      },
      {
        display_name: "Product Design",
        kind: "prompt",
        source: "Help me get started",
        target: "帮助我开始使用",
      },
      {
        display_name: "Product Design",
        kind: "skill_name",
        source: "Audit",
        target: "审查",
      },
    ],
    host_strings: [{source: "New & Noteworthy", target: "新品与精选"}],
  };
}


async function runInjector(body, data = makeData()) {
  const reports = [];
  const context = {
    console,
    TextDecoder,
    Uint8Array,
    Symbol,
    JSON,
    document: new FakeDocument(body),
    location: {protocol: "app:"},
    MutationObserver: FakeMutationObserver,
    NodeFilter: {SHOW_TEXT: 4},
    clearTimeout,
    setTimeout,
    __CODEX_PLUGIN_STORE_ZH_DATA__: data,
    __codexPluginStoreZhReport: (payload) => reports.push(JSON.parse(payload)),
  };
  context.globalThis = context;
  vm.runInNewContext(injectorSource, context, {filename: "injector.js"});
  await new Promise((resolve) => setTimeout(resolve, 120));
  return {context, reports};
}


test("translates an exact plugin description and category heading", async () => {
  const heading = new TextNode("New & Noteworthy");
  const description = new TextNode("Read and manage Gmail");
  const body = new Element(
    new TextNode("安装"),
    heading,
    new Element(new TextNode("Gmail"), withClass(new Element(description), "line-clamp-1")),
  );
  const {reports} = await runInjector(body);
  assert.equal(description.nodeValue, "读取和管理 Gmail");
  assert.equal(heading.nodeValue, "新品与精选");
  assert.ok(reports.at(-1).translated_nodes >= 2);
  assert.equal(reports.at(-1).unmatched_sources, 0);
});

test("uses the selected locale and sets RTL only for Arabic", async () => {
  const data = makeData();
  data.locale = "ar";
  data.plugin_descriptions[0].target_short = "قراءة Gmail وإدارته";
  const description = new TextNode("Read and manage Gmail");
  const body = new Element(
    new TextNode("Install"),
    new Element(new TextNode("Gmail"), withClass(new Element(description), "line-clamp-1")),
  );
  const {context} = await runInjector(body, data);
  assert.equal(description.nodeValue, "قراءة Gmail وإدارته");
  assert.equal(context.document.documentElement.lang, "ar");
  assert.equal(context.document.documentElement.dir, "rtl");
});


test("does not translate a description without its matching plugin name", async () => {
  const description = new TextNode("Read and manage Gmail");
  const body = new Element(
    new TextNode("安装"),
    new Element(
      new TextNode("Gmail"),
      withClass(new Element(new TextNode("Some other description")), "line-clamp-1"),
    ),
    new Element(new TextNode("Another app"), withClass(new Element(description), "line-clamp-1")),
  );
  const {reports} = await runInjector(body);
  assert.equal(description.nodeValue, "Read and manage Gmail");
  assert.equal(reports.at(-1).translated_nodes, 0);
  assert.equal(reports.at(-1).unmatched_sources, 1);
});


test("translates a detail only inside the matching single-plugin panel", async () => {
  const detail = new TextNode("Use Gmail to summarize inbox activity.");
  const body = new Element(
    new TextNode("安装"),
    new Element(new TextNode("Gmail"), detail),
  );
  const {reports} = await runInjector(body);
  assert.equal(detail.nodeValue, "使用 Gmail 汇总收件箱动态。");
  assert.equal(reports.at(-1).unmatched_detail_sources, 0);
});


test("does not translate a detail without the matching plugin name", async () => {
  const detail = new TextNode("Use Gmail to summarize inbox activity.");
  const body = new Element(
    new TextNode("安装"),
    new Element(new TextNode("Another app"), detail),
  );
  const {reports} = await runInjector(body);
  assert.equal(detail.nodeValue, "Use Gmail to summarize inbox activity.");
  assert.equal(reports.at(-1).unmatched_detail_sources, 0);
});


test("translates detail short text, prompts, and skill names for the matching plugin", async () => {
  const detailShort = new TextNode("Explore and prototype ideas");
  const prompt = new TextNode("Help me get started");
  const skillName = new TextNode("Audit");
  let deeplyNestedSkills = new Element(prompt, skillName);
  for (let depth = 0; depth < 16; depth += 1) deeplyNestedSkills = new Element(deeplyNestedSkills);
  const body = new Element(
    new TextNode("立即试用"),
    new Element(new TextNode("Product Design"), detailShort, deeplyNestedSkills),
  );
  const {reports} = await runInjector(body);
  assert.equal(detailShort.nodeValue, "探索创意并制作原型");
  assert.equal(prompt.nodeValue, "帮助我开始使用");
  assert.equal(skillName.nodeValue, "审查");
  assert.equal(reports.at(-1).unmatched_plugin_text_sources, 0);
});


test("does not translate plugin-specific text on another plugin page", async () => {
  const prompt = new TextNode("Help me get started");
  const body = new Element(new TextNode("立即试用"), new TextNode("Another app"), prompt);
  const {reports} = await runInjector(body);
  assert.equal(prompt.nodeValue, "Help me get started");
  assert.equal(reports.at(-1).unmatched_plugin_text_sources, 0);
});


test("handles thousands of project names and shared detail strings without quadratic scans", async () => {
  const data = makeData();
  data.plugin_descriptions = [];
  data.plugin_details = [];
  data.plugin_texts = [];
  for (let index = 0; index < 3200; index += 1) {
    const displayName = `Catalog Project ${index}`;
    data.plugin_descriptions.push({
      display_name: displayName,
      source_short: [`Card description ${index}`],
      target_short: `卡片简介 ${index}`,
    });
    data.plugin_texts.push({
      display_name: displayName,
      kind: "skill_name",
      source: "Shared action",
      target: `共享操作 ${index}`,
    });
  }
  const target = new TextNode("Shared action");
  const body = new Element(new TextNode("立即试用"), new TextNode("Catalog Project 3199"), target);
  const started = performance.now();
  await runInjector(body, data);
  const elapsed = performance.now() - started;
  assert.equal(target.nodeValue, "共享操作 3199");
  assert.ok(elapsed < 1000, `synthetic full catalog scan took ${elapsed}ms`);
});


test("does not alter ordinary app pages even when text matches a catalog entry", async () => {
  const description = new TextNode("Read and manage Gmail");
  const body = new Element(
    new TextNode("Gmail"),
    withClass(new Element(description), "line-clamp-1"),
  );
  await runInjector(body);
  assert.equal(description.nodeValue, "Read and manage Gmail");
});


test("loads and translates with the actual complete catalog payload", async () => {
  const data = JSON.parse(fs.readFileSync(fullDictionaryPath, "utf8"));
  assert.ok(data.plugin_descriptions.length >= 3000);
  assert.ok(data.plugin_texts.length >= 12000);
  const sample = data.plugin_descriptions.find((item) => item.display_name === "Readwise")
    || data.plugin_descriptions[0];
  const description = new TextNode(sample.source_short[0]);
  const body = new Element(
    new TextNode("安装"),
    new Element(
      new TextNode(sample.display_name),
      withClass(new Element(description), "line-clamp-1"),
    ),
  );
  const started = performance.now();
  await runInjector(body, data);
  const elapsed = performance.now() - started;
  assert.equal(description.nodeValue, sample.target_short);
  assert.ok(elapsed < 2000, `actual full catalog initialization took ${elapsed}ms`);
});
