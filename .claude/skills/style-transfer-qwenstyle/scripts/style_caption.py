"""用 Qwen2.5-VL 產生 content / style prompt —— 完全照 QwenStyle 官方 Space 的實作。

來源：https://huggingface.co/spaces/witcherderivia/QwenStyle 的 app.py
Space 用 `pipe.text_encoder`（就是 Qwen-Image-Edit 的 text encoder，即 Qwen2.5-VL）
對兩張輸入圖各跑一次 caption，再把結果用逗號接到固定的 base prompt 後面。

兩句指令一字不改照抄：
  content : describe main objects (fewer than 3) with separated words, ...
  style   : describe only the artistic style, material and stroke in 5 words, not objects.

注意 style 指令結尾的 "not objects." —— 官方把「不要講物件」寫進指令裡。
這跟本專案實測踩到的雷完全一致（prompt 寫 "warm sand" 會被畫成實體沙漠，
見 style_workflow_log.md 教訓 25）。

用法：
    python -X utf8 scripts/style_caption.py --images a.png b.png --kind style
    python -X utf8 scripts/style_caption.py --profile          # 建立/更新快取
"""
import argparse, json, pathlib, sys

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
MODEL_DIR = pathlib.Path(r"D:\models\Qwen2.5-VL-7B-Instruct")
CACHE = SKILL_DIR / "data" / "style_profiles.json"

# —— 官方 Space 的指令，一字不改 ——
CONTENT_INSTRUCTION = ("describe main objects (fewer than 3) with separated words, "
                       "each word is separated by comma,  the total number of words "
                       "is strictly fewer than 3")
STYLE_INSTRUCTION = ("describe only the artistic style, material and stroke in 5 words, "
                     "not objects.")

BASE_PROMPT = ("Style Transfer the style of Figure 2 to Figure 1, "
               "and keep the content and characteristics of Figure 1.")

_model = _proc = None


def _load():
    global _model, _proc
    if _model is not None:
        return
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    if not MODEL_DIR.exists():
        sys.exit(f"找不到 VLM：{MODEL_DIR}。請先下載 Qwen/Qwen2.5-VL-7B-Instruct。")
    _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(MODEL_DIR), dtype=torch.bfloat16, device_map="auto")
    _model.eval()
    _proc = AutoProcessor.from_pretrained(str(MODEL_DIR))


def caption(image_path, instruction, max_new_tokens=1024):
    """照 Space 的流程：apply_chat_template → process_vision_info → generate → decode。"""
    _load()
    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info

    img = Image.open(image_path).convert("RGB")
    messages = [{"role": "user", "content": [{"type": "image", "image": img},
                                             {"type": "text", "text": instruction}]}]
    text = _proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = _proc(text=[text], images=image_inputs, videos=video_inputs,
                   padding=True, return_tensors="pt").to(_model.device)
    with torch.inference_mode():
        gen = _model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
    return _proc.batch_decode(trimmed, skip_special_tokens=True,
                              clean_up_tokenization_spaces=False)[0].strip()


def assemble(base, content_prompt=None, style_prompt=None):
    """照 Space 的組法：逗號串接，content 在前、style 在後。"""
    parts = [base]
    if content_prompt:
        parts.append(content_prompt)
    if style_prompt:
        parts.append(style_prompt)
    return ",".join(parts).strip(",")


def _cache_key(image_path):
    """快取 key：優先用相對於 cwd 的路徑（同專案內可攜），否則用絕對路徑。"""
    p = pathlib.Path(image_path).resolve()
    try:
        return str(p.relative_to(pathlib.Path.cwd())).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"content": {}, "style": {}}


def save_cache(d):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def get(image_path, kind, refresh=False):
    """取得 caption，優先讀快取。kind = content | style"""
    key = _cache_key(image_path)
    cache = load_cache()
    if not refresh and key in cache.get(kind, {}):
        return cache[kind][key]
    instr = CONTENT_INSTRUCTION if kind == "content" else STYLE_INSTRUCTION
    txt = caption(image_path, instr)
    cache.setdefault(kind, {})[key] = txt
    save_cache(cache)
    return txt


def put(image_path, kind, text):
    """人工覆寫 caption。VLM 會看錯——例如把壓縮噪點讀成 pixelated——
    所以 skill 需要一個人工修正的出口。"""
    key = _cache_key(image_path)
    cache = load_cache()
    cache.setdefault(kind, {})[key] = text
    save_cache(cache)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--kind", default="style", choices=["content", "style"])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--set", dest="text", default=None,
                    help="人工覆寫 caption（只能搭配單一 --images）")
    a = ap.parse_args()
    if a.text:
        if len(a.images) != 1:
            sys.exit("--set 只能搭配單一 --images")
        p = pathlib.Path(a.images[0]).resolve()
        put(p, a.kind, a.text)
        print(f"已覆寫 {p.name} 的 {a.kind} caption：\n  → {a.text}")
        return
    for p in a.images:
        p = pathlib.Path(p).resolve()
        txt = get(p, a.kind, a.refresh)
        print(f"{p.name}\n  → {txt}\n")


if __name__ == "__main__":
    main()
