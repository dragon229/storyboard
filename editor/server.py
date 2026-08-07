"""分鏡稿編輯器 — 本地後端

左側讀語音稿並切成可選的台詞單位，右側編輯該段落對應的分鏡格。
資料直接讀寫 output/<系列>/<系列>.json，與 scripts/render.py 流程相容。

啟動：
    python editor/server.py
    → http://127.0.0.1:8420
"""
from __future__ import annotations

import io
import json
import re
import shutil
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "source"
OUTPUT_DIR = ROOT / "output"

sys.path.insert(0, str(ROOT / "scripts"))
import compose as C          # noqa: E402
import render as R           # noqa: E402

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
    if not SOURCE_DIR.exists():
        return []
    return sorted(p.name for p in SOURCE_DIR.iterdir()
                  if p.suffix in {".txt", ".md"} and not p.name.startswith("_"))


def list_series() -> list[str]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted(d.name for d in OUTPUT_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("_"))


def sb_path(series: str) -> Path:
    return OUTPUT_DIR / series / f"{series}.json"


def img_dir(series: str, stage: str = "content") -> Path:
    """編輯器操作的是 content image；transfer 是定稿後才跑的第二階段產物，唯讀預覽。"""
    return OUTPUT_DIR / series / "images" / ("transfer" if stage == "transfer" else "content")


def load_scenes(series: str) -> list[dict]:
    p = sb_path(series)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_scenes(series: str, scenes: list[dict]) -> None:
    p = sb_path(series)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(scenes, ensure_ascii=False, indent=1), encoding="utf-8")


def next_scene_id(scenes: list[dict]) -> str:
    nums = [int(m.group(1)) for s in scenes
            if (m := re.match(r"s(\d+)$", s.get("id", "")))]
    return f"s{(max(nums) + 1) if nums else 1:02d}"


def blank_scene(sid: str, src: str, uids: list[int]) -> dict:
    return {
        "id": sid,
        "unit": "",
        "source": src,
        "rhetorical_function": "建立前提",
        "emotional_shift": None,
        "emotion_en": "light everyday curiosity",
        "is_speculation": False,
        "depiction_mode": "實景",
        "framing": {f: None for f in C.FRAMING_FIELDS},
        "staging": "",
        "prompt": "",
        "prompt_manual": False,
        "workflow": "text_only",
        "needs_post_text": False,
        "line_range": sorted(uids),
    }


# ── API ───────────────────────────────────────────────────────────────────


@app.get("/api/bootstrap")
def bootstrap():
    style = C.load_style()
    return {
        "scripts": list_scripts(),
        "series": list_series(),
        "rhetorical_functions": C.RHETORICAL_FUNCTIONS,
        "depiction_modes": C.DEPICTION_MODES,
        "framing_options": C.framing_options(style),
        "framing_fields": C.FRAMING_FIELDS,
        "style_suffix": style["style_suffix"],
    }


@app.get("/api/script")
def get_script(file: str):
    p = SOURCE_DIR / file
    if not p.exists() or p.parent != SOURCE_DIR:
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
    """沒有 line_range 的格，用 source 文字比對回推對應的台詞 uid。"""
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
        p = SOURCE_DIR / script
        if p.exists():
            if backfill_line_range(scenes, split_script(p.read_text(encoding="utf-8"))):
                save_scenes(series, scenes)
    return {"series": series, "scenes": scenes}


class ScenePayload(BaseModel):
    series: str
    scene: dict[str, Any]


@app.post("/api/scene")
def save_scene(payload: ScenePayload):
    sid = payload.scene.get("id")
    if not sid:
        raise HTTPException(400, "缺少 id")
    scenes = load_scenes(payload.series)
    for i, s in enumerate(scenes):
        if s.get("id") == sid:
            scenes[i] = payload.scene
            break
    else:
        scenes.append(payload.scene)
    save_scenes(payload.series, scenes)
    return {"ok": True, "id": sid}


class NewScene(BaseModel):
    series: str
    uids: list[int]
    script_file: str


@app.post("/api/scene/new")
def new_scene(payload: NewScene):
    p = SOURCE_DIR / payload.script_file
    if not p.exists():
        raise HTTPException(404, "找不到語音稿")
    units = split_script(p.read_text(encoding="utf-8"))
    picked = [u for u in units if u["uid"] in set(payload.uids)]
    if not picked:
        raise HTTPException(400, "沒有選到任何台詞")
    scenes = load_scenes(payload.series)
    sc = blank_scene(next_scene_id(scenes),
                     " ".join(u["text"] for u in picked),
                     [u["uid"] for u in picked])
    scenes.append(sc)
    save_scenes(payload.series, scenes)
    return {"ok": True, "scene": sc}


