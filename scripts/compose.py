"""提示詞組裝 — storyboard-compose 的機械部分。

編輯器與批次流程共用這一份，避免兩邊各寫一套而漂掉。

組裝順序（見 .claude/skills/storyboard-compose/SKILL.md）：
    [取景句], [場面調度], [推演調性?], [風格尾綴], [色卡?], [情緒語句], [全域禁止]

色卡是可選的：不給就跟以前一模一樣。給了就緊接在風格尾綴後面——
兩者都在講「整張圖長什麼樣」，擺在一起比夾在場面調度中間穩定。
"""
from __future__ import annotations

import json
import pathlib

import palette as P

ROOT = pathlib.Path(__file__).resolve().parent.parent

VOCABULARIES = ["實景", "圖解", "混合"]

RHETORICAL_FUNCTIONS = [
    "拋出鉤子", "建立前提", "點出直覺", "推翻", "拆解機制",
    "佐證", "推進", "敘事", "收束",
]

DEPICTION_MODES = [
    "實景", "隱喻", "示意圖", "並置", "序列", "尺度對照", "主持人出鏡", "細部放大",
]

# framing 欄位 → style.json 裡的對照表名稱。順序即組裝順序。
FRAMING_TABLES = {
    "shot_size": "shot_sizes",
    "angle": "angles",
    "composition": "compositions",
    "layout": "layouts",
    "info_hierarchy": "info_hierarchy",
    "directionality": "directionality",
    "contrast_balance": "contrast_balance",
}

# subject 不是對照表，是逐格自由填的英文主體短語（例 "a bare forearm"）。
# 特寫／近景的景別句含 {subject} 佔位，沒填會被 validate_framing 擋下——
# 這是刻意的：舊版把主體寫死成「臉」，導致非臉主體的特寫格憑空多出一張臉。
FRAMING_FIELDS = ["vocabulary", *FRAMING_TABLES, "subject"]


def load_style() -> dict:
    return json.loads((ROOT / "assets" / "style.json").read_text(encoding="utf-8"))


def _keys(table: dict) -> list[str]:
    """取對照表的鍵，濾掉 `_note` 這類註解欄位。"""
    return [k for k in table if not k.startswith("_")]


def framing_options(style: dict) -> dict:
    """給編輯器用的下拉選項。"""
    opts = {"vocabulary": VOCABULARIES}
    for field, table in FRAMING_TABLES.items():
        opts[field] = _keys(style[table])
    return opts


def validate_framing(framing: dict, style: dict) -> list[str]:
    """回傳錯誤訊息清單；空清單代表通過。"""
    errs = []
    for field, table in FRAMING_TABLES.items():
        v = framing.get(field)
        if v not in (None, "") and v not in _keys(style[table]):
            errs.append(f"framing.{field}='{v}' 不在 style.json 的 {table}")
    voc = framing.get("vocabulary")
    if voc not in (None, "") and voc not in VOCABULARIES:
        errs.append(f"framing.vocabulary='{voc}' 不是 {VOCABULARIES}")
    size = framing.get("shot_size")
    if size and "{subject}" in style["shot_sizes"].get(size, "") \
            and not (framing.get("subject") or "").strip():
        errs.append(
            f"framing.shot_size='{size}' 的景別句需要 framing.subject（英文主體短語，"
            f'例 "a bare forearm"）。不填就會退回舊行為：模型自己補一張臉當主體。')
    return errs


def framing_clause(framing: dict, staging: str, style: dict) -> str:
    """把 framing 的各維度轉成英文取景句。"""
    parts = []
    for field, table in FRAMING_TABLES.items():
        key = framing.get(field)
        if key in (None, ""):
            continue
        txt = style[table][key]
        if "{subject}" in txt:
            txt = txt.replace("{subject}", (framing.get("subject") or "").strip()
                              or "the main subject")
        if "{left|right}" in txt:
            # 讓構圖的左右跟場面調度講的一致
            side = "right" if " right third" in (staging or "") else "left"
            txt = txt.replace("{left|right}", side)
        parts.append(txt)
    return ", ".join(parts)


def load_palette(style: dict, slug: str | None = None) -> dict | None:
    """取這次要用的色卡。slug 優先，其次 style.json 的 palette 欄位，都沒有就 None。"""
    slug = slug or style.get("palette")
    return P.load(slug) if slug else None


def compose_prompt(shot: dict, style: dict, pal: dict | None = None) -> str:
    """依規範組出最終 prompt。pal 給了才加色卡句。"""
    seg = []
    clause = framing_clause(shot.get("framing") or {}, shot.get("staging", ""), style)
    if clause:
        seg.append(clause)
    if shot.get("staging"):
        seg.append(shot["staging"])
    if shot.get("is_speculation"):
        seg.append(style["speculation_clause"]["text"])
    seg.append(style["style_suffix"])
    if pal:
        pc = P.clause(shot, pal)
        if pc:
            seg.append(pc)
    if shot.get("emotion_en"):
        seg.append(shot["emotion_en"])
    seg.append(style["global_bans"]["text"])
    seg.append(style["global_bans"]["frame"])
    return ", ".join(seg)


def recompose(shots: list[dict], style: dict | None = None, force: bool = False,
              pal: dict | None = None) -> int:
    """重算整份分鏡稿的 prompt。預設跳過 prompt_manual=True 的格。回傳更新格數。"""
    style = style or load_style()
    n = 0
    for s in shots:
        if s.get("prompt_manual") and not force:
            continue
        new = compose_prompt(s, style, pal)
        if new != s.get("prompt"):
            s["prompt"] = new
            n += 1
    return n


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="重算某個系列的所有 prompt")
    ap.add_argument("--series", required=True)
    ap.add_argument("--force", action="store_true", help="連手改過的格也一起重算")
    a = ap.parse_args()

    p = ROOT / "output" / a.series / f"{a.series}.json"
    shots = json.loads(p.read_text(encoding="utf-8"))
    st = load_style()
    errs = [f"{s['id']}: {e}" for s in shots for e in validate_framing(s.get("framing") or {}, st)]
    if errs:
        raise SystemExit("取景鍵值驗證失敗：\n  " + "\n  ".join(errs))
    n = recompose(shots, st, force=a.force)
    p.write_text(json.dumps(shots, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"重算 {n} / {len(shots)} 格")
