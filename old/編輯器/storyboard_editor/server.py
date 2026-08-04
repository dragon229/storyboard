"""分鏡稿互動編輯器 — 本地後端

左側讀語音稿並切成可選的台詞單位，右側編輯該段落對應的分鏡提示詞。
資料直接讀寫 json/<系列>/sNN.json，與現行 generate.py 流程相容。

啟動：
    python storyboard_editor/server.py
    → http://127.0.0.1:8420
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent  # D:\Cowork\分鏡稿
HERE = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"
SPEC_SLIM = ROOT / "分鏡稿規範_slim.json"

app = FastAPI(title="分鏡稿編輯器")


# ── 台詞切分 ──────────────────────────────────────────────────────────────

# 在句末標點後切，但連續標點（！？）與其後的收尾引號不切開
_SENT_END = re.compile(r"(?<=[。！？!?])(?![。！？!?」』）\)])")


def split_script(text: str) -> list[dict]:
    """把語音稿切成台詞單位。段落用空行分隔，段落內再依句末標點切句。"""
    units: list[dict] = []
    uid = 0
    for p_idx, para in enumerate(text.split("\n\n")):
        para = para.strip()
        if not para:
            continue
        # 段落內先移除單純換行
        para_text = " ".join(l.strip() for l in para.splitlines() if l.strip())
        for sent in _SENT_END.split(para_text):
            sent = sent.strip()
            if not sent:
                continue
            units.append({"uid": uid, "para": p_idx, "text": sent})
            uid += 1
    return units


# ── 檔案存取 ──────────────────────────────────────────────────────────────


def list_scripts() -> list[str]:
    out = []
    for p in sorted(ROOT.glob("*.txt")) + sorted(ROOT.glob("*.md")):
        if p.name.startswith("_") or p.name in {"CLAUDE.md"}:
            continue
        out.append(p.name)
    return out


def list_series() -> list[str]:
    if not JSON_DIR.exists():
        return []
    return sorted(d.name for d in JSON_DIR.iterdir() if d.is_dir() and not d.name.startswith("_"))


def list_image_dirs() -> list[str]:
    """列出所有 images_* 圖片資料夾。"""
    return sorted(d.name for d in ROOT.iterdir() if d.is_dir() and d.name.startswith("images_"))


def scene_files(series: str) -> list[Path]:
    d = JSON_DIR / series
    if not d.exists():
        return []
    return sorted(d.glob("s*.json"), key=lambda p: p.stem)


def load_scenes(series: str) -> list[dict]:
    out = []
    for f in scene_files(series):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def next_scene_id(series: str) -> str:
    nums = []
    for f in scene_files(series):
        m = re.match(r"s(\d+)", f.stem)
        if m:
            nums.append(int(m.group(1)))
    return f"s{(max(nums) + 1) if nums else 1:02d}"


# ── 風格規範（自動生成 prompt 用） ─────────────────────────────────────────

STYLE_PREFIX = (
    "vintage retro science illustration, mid-century educational illustration style, "
    "clean flat color shading with subtle paper-grain texture, bold clear hand-drawn linework, "
    "warm saturated color palette, bright even daylight lighting, 16:9 aspect ratio"
)

NO_TEXT_TAIL = (
    "absolutely no text anywhere in the image, no letters, no words, no numbers, "
    "no titles, no headlines, no captions, no labels, no signage, no typography, "
    "no writing, no handwriting, no inscriptions, "
    "no letterboxing, no black bars, full bleed 16:9 frame"
)

SHOT_PRESETS = {
    "物件焦點": "close-up, eye-level, centered symmetrical framing",
    "人物焦點": "medium close-up, eye-level, rule-of-thirds framing",
    "動作焦點": "medium shot, eye-level, diagonal composition",
    "環境焦點": "wide establishing shot, eye-level, single-point perspective",
    "關係焦點": "medium shot two-shot, eye-level, subjects split left and right",
    "對比焦點": "wide shot, eye-level, bilateral split composition",
    "細節焦點": "extreme close-up, front-facing angle, detail filling the frame",
}


# ── API ───────────────────────────────────────────────────────────────────


@app.get("/api/bootstrap")
def bootstrap():
    return {
        "scripts": list_scripts(),
        "series": list_series(),
        "image_dirs": list_image_dirs(),
        "focus_types": list(SHOT_PRESETS.keys()),
        "style_prefix": STYLE_PREFIX,
        "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.get("/api/script")
def get_script(file: str):
    p = ROOT / file
    if not p.exists() or p.parent != ROOT:
        raise HTTPException(404, "找不到語音稿")
    return {"file": file, "units": split_script(p.read_text(encoding="utf-8"))}


def _longest_run(nums: list[int], max_gap: int = 2) -> list[int]:
    """取最長的連續（容許小間隔）區段，濾掉零星誤匹配。"""
    if not nums:
        return []
    runs, cur = [], [nums[0]]
    for a, b in zip(nums, nums[1:]):
        if b - a <= max_gap:
            cur.append(b)
        else:
            runs.append(cur)
            cur = [b]
    runs.append(cur)
    return max(runs, key=len)


def backfill_line_range(scenes: list[dict], units: list[dict]) -> int:
    """舊系列的場景沒有 line_range，用 source 文字比對回推對應的台詞 uid。
    短句（如單獨的標點）會誤匹配，故設下限；再取最長連續區段濾掉離群值。"""
    filled = 0
    for sc in scenes:
        if sc.get("line_range"):
            continue
        src = re.sub(r"\s+", "", sc.get("source", "") or "")
        if not src:
            continue
        hits = sorted(
            u["uid"] for u in units
            if len(re.sub(r"\s+", "", u["text"])) >= 5
            and re.sub(r"\s+", "", u["text"]) in src
        )
        run = _longest_run(hits)
        if run:
            sc["line_range"] = list(range(run[0], run[-1] + 1))
            filled += 1
    return filled


@app.get("/api/scenes")
def get_scenes(series: str, script: str | None = None):
    scenes = load_scenes(series)
    if script:
        p = ROOT / script
        if p.exists():
            backfill_line_range(scenes, split_script(p.read_text(encoding="utf-8")))
    return {"series": series, "scenes": scenes}


class ScenePayload(BaseModel):
    series: str
    scene: dict[str, Any]


@app.post("/api/scene")
def save_scene(payload: ScenePayload):
    series = payload.series
    scene = payload.scene
    sid = scene.get("id")
    if not sid:
        raise HTTPException(400, "缺少 id")
    d = JSON_DIR / series
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text(
        json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "id": sid}


class NewScene(BaseModel):
    series: str
    uids: list[int]
    script_file: str
    focus_type: str = "環境焦點"


@app.post("/api/scene/new")
def new_scene(payload: NewScene):
    p = ROOT / payload.script_file
    if not p.exists():
        raise HTTPException(404, "找不到語音稿")
    units = split_script(p.read_text(encoding="utf-8"))
    picked = [u for u in units if u["uid"] in set(payload.uids)]
    if not picked:
        raise HTTPException(400, "沒有選到任何台詞")
    src = " ".join(u["text"] for u in picked)
    sid = next_scene_id(payload.series)
    scene = {
        "id": sid,
        "scene": "",
        "dialogue": picked[0]["text"],
        "source": src,
        "focus_hint": f"{payload.focus_type}：",
        "location": "",
        "no_characters": False,
        "ref_character": None,
        "prompt": "",
        "claims": [],
        "line_range": sorted(u["uid"] for u in picked),
    }
    (JSON_DIR / payload.series).mkdir(parents=True, exist_ok=True)
    (JSON_DIR / payload.series / f"{sid}.json").write_text(
        json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "scene": scene}


@app.delete("/api/scene")
def delete_scene(series: str, id: str):
    f = JSON_DIR / series / f"{id}.json"
    if f.exists():
        f.unlink()
        return {"ok": True}
    raise HTTPException(404, "找不到場景")


class GenReq(BaseModel):
    source: str
    focus_hint: str = ""
    location: str = ""
    focus_type: str = "環境焦點"
    no_characters: bool = False


@app.post("/api/generate-prompt")
def generate_prompt(req: GenReq):
    """自動生成 prompt。有 ANTHROPIC_API_KEY 時呼叫 Claude，否則回傳模板骨架。"""
    shot = SHOT_PRESETS.get(req.focus_type, SHOT_PRESETS["環境焦點"])

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            body = _llm_scene_body(req, shot)
            prompt = f"{STYLE_PREFIX} — {shot} — {body}, {NO_TEXT_TAIL}"
            if req.no_characters:
                prompt = prompt.replace(", " + NO_TEXT_TAIL, f", no people visible, {NO_TEXT_TAIL}")
            return {"ok": True, "prompt": prompt, "body": body, "source_mode": "llm"}
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"LLM 呼叫失敗：{e}",
                "prompt": _template_prompt(req, shot),
                "source_mode": "template",
            }

    return {
        "ok": True,
        "prompt": _template_prompt(req, shot),
        "source_mode": "template",
        "note": "未設定 ANTHROPIC_API_KEY，回傳模板骨架；請手動補寫場景描述。",
    }


def _template_prompt(req: GenReq, shot: str) -> str:
    hint = req.focus_hint.split("：", 1)[-1].strip() or "（在此描述畫面焦點）"
    loc = f", {req.location}" if req.location else ""
    body = f"[{hint}]{loc}"
    tail = NO_TEXT_TAIL
    if req.no_characters:
        tail = "no people visible, " + tail
    return f"{STYLE_PREFIX} — {shot} — {body}, {tail}"


def _llm_scene_body(req: GenReq, shot: str) -> str:
    """呼叫 Claude 產生場景描述本體（不含 style 前綴與排除語句）。"""
    import anthropic  # 延遲載入

    spec_note = ""
    if SPEC_SLIM.exists():
        spec_note = "\n\n（本系列不使用喪屍/軍事設定，忽略規範檔中的世界觀、供電、喪屍相關 block。）"

    sys_prompt = (
        "你是分鏡稿提示詞撰寫專員。根據給定的語音稿段落，寫出一段**英文場景描述**，"
        "用於 AI 生圖。只輸出場景描述本體，不要加風格前綴、不要加景別詞、不要加排除文字的語句、"
        "不要任何解釋或引號。\n\n"
        "規則：\n"
        "1. 一個畫面只聚焦一件最重要的事，砍掉次要元素。\n"
        "2. 具體可畫：用具象的視覺描述，避免抽象概念當主體。\n"
        "3. 結尾加一個簡短的情緒語句（名詞片語）。\n"
        "4. 畫面中不可出現任何文字、標籤、招牌——描述時不要要求任何文字元素。\n"
        "5. 若場景需要人物，用 (other character) 標記，不寫細節外觀。\n"
        + spec_note
    )

    user = f"""語音稿段落：
{req.source}