@app.delete("/api/scene")
def delete_scene(series: str, id: str):
    scenes = load_scenes(series)
    kept = [s for s in scenes if s.get("id") != id]
    if len(kept) == len(scenes):
        raise HTTPException(404, "找不到場景")
    save_scenes(series, kept)
    for f in img_dir(series).glob(f"{id}.png"):
        f.unlink()
    return {"ok": True}


# ── 組裝 prompt ───────────────────────────────────────────────────────────


class ComposeReq(BaseModel):
    scene: dict[str, Any]


@app.post("/api/compose")
def compose_one(req: ComposeReq):
    style = C.load_style()
    errs = C.validate_framing(req.scene.get("framing") or {}, style)
    if errs:
        raise HTTPException(400, "；".join(errs))
    return {"ok": True, "prompt": C.compose_prompt(req.scene, style)}


# ── 出圖 ──────────────────────────────────────────────────────────────────

VARIANT_LETTERS = "abcdefgh"


def _prepare(series: str, sid: str) -> tuple[dict, dict]:
    scene = next((s for s in load_scenes(series) if s.get("id") == sid), None)
    if scene is None:
        raise HTTPException(404, "找不到場景")
    if not scene.get("prompt"):
        raise HTTPException(400, "此場景還沒有 prompt")
    try:
        R.check_online()
    except SystemExit as e:
        raise HTTPException(503, str(e)) from e
    style = C.load_style()
    if scene.get("workflow") == "text_with_character":
        R.upload_character(style)
    return scene, style


class GenImgReq(BaseModel):
    series: str
    id: str
    seed: int | None = None


@app.post("/api/generate-image")
def generate_image(req: GenImgReq):
    scene, style = _prepare(req.series, req.id)
    out = img_dir(req.series)
    out.mkdir(parents=True, exist_ok=True)
    seed = req.seed if req.seed is not None else abs(hash(req.id)) % (2 ** 31)
    dest, info = R.run_one(scene, style, seed, out)
    if dest is None:
        return {"ok": False, "note": str(info)}
    return {"ok": True, "updated": True, "seed": seed, "secs": round(info, 1)}


class BatchReq(BaseModel):
    series: str
    id: str
    seed: int | None = None
    count: int = 8


@app.post("/api/batch-generate")
def batch_generate(req: BatchReq):
    scene, style = _prepare(req.series, req.id)
    tmp = img_dir(req.series) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for old in tmp.glob(f"{req.id}_*.png"):
        old.unlink()

    base = req.seed if req.seed is not None else abs(hash(req.id)) % (2 ** 31)
    made, errs = [], []
    for i in range(min(req.count, len(VARIANT_LETTERS))):
        letter = VARIANT_LETTERS[i]
        dest, info = R.run_one(scene, style, (base + i * 7919) % (2 ** 31), tmp,
                               filename=f"{req.id}_{letter}.png")
        if dest:
            made.append(letter)
        else:
            errs.append(f"{letter}: {info}")
    return {"ok": bool(made), "count": len(made), "variants": made,
            "note": "" if made else ("批次生成未產出任何圖：" + "；".join(errs))}


class TransferReq(BaseModel):
    series: str
    id: str
    content_prompt: bool = True


@app.post("/api/transfer-image")
def transfer_image(req: TransferReq):
    """階段 2：把這一格的 content 圖轉成目標畫風，寫進 images/transfer/。

    對應 render.py 的 --transfer-only，但只做單格且一律重做——在編輯器裡按下去
    就是要重轉，跳過已存在的檔案沒有意義。
    """
    scene = next((s for s in load_scenes(req.series) if s.get("id") == req.id), None)
    if scene is None:
        raise HTTPException(404, "找不到場景")
    content_dir = img_dir(req.series)
    if not (content_dir / f"{req.id}.png").exists():
        raise HTTPException(400, "這一格還沒有 content 圖，請先生成圖片")
    try:
        R.check_online()
    except SystemExit as e:
        raise HTTPException(503, str(e)) from e

    transfer_dir = img_dir(req.series, "transfer")
    dest = transfer_dir / f"{req.id}.png"
    before = dest.stat().st_mtime if dest.exists() else 0
    t0 = time.time()
    # run_transfer 只用 print 回報進度，攔下來當成前端的訊息
    buf = io.StringIO()
    with redirect_stdout(buf):
        R.run_transfer([scene], content_dir, transfer_dir, C.load_style(), {req.id},
                       force=True, content_prompt=req.content_prompt)
    log = buf.getvalue().strip()
    ok = dest.exists() and dest.stat().st_mtime > before
    return {"ok": ok, "secs": round(time.time() - t0, 1),
            "log": log[-1200:], "note": "" if ok else (log[-300:] or "風格轉換沒有產出")}


