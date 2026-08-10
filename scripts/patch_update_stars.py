#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).with_name("update_stars.py")
s = p.read_text(encoding="utf-8")

# 1) Treat remote disconnects/timeouts as recoverable AI transport errors.
s = s.replace(
    "import json\nimport os\nimport urllib.error\n",
    "import json\nimport os\nimport http.client\nimport socket\nimport urllib.error\n",
    1,
)
s = s.replace(
    "except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:",
    "except (urllib.error.URLError, urllib.error.HTTPError, http.client.RemoteDisconnected, ConnectionResetError, socket.timeout, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:",
)

# 2) Accept several common OpenAI-compatible model JSON shapes.
marker = "def ai_analyze_once(repos, category_hints):\n"
helper = r'''def normalize_ai_response(parsed, repos, category_hints):
    expected = {r["full_name"] for r in repos}
    out = {}

    # Common wrappers: {"repositories": [...]}, {"results": [...]}, {"data": [...]}
    if isinstance(parsed, dict):
        for key in ("repositories", "results", "data", "items"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break

    if isinstance(parsed, list):
        items = []
        for value in parsed:
            if not isinstance(value, dict):
                continue
            name = value.get("full_name") or value.get("repo") or value.get("repository") or value.get("name")
            if name:
                items.append((name, value))
    elif isinstance(parsed, dict):
        items = list(parsed.items())
    else:
        return out

    for name, value in items:
        if name not in expected:
            continue

        hint = category_hints.get(name)
        category = None
        description_zh = ""

        if isinstance(value, dict):
            category = value.get("category") or value.get("classification") or value.get("type")
            description_zh = (
                value.get("description_zh")
                or value.get("chinese_description")
                or value.get("description_cn")
                or value.get("summary_zh")
                or value.get("summary_cn")
                or ""
            )
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            category, description_zh = value[0], value[1]
        elif isinstance(value, str):
            # For legacy cached repositories the category is already known, so a
            # simple name->Chinese-description map is sufficient and cheaper.
            if hint in VALID_CATEGORIES:
                category, description_zh = hint, value

        if category not in VALID_CATEGORIES and hint in VALID_CATEGORIES:
            category = hint
        description_zh = str(description_zh or "").strip()
        if category in VALID_CATEGORIES and description_zh:
            out[name] = {"category": category, "description_zh": description_zh}

    return out


'''
if marker in s and "def normalize_ai_response(" not in s:
    s = s.replace(marker, helper + marker, 1)

old = '''    parsed = extract_json_object(content)\n    out = {}\n    expected = {r["full_name"] for r in repos}\n    for name, value in parsed.items():\n        if name not in expected or not isinstance(value, dict):\n            continue\n        category = value.get("category")\n        description_zh = (value.get("description_zh") or "").strip()\n        if category in VALID_CATEGORIES and description_zh:\n            out[name] = {\n                "category": category,\n                "description_zh": description_zh,\n            }\n    return out\n'''
new = '''    parsed = extract_json_object(content)\n    return normalize_ai_response(parsed, repos, category_hints)\n'''
if old in s:
    s = s.replace(old, new, 1)

# 3) If a response parses to zero useful rows, do not pay for an identical full
# retry. Split immediately; partial responses still retry only the missing rows.
old2 = '''        if not missing:\n            return analyzed\n\n        if depth >= AI_MAX_SPLIT_DEPTH:\n'''
new2 = '''        if not missing:\n            return analyzed\n\n        if not analyzed and len(repos) > 1:\n            if depth >= AI_MAX_SPLIT_DEPTH:\n                print(f"{indent}No valid rows after parsing; local fallback will be used")\n                return {}\n            midpoint = len(repos) // 2\n            left, right = repos[:midpoint], repos[midpoint:]\n            print(f"{indent}No valid rows; splitting into {len(left)} + {len(right)} instead of repeating the same request")\n            out = ai_analyze_resilient(left, category_hints, depth + 1)\n            out.update(ai_analyze_resilient(right, category_hints, depth + 1))\n            return out\n\n        if depth >= AI_MAX_SPLIT_DEPTH:\n'''
if old2 in s:
    s = s.replace(old2, new2, 1)

p.write_text(s, encoding="utf-8")
print("Applied SenseNova compatibility patch to scripts/update_stars.py")