焦點類型：{req.focus_type}
焦點提示：{req.focus_hint or "（未指定，請自行判斷最該讓觀眾看到什麼）"}
地點：{req.location or "（未指定，請從段落推斷）"}
景別已定為：{shot}

請輸出英文場景描述本體。"""

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=600,
        system=sys_prompt,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


class InstrReq(BaseModel):
    source: str


@app.post("/api/gen-instruction")
def gen_instruction(req: InstrReq):
    """組出一段可貼給 Claude 的指令：輸入只有語音稿原文，
    要 Claude 執行『階段一切分 + 階段二寫提示詞』並回傳 6 欄位 JSON。
    規則與風格常數與現行 skill 流程一致。"""
    shot_lines = "\n".join(f"     - {k} → {v}" for k, v in SHOT_PRESETS.items())
    instr = f"""你是分鏡稿生成助手。以下是一支科普影片「如果魔法真的存在」的一段語音稿台詞。\
請把它轉成「一格分鏡場景」，完成切分判斷與英文生圖提示詞，最後只輸出一個 JSON。

【語音稿原文（唯一輸入）】
{req.source.strip()}

【要產出的欄位】
1. scene：中文短標題，格式「主題｜事件」，點出這格畫面的重點。
2. location：畫面地點（中文，務必點出室內/室外＋場所類型；原文沒明講就從語意合理推斷，不可留空）。
3. focus_hint：格式「焦點類型：一句話說明要讓觀眾看到什麼」。焦點類型從下列七種擇一：
   物件焦點 / 人物焦點 / 動作焦點 / 環境焦點 / 關係焦點 / 對比焦點 / 細節焦點。
