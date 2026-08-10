#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

USER = os.environ.get("GITHUB_STAR_USER", "denghuinow")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
AI_BASE_URL = (os.environ.get("AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
AI_API_KEY = os.environ.get("AI_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL") or "gpt-5-mini"
AI_TIMEOUT = max(30, int(os.environ.get("AI_TIMEOUT", "300")))
AI_MAX_SPLIT_DEPTH = max(0, int(os.environ.get("AI_MAX_SPLIT_DEPTH", "6")))

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CATEGORIES_DIR = ROOT / "categories"
OVERRIDES_FILE = ROOT / "overrides.json"
AI_CACHE_FILE = DATA_DIR / "ai_categories.json"

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
VALID_CATEGORIES = set(CATEGORY_ORDER)

RULES = [
    ("AI / Agents", ["agent", "agents", "agentic", "mcp", "tool-use", "tool use", "autogen", "crew", "codex", "claude code", "coding agent"]),
    ("AI / LLM Serving", ["vllm", "inference", "serving", "llm serving", "sglang", "tensorrt-llm", "ollama", "llama.cpp", "lmdeploy", "kv cache", "speculative decoding"]),
    ("AI / RAG & Knowledge", ["rag", "retrieval", "knowledge base", "knowledge-base", "vector database", "vector-db", "embedding", "graphrag"]),
    ("AI / NL2SQL", ["nl2sql", "text2sql", "text-to-sql", "sql agent"]),
    ("Quant / Finance", ["quant", "trading", "stock", "finance", "financial", "backtest", "broker", "ibkr", "market data", "crypto", "portfolio"]),
    ("Data / Visualization", ["visualization", "plot", "chart", "dashboard", "matplotlib", "vega", "grafana", "business intelligence"]),
    ("Embedded / Hardware", ["rp2040", "raspberry pi", "arduino", "microcontroller", "embedded", "firmware", "usb device", "tinyusb", "pico sdk", "stm32", "esp32"]),
    ("Networking / Security", ["proxy", "vpn", "openwrt", "network", "security", "pentest", "wifi", "wpa", "firewall", "wireguard", "tailscale", "browser automation"]),
    ("DevOps / Cloud", ["docker", "kubernetes", "k8s", "terraform", "ansible", "ci/cd", "devops", "container", "helm", "cloud native"]),
    ("Dev Tools", ["cli", "terminal", "editor", "ide", "developer tool", "code analysis", "parser", "debugger", "github action"]),
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


def request_json(url, *, headers=None, payload=None, timeout=60):
    hdrs = {"User-Agent": "github-stars-indexer", **(headers or {})}
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, headers=hdrs, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def github_get(url):
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return request_json(url, headers=headers, timeout=30)


def fetch_all_stars():
    repos = []
    page = 1
    while True:
        batch = github_get(f"https://api.github.com/users/{USER}/starred?per_page=100&page={page}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def load_overrides():
    return load_json(OVERRIDES_FILE, {"categories": {}, "ignore": []})


def rule_classify(repo):
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


def repo_for_ai(repo):
    return {
        "full_name": repo.get("full_name"),
        "description": repo.get("description") or "",
        "language": repo.get("language") or "",
        "topics": repo.get("topics") or [],
        "homepage": repo.get("homepage") or "",
    }


def extract_json_object(text):
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI response did not contain a JSON object")
    return json.loads(text[start:end + 1])


def ai_classify_once(repos):
    categories = "\n".join(f"- {c}" for c in CATEGORY_ORDER)
    system = (
        "You classify GitHub repositories for a personal technical bookmark library. "
        "Choose exactly one category for every repository. Classify by the repository's PRIMARY PURPOSE, not incidental keywords. "
        "You MUST include every supplied full_name exactly once. "
        "Return ONLY a JSON object mapping full_name to one allowed category, with no markdown or commentary."
    )
    user = (
        f"Allowed categories:\n{categories}\n\n"
        "Guidance:\n"
        "AI / Agents = autonomous/coding/tool-using agents and MCP ecosystems.\n"
        "AI / LLM = models, training, fine-tuning, NLP/speech projects not primarily serving/RAG/agents.\n"
        "AI / LLM Serving = inference engines, runtimes, acceleration, KV cache, model serving.\n"
        "AI / RAG & Knowledge = retrieval, vector DB, knowledge bases, GraphRAG.\n"
        "AI / NL2SQL = text-to-SQL/data querying by natural language.\n"
        "Quant / Finance = trading, market data, portfolio, financial analysis.\n"
        "Data / Visualization = charts, BI, dashboards, plotting and visualization.\n"
        "Dev Tools = IDE/CLI/debugging/parsing/code analysis/developer productivity.\n"
        "DevOps / Cloud = containers, orchestration, infra automation, cloud operations.\n"
        "Embedded / Hardware = MCU, firmware, electronics, Raspberry Pi/Arduino/USB devices.\n"
        "Networking / Security = networking, proxy/VPN, security, pentest, firewall/browser automation.\n"
        "Learning / Resources = tutorials, awesome lists, books, courses, datasets/reference collections.\n"
        "Other = none of the above.\n\n"
        f"Classify all {len(repos)} repositories below in one response:\n"
        f"{json.dumps([repo_for_ai(r) for r in repos], ensure_ascii=False, separators=(',', ':'))}"
    )
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}",
    }
    result = request_json(
        f"{AI_BASE_URL}/chat/completions",
        headers=headers,
        payload=payload,
        timeout=AI_TIMEOUT,
    )
    content = result["choices"][0]["message"]["content"]
    parsed = extract_json_object(content)
    out = {}
    expected = {r["full_name"] for r in repos}
    for name, category in parsed.items():
        if name in expected and category in VALID_CATEGORIES:
            out[name] = category
    return out


def ai_classify_resilient(repos, depth=0):
    """Prefer one paid request; retry only missing items, split only after a hard failure."""
    if not repos:
        return {}

    indent = "  " * depth
    try:
        print(f"{indent}AI request: {len(repos)} repositories")
        classified = ai_classify_once(repos)
        missing = [r for r in repos if r["full_name"] not in classified]
        print(f"{indent}AI returned {len(classified)}/{len(repos)} valid classifications")

        if not missing:
            return classified

        if depth >= AI_MAX_SPLIT_DEPTH:
            print(f"{indent}{len(missing)} repositories still missing; rule fallback will be used")
            return classified

        print(f"{indent}Retrying only {len(missing)} missing repositories")
        classified.update(ai_classify_resilient(missing, depth + 1))
        return classified

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"{indent}AI request failed: {exc}")
        if len(repos) <= 1 or depth >= AI_MAX_SPLIT_DEPTH:
            print(f"{indent}Rule fallback will be used for these repositories")
            return {}

        # Only split after the preferred all-in-one request actually fails.
        midpoint = len(repos) // 2
        left, right = repos[:midpoint], repos[midpoint:]
        print(f"{indent}Splitting failed request into {len(left)} + {len(right)} repositories")
        out = ai_classify_resilient(left, depth + 1)
        out.update(ai_classify_resilient(right, depth + 1))
        return out


def build_categories(repos, overrides):
    cache = load_json(AI_CACHE_FILE, {})
    cache = {k: v for k, v in cache.items() if v in VALID_CATEGORIES}
    override_categories = overrides.get("categories", {})
    need_ai = [
        r for r in repos
        if r["full_name"] not in override_categories and r["full_name"] not in cache
    ]

    ai_ok = bool(AI_API_KEY and AI_MODEL and AI_BASE_URL)
    if ai_ok and need_ai:
        print(
            f"AI classification: {len(need_ai)} uncached repositories using {AI_MODEL}. "
            "Trying all uncached repositories in ONE request."
        )
        classified = ai_classify_resilient(need_ai)
        cache.update(classified)
        print(f"AI classification complete: {len(classified)}/{len(need_ai)} newly cached")
    elif need_ai:
        print(
            "AI is not configured; using keyword rules as fallback. "
            "Set AI_API_KEY to enable semantic classification."
        )

    categories = {}
    sources = {}
    for repo in repos:
        name = repo["full_name"]
        if name in override_categories and override_categories[name] in VALID_CATEGORIES:
            categories[name] = override_categories[name]
            sources[name] = "override"
        elif name in cache:
            categories[name] = cache[name]
            sources[name] = "ai"
        else:
            categories[name] = rule_classify(repo)
            sources[name] = "rule"

    if ai_ok:
        DATA_DIR.mkdir(exist_ok=True)
        AI_CACHE_FILE.write_text(
            json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return categories, sources


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


def render_table(repos, now, sources):
    lines = [
        "| Repository | Description | Lang | Stars | Classifier | Status | Last push |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for r in sorted(
        repos,
        key=lambda x: (x.get("stargazers_count", 0), x["full_name"]),
        reverse=True,
    ):
        pushed = (r.get("pushed_at") or "")[:10] or "-"
        desc = esc(r.get("description")) or "-"
        lang = esc(r.get("language")) or "-"
        source = {
            "ai": "🤖 AI",
            "override": "📌 Manual",
            "rule": "⚙️ Rule",
        }.get(sources.get(r["full_name"]), "-")
        lines.append(
            f"| [{r['full_name']}]({r['html_url']}) | {desc} | {lang} | "
            f"{r.get('stargazers_count', 0):,} | {source} | {status(r, now)} | {pushed} |"
        )
    return "\n".join(lines)


def main():
    now = datetime.now(timezone.utc)
    overrides = load_overrides()
    ignored = set(overrides.get("ignore", []))
    repos = [r for r in fetch_all_stars() if r.get("full_name") not in ignored]
    DATA_DIR.mkdir(exist_ok=True)
    CATEGORIES_DIR.mkdir(exist_ok=True)

    categories, sources = build_categories(repos, overrides)
    grouped = defaultdict(list)
    for repo in repos:
        grouped[categories[repo["full_name"]]].append(repo)

    compact = []
    for r in repos:
        name = r.get("full_name")
        compact.append({
            "full_name": name,
            "html_url": r.get("html_url"),
            "description": r.get("description"),
            "language": r.get("language"),
            "stargazers_count": r.get("stargazers_count"),
            "forks_count": r.get("forks_count"),
            "topics": r.get("topics") or [],
            "pushed_at": r.get("pushed_at"),
            "updated_at": r.get("updated_at"),
            "archived": r.get("archived", False),
            "category": categories[name],
            "classifier": sources[name],
        })
    (DATA_DIR / "stars.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for old in CATEGORIES_DIR.glob("*.md"):
        old.unlink()
    for cat in CATEGORY_ORDER:
        items = grouped.get(cat, [])
        if items:
            body = (
                f"# {cat}\n\n共 **{len(items)}** 个收藏。\n\n"
                f"{render_table(items, now, sources)}\n"
            )
            (CATEGORIES_DIR / f"{SLUGS[cat]}.md").write_text(body, encoding="utf-8")

    counts = {
        cat: len(grouped.get(cat, []))
        for cat in CATEGORY_ORDER
        if grouped.get(cat)
    }
    active = sum(1 for r in repos if status(r, now) == "🔥 Active")
    stale = sum(1 for r in repos if status(r, now) == "⚠️ Stale")
    archived = sum(1 for r in repos if status(r, now) == "📦 Archived")
    ai_count = sum(1 for s in sources.values() if s == "ai")
    rule_count = sum(1 for s in sources.values() if s == "rule")
    manual_count = sum(1 for s in sources.values() if s == "override")
    updated = now.strftime("%Y-%m-%d %H:%M UTC")

    readme = [
        "# GitHub Stars",
        "",
        f"自动整理 [@{USER}](https://github.com/{USER}) 的 GitHub Star 收藏。",
        "",
        f"**总计 {len(repos)} 个项目** · 🤖 AI {ai_count} · 📌 Manual {manual_count} · ⚙️ Rule {rule_count}",
        f"🔥 Active {active} · ⚠️ Stale {stale} · 📦 Archived {archived}",
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
            readme.append(
                f"| {cat} | {counts[cat]} | [查看](categories/{SLUGS[cat]}.md) |"
            )
    readme += [
        "",
        "## 分类优先级",
        "",
        "`overrides.json` 人工指定 > AI 缓存分类 > 关键词规则兜底。",
        "",
        "AI 分类结果保存在 `data/ai_categories.json`。已有项目不会每天重复调用 AI；新增 Star 才需要新的 AI 分类。",
        "",
        "首次或存在多个未缓存项目时，会优先把全部未缓存项目合并为一次 AI 请求；仅在请求失败或结果缺失时才对失败部分重试/拆分。",
        "",
        "## 状态说明",
        "",
        "- 🔥 **Active**：最近 90 天有 push",
        "- ✅ **Maintained**：最近 1 年有 push",
        "- 🕰️ **Stable**：1～3 年未 push，可能是稳定项目",
        "- ⚠️ **Stale**：超过 3 年未 push",
        "- 📦 **Archived**：GitHub 已归档",
        "",
        "## AI 配置",
        "",
        "GitHub Actions 使用 `AI_API_KEY` Secret，以及 `AI_BASE_URL`、`AI_MODEL` Repository Variables。接口需兼容 OpenAI `/v1/chat/completions`。",
        "",
        "可选：`AI_TIMEOUT`（默认 300 秒）、`AI_MAX_SPLIT_DEPTH`（默认 6）。",
        "",
        "## 人工修正",
        "",
        "编辑 `overrides.json` 可锁定分类或忽略项目。人工规则始终优先。",
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