@app.get("/api/tmp-images")
def tmp_images(series: str, id: str):
    tmp = img_dir(series) / "tmp"
    if not tmp.exists():
        return {"variants": []}
    return {"variants": sorted(p.stem.split("_")[-1] for p in tmp.glob(f"{id}_*.png"))}


class PickReq(BaseModel):
    series: str
    id: str
    variant: str


@app.post("/api/pick-image")
def pick_image(req: PickReq):
    src = img_dir(req.series) / "tmp" / f"{req.id}_{req.variant}.png"
    if not src.exists():
        raise HTTPException(404, "找不到該候選圖")
    dst = img_dir(req.series) / f"{req.id}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    for leftover in (img_dir(req.series) / "tmp").glob(f"{req.id}_*.png"):
        leftover.unlink()
    return {"ok": True, "picked": req.variant}


@app.get("/api/image")
def get_image(series: str, id: str, variant: str | None = None, stage: str = "content"):
    # 候選圖只存在於 content/tmp，stage 不影響
    p = (img_dir(series) / "tmp" / f"{id}_{variant}.png") if variant \
        else (img_dir(series, stage) / f"{id}.png")
    if p.exists():
        return FileResponse(p)
    raise HTTPException(404, "還沒有圖片")


# ── 重新編號 ──────────────────────────────────────────────────────────────


class RenumberReq(BaseModel):
    series: str
    script: str
    dry_run: bool = False


@app.post("/api/renumber")
def renumber(req: RenumberReq):
    """依台詞順序重新編號整個系列，JSON 與對應圖片一起改名。"""
    p = SOURCE_DIR / req.script
    if not p.exists():
        raise HTTPException(404, "找不到語音稿")
    scenes = load_scenes(req.series)
    if not scenes:
        raise HTTPException(400, "這個系列沒有分鏡")

    backfill_line_range(scenes, split_script(p.read_text(encoding="utf-8")))
    unlocated = [s["id"] for s in scenes if not s.get("line_range")]
    if unlocated:
        raise HTTPException(400, f"無法定位這些分鏡的台詞位置，請先補上 source：{unlocated}")

    ordered = sorted(scenes, key=lambda s: (s["line_range"][0], -len(s["line_range"]), s["id"]))
    width = max(2, len(str(len(ordered))))
    plan = [(s["id"], f"s{i + 1:0{width}d}") for i, s in enumerate(ordered)]
    changes = [(o, n) for o, n in plan if o != n]
    if req.dry_run:
        return {"ok": True, "total": len(plan), "changed": len(changes), "changes": changes}
    if not changes:
        return {"ok": True, "total": len(plan), "changed": 0, "changes": [],
                "note": "編號已經是正確順序"}

    d = img_dir(req.series)
    tmpd = d / "tmp"

    def targets(sid: str) -> list[Path]:
        out = [d / f"{sid}.png"]
        if tmpd.exists():
            out += list(tmpd.glob(f"{sid}_*.png"))
        return [f for f in out if f.exists()]

    # 兩階段改名：先全部搬到暫存名，避免新舊編號互相覆蓋
    staged: list[tuple[Path, str]] = []
    for old, new in plan:
        for f in targets(old):
            t = f.with_name(f"__renum__{new}{f.name[len(old):]}")
            f.rename(t)
            staged.append((t, new))
    for t, _ in staged:
        t.rename(t.with_name(t.name.replace("__renum__", "", 1)))

    id_map = dict(plan)
    for s in ordered:
        s["id"] = id_map[s["id"]]
    save_scenes(req.series, ordered)
    return {"ok": True, "total": len(plan), "changed": len(changes), "changes": changes}


# ── 產生給 Claude 的指令 ──────────────────────────────────────────────────

TENDENCY = """| 修辭功能 | 首選 | 可用 | 避免 |
| 拋出鉤子 | 實景、細部放大、尺度對照 | 隱喻 | 示意圖 |
| 建立前提 | 示意圖、實景 | 隱喻 | 細部放大 |
| 點出直覺 | 隱喻、示意圖 | 實景 | — |
| 推翻 | 並置、示意圖 | 實景 | — |
| 拆解機制 | 示意圖、隱喻、序列 | — | 實景 |
| 佐證 | 實景、尺度對照 | 並置 | 隱喻 |
| 推進 | 示意圖、序列 | 隱喻 | 實景 |
| 敘事 | 實景、細部放大 | 主持人出鏡 | 示意圖 |
| 收束 | 主持人出鏡、實景、隱喻 | 並置 | 細部放大 |"""


