#!/usr/bin/env python3
import json
import os
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

USER = os.environ.get("GITHUB_STAR_USER", "denghuinow")
TOKEN = os.environ.get("GITHUB_TOKEN")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CATEGORIES_DIR = ROOT / "categories"
OVERRIDES_FILE = ROOT / "overrides.json"

CATEGORY_ORDER = [
    "AI / Agents",
    "AI / LLM",
    "AI / LLM Serving",
    "AI / RAG & Knowledge",
    "AI / NL2SQL",
    "Quant / Finance",
    "Data / Visualization",
    "Dev Tools",
    "DevOps / Cloud",
    "Embedded / Hardware",
    "Networking / Security",
    "Learning / Resources",
    "Other",
]

RULES = [
    ("AI / Agents", ["agent", "agents", "agentic", "mcp", "tool-use", "tool use", "autogen", "crew", "codex", "claude code", "coding agent"]),
    ("AI / LLM Serving", ["vllm", "inference", "serving", "llm serving", "sglang", "tensorrt-llm", "ollama", "llama.cpp", "lmdeploy", "kv cache", "speculative decoding"]),
    ("AI / RAG & Knowledge", ["rag", "retrieval", "knowledge base", "knowledge-base", "vector database", "vector-db", "embedding", "graphrag"]),
    ("AI / NL2SQL", ["nl2sql", "text2sql", "text-to-sql", "sql agent"]),
    ("Quant / Finance", ["quant", "trading", "stock", "finance", "financial", "backtest", "broker", "ibkr", "market data", "crypto", "portfolio"]),
    ("Data / Visualization", ["visualization", "plot", "chart", "dashboard", "matplotlib", "vega", "grafana", "bi ", "business intelligence"]),
    ("Embedded / Hardware", ["rp2040", "raspberry pi", "arduino", "microcontroller", "embedded", "firmware", "usb device", "tinyusb", "pico sdk", "stm32", "esp32"]),
    ("Networking / Security", ["proxy", "vpn", "openwrt", "network", "security", "pentest", "wifi", "wpa", "firewall", "wireguard", "tailscale", "browser automation"]),
    ("DevOps / Cloud", ["docker", "kubernetes", "k8s", "terraform", "ansible", "ci/cd", "devops", "container", "helm", "cloud native"]),
    ("Dev Tools", ["cli", "terminal", "editor", "ide", "developer tool", "code analysis", "parser", "debugger", "git ", "github action"]),
    ("Learning / Resources", ["awesome", "tutorial", "book", "course", "algorithm", "algorithms", "dataset", "corpus", "interview", "roadmap", "cheatsheet"]),
    ("AI / LLM", ["llm", "large language model", "language model", "chatgpt", "qwen", "deepseek", "transformer", "prompt", "fine-tun", "finetun", "nlp", "speech", "whisper", "tts"]),
]

SLUGS = {
    "AI / Agents": "ai-agents",
    "AI / LLM": "ai-llm",
    "AI / LLM Serving": "ai-llm-serving",
    "AI / RAG & Knowledge": "ai-rag-knowledge",
    "AI / NL2SQL": "ai-nl2sql",
    "Quant / Finance": "quant-finance",
    "Data / Visualization": "data-visualization",
    "Dev Tools": "dev-tools",
    "DevOps / Cloud": "devops-cloud",
    "Embedded / Hardware": "embedded-hardware",
    "Networking / Security": "networking-security",
    "Learning / Resources": "learning-resources",
    "Other": "other",
}


def api_get(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "github-stars-indexer"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_all_stars():
    repos = []
    page = 1
    while True:
        batch = api_get(f"https://api.github.com/users/{USER}/starred?per_page=100&page={page}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def load_overrides():
    if not OVERRIDES_FILE.exists():
        return {"categories": {}, "ignore": []}
    return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))


def classify(repo, overrides):
    full_name = repo["full_name"]
    if full_name in overrides.get("categories", {}):
        return overrides["categories"][full_name]
    fields = [
        repo.get("name") or "",
        repo.get("description") or "",
        repo.get("language") or "",
        " ".join(repo.get("topics") or []),
    ]
    text = " ".join(fields).lower()
    for category, needles in RULES:
        if any(n in text for n in needles):
            return category
    return "Other"


