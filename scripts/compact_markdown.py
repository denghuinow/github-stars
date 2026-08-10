#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES_DIR = ROOT / "categories"
README_FILE = ROOT / "README.md"

CATEGORY_DESCRIPTIONS = {
    "AI / Agents": "智能体、编码助手、MCP 与工具调用生态",
    "AI / LLM": "大语言模型、训练微调、NLP 与语音相关项目",
    "AI / LLM Serving": "大模型推理、部署、加速与服务框架",
    "AI / RAG & Knowledge": "RAG、知识库、向量检索与 GraphRAG",
    "AI / NL2SQL": "自然语言转 SQL 与智能数据查询",
    "Quant / Finance": "量化交易、行情、投资组合与金融分析",
    "Data / Visualization": "数据分析、图表、BI 与可视化工具",
    "Dev Tools": "IDE、CLI、调试、代码分析与开发效率工具",
    "DevOps / Cloud": "容器、云原生、基础设施与运维自动化",
    "Embedded / Hardware": "MCU、嵌入式、固件、电子与硬件开发",
    "Networking / Security": "网络、代理、VPN、安全与渗透测试",
    "Learning / Resources": "教程、书籍、Awesome 列表、数据集与学习资料",
    "Other": "暂未归入其他主题的项目",
}


def simplify_category_table(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    in_table = False

    for line in lines:
        if line.startswith("| Repository |"):
            out.append("| Repository | 中文描述 | Stars | Classifier | Status | Last push |")
            in_table = True
            continue

        if in_table and line.startswith("|---"):
            out.append("|---|---|---:|---|---|---|")
            continue

        if in_table and line.startswith("|"):
            # Generated table columns:
            # Repository | 中文描述 | Original description | Lang | Stars | Classifier | Status | Last push
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 8:
                repo, desc_zh, _original, _lang, stars, classifier, status, last_push = cells[:8]
                out.append(
                    f"| {repo} | {desc_zh} | {stars} | {classifier} | {status} | {last_push} |"
                )
                continue

        if in_table and not line.startswith("|"):
            in_table = False

        out.append(line)

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def add_readme_category_descriptions() -> None:
    if not README_FILE.exists():
        return

    lines = README_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    in_category_table = False

    for line in lines:
        if line.strip() == "| Category | Count | Index |":
            out.append("| Category | 中文说明 | Count | Index |")
            in_category_table = True
            continue

        if in_category_table and line.startswith("|---"):
            out.append("|---|---|---:|---|")
            continue

        if in_category_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 3:
                category, count, index = cells[:3]
                desc = CATEGORY_DESCRIPTIONS.get(category, "-")
                out.append(f"| {category} | {desc} | {count} | {index} |")
                continue

        if in_category_table and not line.startswith("|"):
            in_category_table = False

        # README wording should match the simplified project table.
        if "分类页同时保留 GitHub 原始 description 便于核对" in line:
            line = line.replace(
                "分类页同时保留 GitHub 原始 description 便于核对",
                "分类页展示简体中文项目描述，完整原始元数据仍保存在 `data/stars.json`",
            )

        out.append(line)

    README_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    if CATEGORIES_DIR.exists():
        for path in CATEGORIES_DIR.glob("*.md"):
            simplify_category_table(path)
    add_readme_category_descriptions()


if __name__ == "__main__":
    main()