class InstrReq(BaseModel):
    source: str


@app.post("/api/gen-instruction")
def gen_instruction(req: InstrReq):
    """組出一段可貼給 Claude 的指令，要它判讀這一格並回傳決策欄位 JSON。
    不要 Claude 寫 prompt——prompt 由編輯器依 style.json 機械組裝。"""
    opts = C.framing_options(C.load_style())
    fr_lines = "\n".join(
        f"   - {f}：{'／'.join(v)}（用不到就填 null）" for f, v in opts.items())
    instr = f"""你是科普影片分鏡稿的判讀助手。以下是一段語音稿原文，對應「一格分鏡」。
請完成判讀並只輸出一個 JSON。**不要寫 prompt**，那由程式依風格規範自動組裝。

【語音稿原文（唯一輸入）】
{req.source.strip()}

【頻道設定】
・科普／知識型，核心是推演的樂趣，基調輕鬆好奇。
・主持角色叫「觀察者」，定位是**體驗者**——被丟進推演出來的世界裡親自遭遇後果，
  不是站在旁邊解說。
・畫面**絕對不能出現任何文字**（招牌、螢幕內容、標籤、數字都不行），資訊要靠
  顏色／形狀／大小／密度／箭頭方向等視覺編碼承載。

【要產出的欄位】
1. rhetorical_function：{'／'.join(C.RHETORICAL_FUNCTIONS)} 擇一。
   問「這段對觀眾的認知做了什麼」，看上下文而非字面內容。
2. emotional_shift：相對於基調的情緒偏移（中文，大多數格沒有偏移就填 null）。
3. emotion_en：一個簡短英文名詞片語，接在 prompt 尾端。避免把情緒當主語
   （✗ sadness fills the room ✓ a held breath before the answer）。
4. is_speculation：這格畫的是「推測的」還是「確實發生過的」。
   推進＝true；佐證／建立前提／敘事＝false；其餘看內容。標錯會讓觀眾把推測記成事實。
5. depiction_mode：{'／'.join(C.DEPICTION_MODES)} 擇一。依下表選，「避免」欄是硬約束：
{TENDENCY}
   選完再問三題修正：觀眾熟不熟悉這東西（完全陌生→隱喻）？講的是實體還是關係
   （關係→示意圖）？有沒有現成真實案例（有→實景）？
6. framing：取景設計物件，鍵值必須完全來自下列清單：
{fr_lines}
   實景類手法用 shot_size／angle／composition；圖解類再加 layout 等；混合則都填。
   ★景別是用「裁切位置」定義的，直接選鍵名即可。
7. staging：英文，**只寫畫框內容**（主體、動作、空間關係、道具的物理狀態）。
   不要寫風格、不要寫景別視角構圖的詞、不要寫情緒語句。
   ・受景別限制：特寫格不要描述全身姿態或鞋子，否則模型會退回全身景。
   ・不要出現任何數量詞（「一百多顆」會讓模型畫一千顆）；改寫具體排列。
   ・要「很多」時選 3–5 個代表性個體並給差異特徵，規模感交給 emotion_en。
   ・有觀察者時背景必須寫具體（場所＋兩個具體元素＋色調方向），
     否則參考圖的米白素底會滲進來讓整張褪色。
8. workflow：畫面中會出現觀察者就填 "text_with_character"，否則 "text_only"。
9. needs_post_text：真的非要專有名詞（人名、年份、學術詞）才填 true，該格不出圖。

【輸出格式】只輸出一個 JSON 物件，不要 markdown 圍欄、不要任何解釋：
{{"rhetorical_function":"…","emotional_shift":null,"emotion_en":"…","is_speculation":false,\
"depiction_mode":"…","framing":{{"vocabulary":"…","shot_size":"…","angle":"…","composition":"…",\
"layout":null,"info_hierarchy":null,"directionality":null,"contrast_balance":null}},\
"staging":"…","workflow":"text_only","needs_post_text":false}}"""
    return {"instruction": instr}


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    print("分鏡稿編輯器 → http://127.0.0.1:8420")
    uvicorn.run(app, host="127.0.0.1", port=8420, log_level="warning")
