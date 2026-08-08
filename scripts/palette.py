"""色卡 → prompt 片語。

`assets/palette/*.json` 每組七個角色鍵一致，因此整組抽換不動下游。
哪一格用哪個底、線稿用哪一支，全部由分鏡稿的資料決定，不做逐格美感判斷
（規則見 assets/palette/README.md）：

    is_speculation = true          → 推演底
    framing.vocabulary = 圖解      → 圖解底
    其餘                           → 現實底
    底色暗（luminance < 0.42）     → 反白線稿，否則線稿
    workflow = text_with_character → 加「角色」句
    每格                           → 加一句「高亮」

角色句寫的是主持人的毛衣，畫面上沒有人的格加了只會憑空長出一個人，
所以綁在 workflow 上而不是無條件套。
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAL_DIR = ROOT / "assets" / "palette"

DARK_THRESHOLD = 0.42


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h: str) -> float:
    r, g, b = (c / 255 for c in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def available() -> list[str]:
    return sorted(p.stem for p in PAL_DIR.glob("*.json"))


def load(slug: str) -> dict:
    """依 slug 讀一組色卡。找不到就把可選的列出來，不要讓呼叫端猜。"""
    p = PAL_DIR / f"{slug}.json"
    if not p.exists():
        raise SystemExit(f"找不到色卡 {slug}。可選：{', '.join(available())}")
    return json.loads(p.read_text(encoding="utf-8"))


def background_role(shot: dict) -> str:
    if shot.get("is_speculation"):
        return "推演底"
    if (shot.get("framing") or {}).get("vocabulary") == "圖解":
        return "圖解底"
    return "現實底"


def clause(shot: dict, spec: dict) -> str:
    """組出這一格的色卡句。回傳空字串代表這組色卡缺鍵，呼叫端當作沒色卡。"""
    roles = spec.get("roles") or {}

    def en(key: str) -> str:
        return (roles.get(key) or {}).get("en", "")

    bg_key = background_role(shot)
    bg = en(bg_key)
    if not bg:
        return ""

    dark = luminance(roles[bg_key]["hex"]) < DARK_THRESHOLD
    parts = ["a strict limited flat colour palette", bg,
             en("反白線稿" if dark else "線稿")]
    if shot.get("workflow") == "text_with_character":
        parts.append(en("角色"))
    parts.append(en("高亮"))
    parts.append("every other element kept in flat tints of these same colours")
    return ", ".join(p for p in parts if p)
