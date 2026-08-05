"""用 Qwen2.5-VL 產生 sref 用的中文編輯指令 —— 對應官方 workflow 裡的 AILab_QwenVL 節點。

官方 workflow（qwen_image_edit_2509_vl_sref.json）用自訂節點 AILab_QwenVL + Qwen3-VL-4B，
把「風格參考圖」和「目標題材字串」餵給 VLM，要它寫出一段以「进行下面的修改：」開頭的
中文編輯指令，再送進 TextEncodeQwenImageEditPlus 當正向 prompt。

本機沒裝那個節點，所以搬到 ComfyUI 外面做。**指令文字逐字照抄官方的兩段 StringConcatenate
（節點 397 + 394）**，一個字都沒改，包含結尾那個孤零零的雙引號。

用法：
    D:/models/qwen_vl_venv/Scripts/python.exe -X utf8 scripts/sref_prompt.py \\
        --style assets/ref.png --target "粉色八爪鱼"
    # 人工覆寫（VLM 寫歪時）
    python -X utf8 scripts/sref_prompt.py --style assets/ref.png --target "粉色八爪鱼" \\
        --set "进行下面的修改：..."
"""
import argparse, json, pathlib, sys

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
MODEL_DIR = pathlib.Path(r"D:\models\Qwen2.5-VL-7B-Instruct")
CACHE = SKILL_DIR / "data" / "sref_prompts.json"

# —— 官方節點 397 + 394 的字串，逐字照抄，不要「順」它 ——
_PREFIX = "使用中文描述这个图片是如何根据这个图片用相同的画风进行编辑得到“"
_SUFFIX = ("”的,不要指出人物的名字或出处或其它猜测，只严格描述进行了哪些在同一画风下的编辑和改变，"
           "注意要将这个照片中与上一张照片中画风相对应的部分进行提及，"
           "对物体取代、色彩变化、整体画风遵循进行对应描述。以'进行下面的修改：'开头\"")

# 官方那段指令是配 Qwen3-VL 調的。本機用 Qwen2.5-VL-7B 時它守不住「只描述同畫風下的編輯」，
# 會自己發明新場景——實測寫出「替换为一个简单的白色背景」「如草地或公园」，出圖直接漂白、
# 原本的隧道綠調全毀（見 research/sref-lora/log.md 教訓 5）。這段是補的護欄，不是官方原文。
_GUARD = ("\n严格遵守以下约束：只替换主体对象，"
          "背景、场景、构图、光源方向、色调、曝光、颗粒质感、锐度、镜头特性全部原样保留；"
          "禁止出现「纯色背景」「白色背景」「更换场景」「还原成自然颜色」这类改动；"
          "禁止新增原图没有的装饰物。每一条都要写明是沿用原图的哪个特征。")


# content 圖 → 文字。實測：sref LoRA 在雙圖模式下**完全忽略 image2**（換三張性質天差地遠的
# 風格圖，輸出統計量一模一樣），裸底模也一樣——雙圖風格轉換的能力只存在於 qwenstyle LoRA。
# 所以走 sref 這條路時，content 只能經由文字進來。
#
# 這段指令刻意**禁止提到畫風**：content 描述裡只要出現材質/色調/筆觸的詞，
# 就會跟風格圖打架，最後兩邊都不像（描述污染）。
_CONTENT_INSTRUCTION = (
    "用中文详细描述这张图片的画面内容：主体是什么、正在做什么、"
    "在画面中的位置与大小、朝向与姿态、背景里有什么、各元素的空间关系。"
    "只描述画面内容与构图，"
    "绝对不要提及画风、笔触、材质、色调、光影、清晰度或任何风格相关的形容。"
    "不要写成条列，用一段连续的文字，200 字以内。")


_model = _proc = None


def build_instruction(target, guard=True):
    """組出餵給 VLM 的指令。target 就是官方 PrimitiveStringMultiline 那格，例如「粉色八爪鱼」。

    guard=False 時是官方逐字原文（做對照實驗用）；預設 True 會多接一段護欄。
    """
    s = _PREFIX + target + _SUFFIX
    return s + _GUARD if guard else s


def _load():
    global _model, _proc
    if _model is not None:
        return
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    if not MODEL_DIR.exists():
        sys.exit(f"找不到 VLM：{MODEL_DIR}")
    _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(MODEL_DIR), dtype=torch.bfloat16, device_map="auto")
    _model.eval()
    _proc = AutoProcessor.from_pretrained(str(MODEL_DIR))


def describe(style_path, target, max_new_tokens=1024, guard=True):
    _load()
    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info

    img = Image.open(style_path).convert("RGB")
    messages = [{"role": "user", "content": [{"type": "image", "image": img},
                                             {"type": "text", "text": build_instruction(target, guard)}]}]
    text = _proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = _proc(text=[text], images=image_inputs, videos=video_inputs,
                   padding=True, return_tensors="pt").to(_model.device)
    with torch.inference_mode():
        gen = _model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
    return _proc.batch_decode(trimmed, skip_special_tokens=True,
                              clean_up_tokenization_spaces=False)[0].strip()


def describe_content(content_path, max_new_tokens=512):
    """看 content 圖，寫出純內容描述（不含任何風格詞），供當作 --target。"""
    _load()
    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info

    img = Image.open(content_path).convert("RGB")
    messages = [{"role": "user", "content": [{"type": "image", "image": img},
                                             {"type": "text", "text": _CONTENT_INSTRUCTION}]}]
    text = _proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ii, vi = process_vision_info(messages)
    inputs = _proc(text=[text], images=ii, videos=vi,
                   padding=True, return_tensors="pt").to(_model.device)
    with torch.inference_mode():
        gen = _model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
    return _proc.batch_decode(trimmed, skip_special_tokens=True,
                              clean_up_tokenization_spaces=False)[0].strip()


def get_content(content_path, refresh=False):
    k = "CONTENT||" + _key(content_path, "")
    c = load_cache()
    if not refresh and k in c:
        return c[k]
    txt = describe_content(content_path)
    c[k] = txt
    save_cache(c)
    return txt


def _key(style_path, target):
    p = pathlib.Path(style_path).resolve()
    try:
        s = str(p.relative_to(pathlib.Path.cwd()))
    except ValueError:
        s = str(p)
    return s.replace("\\", "/") + "||" + target


def load_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save_cache(d):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def get(style_path, target, refresh=False, guard=True):
    k = _key(style_path, target)
    c = load_cache()
    if not refresh and k in c:
        return c[k]
    txt = describe(style_path, target, guard=guard)
    c[k] = txt
    save_cache(c)
    return txt


def put(style_path, target, text):
    c = load_cache()
    c[_key(style_path, target)] = text
    save_cache(c)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--set", dest="text", default=None, help="人工覆寫")
    ap.add_argument("--no-guard", action="store_true", help="用官方逐字原文（對照實驗用）")
    a = ap.parse_args()
    if a.text:
        put(a.style, a.target, a.text)
        print(f"已覆寫 [{pathlib.Path(a.style).name} || {a.target}]")
        return
    print(get(a.style, a.target, a.refresh, guard=not a.no_guard))


if __name__ == "__main__":
    main()