def status(repo, now):
    if repo.get("archived"):
        return "📦 Archived"
    pushed = repo.get("pushed_at")
    if not pushed:
        return "❔ Unknown"
    dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
    days = (now - dt).days
    if days <= 90:
        return "🔥 Active"
    if days <= 365:
        return "✅ Maintained"
    if days <= 1095:
        return "🕰️ Stable"
    return "⚠️ Stale"


def esc(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def render_table(repos, now):
    lines = [
        "| Repository | Description | Lang | Stars | Status | Last push |",
        "|---|---|---:|---:|---|---|",
    ]
    for r in sorted(repos, key=lambda x: (x.get("stargazers_count", 0), x["full_name"]), reverse=True):
        pushed = (r.get("pushed_at") or "")[:10] or "-"
        desc = esc(r.get("description")) or "-"
        lang = esc(r.get("language")) or "-"
        lines.append(
            f"| [{r['full_name']}]({r['html_url']}) | {desc} | {lang} | {r.get('stargazers_count', 0):,} | {status(r, now)} | {pushed} |"
        )
    return "\n".join(lines)


def main():
    now = datetime.now(timezone.utc)
    overrides = load_overrides()
    ignored = set(overrides.get("ignore", []))
    repos = [r for r in fetch_all_stars() if r.get("full_name") not in ignored]
    grouped = defaultdict(list)
    for repo in repos:
        grouped[classify(repo, overrides)].append(repo)

    DATA_DIR.mkdir(exist_ok=True)
    CATEGORIES_DIR.mkdir(exist_ok=True)
    compact = []
    for r in repos:
        compact.append({
            "full_name": r.get("full_name"),
            "html_url": r.get("html_url"),
            "description": r.get("description"),
            "language": r.get("language"),
            "stargazers_count": r.get("stargazers_count"),
            "forks_count": r.get("forks_count"),
            "topics": r.get("topics") or [],
            "pushed_at": r.get("pushed_at"),
            "updated_at": r.get("updated_at"),
            "archived": r.get("archived", False),
            "category": classify(r, overrides),
        })
    (DATA_DIR / "stars.json").write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for old in CATEGORIES_DIR.glob("*.md"):
        old.unlink()
    for cat in CATEGORY_ORDER:
        items = grouped.get(cat, [])
        if not items:
            continue
        body = f"# {cat}\n\n共 **{len(items)}** 个收藏。\n\n{render_table(items, now)}\n"
        (CATEGORIES_DIR / f"{SLUGS[cat]}.md").write_text(body, encoding="utf-8")

    counts = {cat: len(grouped.get(cat, [])) for cat in CATEGORY_ORDER if grouped.get(cat)}
    active = sum(1 for r in repos if status(r, now) == "🔥 Active")
    stale = sum(1 for r in repos if status(r, now) == "⚠️ Stale")
    archived = sum(1 for r in repos if status(r, now) == "📦 Archived")
    updated = now.strftime("%Y-%m-%d %H:%M UTC")

    readme = [
        "# GitHub Stars",
        "",
        f"自动整理 [@{USER}](https://github.com/{USER}) 的 GitHub Star 收藏。",
        "",
        f"**总计 {len(repos)} 个项目** · 🔥 Active {active} · ⚠️ Stale {stale} · 📦 Archived {archived}",
        "",
        f"最后同步：`{updated}`",
        "",
        "## 分类",
        "",
        "| Category | Count | Index |",
        "|---|---:|---|",
    ]
    for cat in CATEGORY_ORDER:
        if counts.get(cat):
            readme.append(f"| {cat} | {counts[cat]} | [查看](categories/{SLUGS[cat]}.md) |")
    readme += [
        "",
        "## 状态说明",
        "",
        "- 🔥 **Active**：最近 90 天有 push",
        "- ✅ **Maintained**：最近 1 年有 push",
        "- 🕰️ **Stable**：1～3 年未 push，可能是稳定项目",
        "- ⚠️ **Stale**：超过 3 年未 push",
        "- 📦 **Archived**：GitHub 已归档",
        "",
        "## 人工修正",
        "",
        "编辑 `overrides.json` 可指定分类或忽略项目。自动同步不会覆盖人工规则。",
        "",
        "## 自动更新",
        "",
        "GitHub Actions 每天自动同步一次，也支持从 Actions 页面手动运行。",
        "",
        "---",
        "Generated by `scripts/update_stars.py`.",
    ]
    (ROOT / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
