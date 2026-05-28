import json
import pathlib
import sys
import time
import urllib.request

import websocket


USER_DATA = pathlib.Path.home() / "AppData" / "Roaming" / "Antigravity"
PORT_FILE = USER_DATA / "DevToolsActivePort"

TRANSLATOR_JS = r"""
(() => {
  const exact = new Map(Object.entries({
    "File": "文件",
    "View": "视图",
    "Window": "窗口",
    "New Conversation": "新建对话",
    "Conversation History": "对话历史",
    "Scheduled Tasks": "计划任务",
    "Projects": "项目",
    "No conversations yet": "暂无对话",
    "Conversations": "对话",
    "Settings": "设置",
    "Starting The Conversation": "开始对话",
    "Toggle Sidebar": "切换侧边栏",
    "Go Back": "后退",
    "Go Forward": "前进",
    "Display Options": "显示选项",
    "Toggle Auxiliary Pane": "切换辅助面板",
    "Copy": "复制",
    "Copy code": "复制代码",
    "At mention code block": "引用代码块",
    "Good response": "回答不错",
    "Bad response": "回答不好",
    "Open Settings": "打开设置",
    "Sign In": "登录",
    "Account": "账户",
    "General": "通用",
    "Models": "模型",
    "Quota": "额度",
    "Customizations": "自定义",
    "Default Customizations": "默认自定义",
    "Customize Global Skills": "自定义全局技能",
    "Custom Agents": "自定义智能体",
    "MCP Servers": "MCP 服务器",
    "Notifications": "通知",
    "App": "应用",
    "Security": "安全",
    "Browser": "浏览器",
    "Editor": "编辑器",
    "Terminal": "终端",
    "Commands": "命令",
    "Files": "文件",
    "New Project": "新建项目",
    "Quick Start": "快速开始",
    "Create New Project": "创建新项目",
    "Select Project": "选择项目",
    "Create a new project. You can add folders to it now or later.": "创建一个新项目。你可以现在或稍后添加文件夹。",
    "Instantly create a new project and folder to start building.": "立即创建一个新项目和文件夹并开始构建。",
    "Start first conversation": "开始第一个对话",
    "Ask anything, @ to mention, / for actions": "输入消息，@ 提及，/ 执行动作",
    "Ask anything, @ to mention": "输入消息，@ 提及",
    "Worked for": "已执行",
    "See less": "收起"
  }));

  const rewriters = [
    [/^Worked for\s+(.+)$/i, "已执行 $1"],
    [/^See all \((\d+)\)$/i, "查看全部 ($1)"],
    [/^(\d+)m$/i, "$1 分钟"],
    [/^(\d+)h$/i, "$1 小时"],
    [/^(\d+)d$/i, "$1 天"]
  ];

  function translateText(raw) {
    if (!raw) return raw;
    const trimmed = raw.trim();
    if (!trimmed) return raw;
    let translated = exact.get(trimmed);
    if (!translated) {
      for (const [pattern, replacement] of rewriters) {
        if (pattern.test(trimmed)) {
          translated = trimmed.replace(pattern, replacement);
          break;
        }
      }
    }
    if (!translated || translated === trimmed) return raw;
    const leading = raw.match(/^\s*/)?.[0] ?? "";
    const trailing = raw.match(/\s*$/)?.[0] ?? "";
    return leading + translated + trailing;
  }

  function shouldSkipNode(node) {
    const parent = node.parentElement;
    if (!parent) return true;
    return parent.closest("pre, code, textarea, input, [contenteditable='true']");
  }

  function translateAttributes(element) {
    for (const attr of ["aria-label", "title", "placeholder", "data-placeholder"]) {
      const value = element.getAttribute?.(attr);
      if (!value) continue;
      const next = translateText(value);
      if (next !== value) element.setAttribute(attr, next);
    }
  }

  function translateOne(node) {
    if (!node) return;
    if (node.nodeType === Node.TEXT_NODE) {
      if (shouldSkipNode(node)) return;
      const next = translateText(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
      return;
    }
    if (node.nodeType === Node.ELEMENT_NODE) translateAttributes(node);
  }

  function translateTree(root) {
    if (!root) return;
    translateOne(root);
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) translateOne(node);
  }

  if (window.__antigravityZhObserver) {
    window.__antigravityZhObserver.disconnect();
  }
  translateTree(document.documentElement);
  window.__antigravityZhObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "characterData") {
        translateOne(mutation.target);
      } else if (mutation.type === "attributes") {
        translateOne(mutation.target);
      } else {
        for (const node of mutation.addedNodes) translateTree(node);
      }
    }
  });
  window.__antigravityZhObserver.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["aria-label", "title", "placeholder", "data-placeholder"]
  });
  return {
    language: navigator.language,
    title: document.title,
    body: document.body ? document.body.innerText.slice(0, 500) : ""
  };
})()
"""


def read_targets():
    port = PORT_FILE.read_text(encoding="utf-8").splitlines()[0].strip()
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as response:
        return port, json.load(response)


def send(ws, seq, method, params=None):
    seq += 1
    ws.send(json.dumps({"id": seq, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == seq:
            return seq, message


def main():
    deadline = time.time() + 45
    last_error = None
    while time.time() < deadline:
        try:
            if not PORT_FILE.exists():
                time.sleep(0.5)
                continue
            _, targets = read_targets()
            target = next(
                (
                    item
                    for item in targets
                    if item.get("type") == "page"
                    and str(item.get("url", "")).startswith("https://127.0.0.1")
                    and item.get("webSocketDebuggerUrl")
                ),
                None,
            )
            if not target:
                time.sleep(0.5)
                continue
            ws = websocket.create_connection(
                target["webSocketDebuggerUrl"], timeout=5, suppress_origin=True
            )
            seq = 0
            seq, _ = send(ws, seq, "Runtime.enable")
            seq, result = send(
                ws,
                seq,
                "Runtime.evaluate",
                {"expression": TRANSLATOR_JS, "returnByValue": True},
            )
            ws.close()
            value = result.get("result", {}).get("result", {}).get("value", {})
            print(json.dumps(value, ensure_ascii=False))
            return 0
        except Exception as exc:
            last_error = exc
            time.sleep(0.75)
    print(f"Failed to inject zh patch: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
