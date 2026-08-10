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


def normalize_ai_cache(raw):
    """Accept both legacy name->category strings and the new structured cache."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for name, value in raw.items():
        if isinstance(value, str):
            if value in VALID_CATEGORIES:
                out[name] = {"category": value, "description_zh": ""}
        elif isinstance(value, dict):
            category = value.get("category")
            description_zh = (value.get("description_zh") or "").strip()
            if category in VALID_CATEGORIES:
                out[name] = {
                    "category": category,
                    "description_zh": description_zh,
                }
    return out


def repo_for_ai(repo, category_hint=""):
    item = {
        "full_name": repo.get("full_name"),
        "description": repo.get("description") or "",
        "language": repo.get("language") or "",
        "topics": repo.get("topics") or [],
        "homepage": repo.get("homepage") or "",
    }
    if category_hint in VALID_CATEGORIES:
        item["existing_category"] = category_hint
    return item


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


def ai_analyze_once(repos, category_hints):
    categories = "\n".join(f"- {c}" for c in CATEGORY_ORDER)
    system = (
        "You organize GitHub repositories for a Chinese personal technical bookmark library. "
        "For EVERY supplied repository, return exactly one allowed category and one concise Simplified Chinese description. "
        "Classify by PRIMARY PURPOSE, not incidental keywords. If existing_category is supplied, preserve it unless it is clearly invalid. "
        "The Chinese description must explain what the project is/does in natural Chinese, preferably 15-45 Chinese characters, "
        "without marketing fluff, emojis, markdown, or a trailing period. "
        "You MUST include every supplied full_name exactly once. "
        "Return ONLY a JSON object. Each value must be an object with keys category and description_zh."
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
        "Required output shape example:\n"
        '{"owner/repo":{"category":"Dev Tools","description_zh":"面向开发者的代码分析与自动化工具"}}\n\n'
        f"Analyze all {len(repos)} repositories below in one response:\n"
        f"{json.dumps([repo_for_ai(r, category_hints.get(r['full_name'], '')) for r in repos], ensure_ascii=False, separators=(',', ':'))}"
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
    for name, value in parsed.items():
        if name not in expected or not isinstance(value, dict):
            continue
        category = value.get("category")
        description_zh = (value.get("description_zh") or "").strip()
        if category in VALID_CATEGORIES and description_zh:
            out[name] = {
                "category": category,
                "description_zh": description_zh,
            }
    return out


def ai_analyze_resilient(repos, category_hints, depth=0):
    """Prefer one paid request; retry only missing items, split only after a hard failure."""
    if not repos:
        return {}

    indent = "  " * depth
    try:
        print(f"{indent}AI request: {len(repos)} repositories (category + Chinese description)")
        analyzed = ai_analyze_once(repos, category_hints)
        missing = [r for r in repos if r["full_name"] not in analyzed]
        print(f"{indent}AI returned {len(analyzed)}/{len(repos)} valid results")

        if not missing:
            return analyzed

        if depth >= AI_MAX_SPLIT_DEPTH:
            print(f"{indent}{len(missing)} repositories still missing; local fallback will be used")
            return analyzed

        print(f"{indent}Retrying only {len(missing)} missing repositories")
        analyzed.update(ai_analyze_resilient(missing, category_hints, depth + 1))
        return analyzed

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"{indent}AI request failed: {exc}")
        if len(repos) <= 1 or depth >= AI_MAX_SPLIT_DEPTH:
            print(f"{indent}Local fallback will be used for these repositories")
            return {}

        midpoint = len(repos) // 2
        left, right = repos[:midpoint], repos[midpoint:]
        print(f"{indent}Splitting failed request into {len(left)} + {len(right)} repositories")
        out = ai_analyze_resilient(left, category_hints, depth + 1)
        out.update(ai_analyze_resilient(right, category_hints, depth + 1))
        return out


def build_metadata(repos, overrides):
    cache = normalize_ai_cache(load_json(AI_CACHE_FILE, {}))
    override_categories = overrides.get("categories", {})

    category_hints = {}
    for repo in repos:
        name = repo["full_name"]
        if override_categories.get(name) in VALID_CATEGORIES:
            category_hints[name] = override_categories[name]
        elif name in cache:
            category_hints[name] = cache[name]["category"]
        else:
            category_hints[name] = rule_classify(repo)

    # AI is required not only for new repos, but also once for legacy cached repos
    # that already have a category but do not yet have a Chinese description.
    need_ai = [
        r for r in repos
        if r["full_name"] not in cache or not cache[r["full_name"]].get("description_zh")
    ]

    ai_ok = bool(AI_API_KEY and AI_MODEL and AI_BASE_URL)
    if ai_ok and need_ai:
        print(
            f"AI enrichment: {len(need_ai)} repositories using {AI_MODEL}. "
            "Trying all missing metadata in ONE request."
        )
        analyzed = ai_analyze_resilient(need_ai, category_hints)
        for name, value in analyzed.items():
            # Manual category remains authoritative; only the Chinese description is taken from AI.
            category = override_categories.get(name)
            if category not in VALID_CATEGORIES:
                category = value["category"]
            cache[name] = {
                "category": category,
                "description_zh": value["description_zh"],
            }
        print(f"AI enrichment complete: {len(analyzed)}/{len(need_ai)} newly enriched")
    elif need_ai:
        print(
            "AI is not configured; category rules and original descriptions will be used as fallback. "
            "Set AI_API_KEY to enable semantic classification and Chinese descriptions."
        )

    categories = {}
    descriptions_zh = {}
    sources = {}
    for repo in repos:
        name = repo["full_name"]
        if name in override_categories and override_categories[name] in VALID_CATEGORIES:
            categories[name] = override_categories[name]
            sources[name] = "override"
        elif name in cache:
            categories[name] = cache[name]["category"]
            sources[name] = "ai"
        else:
            categories[name] = rule_classify(repo)
            sources[name] = "rule"

        if name in cache and cache[name].get("description_zh"):
            descriptions_zh[name] = cache[name]["description_zh"]
        else:
            descriptions_zh[name] = repo.get("description") or "-"

    if ai_ok:
        DATA_DIR.mkdir(exist_ok=True)
        AI_CACHE_FILE.write_text(
            json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return categories, descriptions_zh, sources


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


def render_table(repos, now, sources, descriptions_zh):
    lines = [
        "| Repository | 中文描述 | Original description | Lang | Stars | Classifier | Status | Last push |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for r in sorted(
        repos,
        key=lambda x: (x.get("stargazers_count", 0), x["full_name"]),
        reverse=True,
    ):
        name = r["full_name"]
        pushed = (r.get("pushed_at") or "")[:10] or "-"
        desc_zh = esc(descriptions_zh.get(name)) or "-"
        desc = esc(r.get("description")) or "-"
        lang = esc(r.get("language")) or "-"
        source = {
            "ai": "🤖 AI",
            "override": "📌 Manual",
            "rule": "⚙️ Rule",
        }.get(sources.get(name), "-")
        lines.append(
            f"| [{name}]({r['html_url']}) | {desc_zh} | {desc} | {lang} | "
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

    categories, descriptions_zh, sources = build_metadata(repos, overrides)
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
            "description_zh": descriptions_zh.get(name),
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
                f"{render_table(items, now, sources, descriptions_zh)}\n"
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
    zh_count = sum(1 for d in descriptions_zh.values() if d and d != "-")
    updated = now.strftime("%Y-%m-%d %H:%M UTC")

    readme = [
        "# GitHub Stars",
        "",
        f"自动整理 [@{USER}](https://github.com/{USER}) 的 GitHub Star 收藏。",
        "",
        f"**总计 {len(repos)} 个项目** · 🤖 AI {ai_count} · 📌 Manual {manual_count} · ⚙️ Rule {rule_count}",
        f"中文描述 {zh_count}/{len(repos)} · 🔥 Active {active} · ⚠️ Stale {stale} · 📦 Archived {archived}",
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
        "## AI 元数据",
        "",
        "AI 会同时生成项目分类和简体中文一句话描述。结果保存在 `data/ai_categories.json`，分类页同时保留 GitHub 原始 description 便于核对。",
        "",
        "旧版仅包含分类的缓存会自动迁移；缺少中文描述的旧项目会在下一次运行时一次性补齐。",
        "",
        "## 分类优先级",
        "",
        "`overrides.json` 人工指定 > AI 缓存分类 > 关键词规则兜底。人工分类不会被 AI 覆盖。",
        "",
        "首次或存在多个未缓存/未翻译项目时，会优先合并为一次 AI 请求；仅在请求失败或结果缺失时才对失败部分重试/拆分。",
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