4. dialogue：從原文挑一句最能代表這個畫面的關鍵台詞。
5. no_characters：畫面裡若沒有人物（物件、環境、自然現象等焦點）設 true；有人物設 false。
6. prompt：完整英文生圖提示詞，務必嚴格照下列格式與規則：

   格式：
   {STYLE_PREFIX} — [景別+視角+構圖] — [英文場景描述], [情緒語句], {NO_TEXT_TAIL}

   規則：
   - [景別+視角+構圖] 依 focus_hint 的焦點類型，直接套用：
{shot_lines}
   - [英文場景描述]：一個畫面只聚焦一件最重要的事，具體可畫，砍掉次要元素；主動避免任何文字/招牌/標籤/數字出現在畫面裡（用視覺表達，不要要求任何文字元素）。
   - 若 no_characters=true，在場景描述後補一句 "no people visible"。
   - 若畫面需要人物，一律用 (other character) 標記，不寫細節外觀。
   - 題材是科普／奇幻／歷史，不是喪屍或軍事，切勿套用末日/軍事描述。
   - 風格：復古科普插畫、溫暖飽和明亮、中景為主穩定平視（除非對比/分割畫面需要其他景別）。

【輸出格式】只輸出一個 JSON 物件，不要 markdown 圍欄、不要任何解釋文字：
{{"scene":"…","location":"…","focus_hint":"…","dialogue":"…","no_characters":true,"prompt":"…"}}"""
    return {"instruction": instr}


class GenImgReq(BaseModel):
    series: str
    id: str
    seed: int | None = None
    image_dir: str | None = None


@app.post("/api/generate-image")
def generate_image(req: GenImgReq):
    """呼叫 generate.py 生成單張圖片。"""
    f = JSON_DIR / req.series / f"{req.id}.json"
    if not f.exists():
        raise HTTPException(404, "找不到場景")
    scene = json.loads(f.read_text(encoding="utf-8"))
    if not scene.get("prompt"):
        raise HTTPException(400, "此場景還沒有 prompt")

    tmp = JSON_DIR / f"_editor_{req.id}.json"
    tmp.write_text(json.dumps([scene], ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        sys.executable, "generate.py",
        "--input", str(tmp.relative_to(ROOT)),
        "--output", req.image_dir or f"images_{req.series}",
        "--variants", "1", "--no-skip",
        "--workflow", "image_flux2_text_to_image_9b",
    ]
    if req.seed is not None:
        cmd += ["--seed", str(req.seed)]

    # 記下生成前的圖檔狀態，用來判斷是否真的產出新圖
    out_png = ROOT / (req.image_dir or f"images_{req.series}") / f"{req.id}_a.png"
    before = out_png.stat().st_mtime if out_png.exists() else None

    # Windows 預設以 cp950 解碼子行程輸出，遇中文會拋 UnicodeDecodeError
    # 導致 proc.stdout 變成 None，故強制 utf-8 並容錯
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)

    # generate.py 逾時跳過時仍會 exit 0，故以圖檔是否更新為準
    after = out_png.stat().st_mtime if out_png.exists() else None
    updated = after is not None and after != before
    ok = proc.returncode == 0 and updated
    note = "" if ok else ("生成未產出新圖（ComfyUI 可能逾時或佇列卡住）" if proc.returncode == 0
                          else "generate.py 執行失敗")
    return {"ok": ok, "updated": updated, "note": note,
            "stdout": (proc.stdout or "")[-2000:], "stderr": (proc.stderr or "")[-1000:]}


class RenumberReq(BaseModel):
    series: str
    script: str
    dry_run: bool = False


@app.post("/api/renumber")
def renumber(req: RenumberReq):
    """依台詞順序重新編號整個系列，JSON 與對應圖片一起改名。"""
    p = ROOT / req.script
    if not p.exists():
        raise HTTPException(404, "找不到語音稿")
    scenes = load_scenes(req.series)
    if not scenes:
        raise HTTPException(400, "這個系列沒有分鏡")

    units = split_script(p.read_text(encoding="utf-8"))
    backfill_line_range(scenes, units)          # 先補齊排序依據
    unlocated = [s["id"] for s in scenes if not s.get("line_range")]
    if unlocated:
        raise HTTPException(400, f"無法定位這些分鏡的台詞位置，請先補上 source：{unlocated}")

    # 依台詞起始位置排序，起點相同時涵蓋較多句的排前面
    ordered = sorted(scenes, key=lambda s: (s["line_range"][0], -len(s["line_range"]), s["id"]))
    width = max(2, len(str(len(ordered))))
    plan = [(s["id"], f"s{i+1:0{width}d}") for i, s in enumerate(ordered)]
    changes = [(o, n) for o, n in plan if o != n]
    if req.dry_run:
        return {"ok": True, "total": len(plan), "changed": len(changes), "changes": changes}
    if not changes:
        return {"ok": True, "total": len(plan), "changed": 0, "changes": [], "note": "編號已經是正確順序"}

    json_dir = JSON_DIR / req.series
    img_dirs = [ROOT / d for d in list_image_dirs() if d.startswith(f"images_{req.series}")]

    def targets(sid: str) -> list[Path]:
        """這個編號對應到的所有檔案：JSON、各資料夾正式圖、tmp 候選圖。"""
        out = [json_dir / f"{sid}.json"]
        for d in img_dirs:
            out += list(d.glob(f"{sid}_*.png"))
            out += list((d / "tmp").glob(f"{sid}_*.png")) if (d / "tmp").exists() else []
        return [f for f in out if f.exists()]

    # 兩階段改名：先全部搬到暫存名，避免新舊編號互相覆蓋
    staged: list[tuple[Path, str]] = []
    for old, new in plan:
        for f in targets(old):
            tmp = f.with_name(f"__renum__{new}{f.name[len(old):]}")
            f.rename(tmp)
            staged.append((tmp, new))
    for tmp, new in staged:
        tmp.rename(tmp.with_name(tmp.name.replace("__renum__", "", 1)))

    # 更新每個 JSON 內的 id 欄位
    for _, new in plan:
        jf = json_dir / f"{new}.json"
        if jf.exists():
            data = json.loads(jf.read_text(encoding="utf-8"))
            data["id"] = new
            jf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"ok": True, "total": len(plan), "changed": len(changes), "changes": changes}


class BatchReq(BaseModel):
    series: str
    id: str
    image_dir: str | None = None
    seed: int | None = None


@app.post("/api/batch-generate")
def batch_generate(req: BatchReq):
    """一次生成 8 張候選圖到 <image_dir>/tmp/，供挑選。"""
    f = JSON_DIR / req.series / f"{req.id}.json"
    if not f.exists():
        raise HTTPException(404, "找不到場景")
    scene = json.loads(f.read_text(encoding="utf-8"))
    if not scene.get("prompt"):
        raise HTTPException(400, "此場景還沒有 prompt")

    base = req.image_dir or f"images_{req.series}"
    tmp_dir = ROOT / base / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # 清掉這一格的舊候選，避免跟本次結果混在一起
    for old in tmp_dir.glob(f"{req.id}_*.png"):
        old.unlink()

    tmp_json = JSON_DIR / f"_editor_{req.id}.json"
    tmp_json.write_text(json.dumps([scene], ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        sys.executable, "generate.py",
        "--input", str(tmp_json.relative_to(ROOT)),
        "--output", f"{base}/tmp",
        "--variants", "8", "--no-skip",
        "--workflow", "image_flux2_text_to_image_9b",
    ]
    if req.seed is not None:
        cmd += ["--seed", str(req.seed)]

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1800)
    made = sorted(p.name for p in tmp_dir.glob(f"{req.id}_*.png"))
    variants = [p.split("_")[-1].removesuffix(".png") for p in made]
    return {"ok": bool(made), "count": len(made), "variants": variants,
            "note": "" if made else "批次生成未產出任何圖（ComfyUI 可能逾時或佇列卡住）",
            "stdout": (proc.stdout or "")[-2000:], "stderr": (proc.stderr or "")[-1000:]}


@app.get("/api/tmp-images")
def tmp_images(series: str, id: str, image_dir: str | None = None):
    """列出某一格目前在 tmp 裡的候選圖標籤。"""
    base = image_dir or f"images_{series}"
    tmp_dir = ROOT / base / "tmp"
    if not tmp_dir.exists():
        return {"variants": []}
    made = sorted(p.name for p in tmp_dir.glob(f"{id}_*.png"))
    return {"variants": [p.split("_")[-1].removesuffix(".png") for p in made]}


class PickReq(BaseModel):
    series: str
    id: str
    variant: str
    image_dir: str | None = None


@app.post("/api/pick-image")
def pick_image(req: PickReq):
    """把選定的候選圖搬成正式圖 <image_dir>/<id>_a.png，並清掉其餘候選。"""
    base = req.image_dir or f"images_{req.series}"
    src = ROOT / base / "tmp" / f"{req.id}_{req.variant}.png"
    if not src.exists():
        raise HTTPException(404, "找不到該候選圖")
    dst = ROOT / base / f"{req.id}_a.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    for leftover in (ROOT / base / "tmp").glob(f"{req.id}_*.png"):
        leftover.unlink()
    return {"ok": True, "picked": req.variant}


@app.get("/api/image")
def get_image(series: str, id: str, image_dir: str | None = None,
              variant: str = "a", sub: str | None = None):
    if image_dir:
        p = ROOT / image_dir / (sub or "") / f"{id}_{variant}.png"
        if p.exists():
            return FileResponse(p)
        raise HTTPException(404, "還沒有圖片")
    for folder in (f"images_{series}", f"images_{series}_flux2"):
        p = ROOT / folder / f"{id}_a.png"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "還沒有圖片")


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    print("分鏡稿編輯器 → http://127.0.0.1:8420")
    uvicorn.run(app, host="127.0.0.1", port=8420, log_level="warning")
