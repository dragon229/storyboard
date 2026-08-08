"""把角色參考圖重新上色成各組色卡的版本。

    python -X utf8 scripts/character_palette.py [--slug whimsy] [--preview]

為什麼要做這件事：`character_ref.png` 經 ReferenceLatent 掛進正向條件，
鎖的不只是造型，**顏色也一起鎖了**。實測（if_test_2 whimsy 22 格）：
畫面有完整人物的格，線稿一律變回參考圖的黑、毛衣一律變回赭紅 #B25B49，
色卡的線稿色與角色色完全叫不動；只有一隻手的格（s04）或純文字格（s11/s14）
才守得住色卡。既然參考圖會把自己的顏色帶進去，就讓它帶對的顏色進去。

每組色卡出三張，對應三種底（現實／推演／圖解）——參考圖的素底同樣會滲進輸出，
底色不一致的話，圖解格會被參考圖的米白拉淡。哪一格用哪張由分鏡稿資料決定，
規則跟色卡的底色三選一完全相同，見 assets/palette/README.md。

做法不是換色相濾鏡，是**先判每個像素屬於哪一塊填色，再按它相對該塊的明暗上色**
（見 recolour 的註解）。填色精準等於色卡，原圖的深色線自動變成新填色的深色版，
真正的黑線變成色卡的線稿色。造型與線條完全不動。

**皮膚不進色卡**。色卡沒有膚色這個角色鍵，把臉一起換掉角色就不像人了。
臉與手原樣保留。腮紅**移除**（2026-08-07 指定），改成跟臉同色。
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
from PIL import Image, ImageFilter

import palette as P

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "character_ref.png"
OUT_DIR = ROOT / "assets" / "character_ref"

# 三種底對應到色卡的角色鍵。檔名用 ascii，ComfyUI 的 input 名稱不要帶中文。
BG_ROLES = {"real": "現實底", "spec": "推演底", "diagram": "圖解底"}

# 從 character_ref.png 實際取樣出來的錨點。改了參考圖就要重取。
ANCHORS = {
    "bg":       (0xFE, 0xFA, 0xEE),
    "line":     (0x0E, 0x06, 0x02),
    "hair":     (0x39, 0x23, 0x0F),
    "sweater":  (0xB2, 0x5B, 0x49),
    "trousers": (0x95, 0x8C, 0x83),
    "shoes":    (0x7C, 0x4F, 0x21),
    "face":     (0xEE, 0xC0, 0x9E),
    "hand":     (0xF3, 0xC8, 0xA7),
    "blush":    (0xDD, 0x90, 0x7D),
}

# 中值濾波的核大小，用來抹掉細線好判斷「這個像素屬於哪一塊填色」。
# 線最寬 3px，7 夠蓋過去；再大會吃掉眼鏡框這種細部件的身分。
MED = 7
# 亮度降到填色的幾成算「完全是線」。0.35 是照原圖量的：毛衣輪廓 #7B3623 相對毛衣
# 是 0.62、領口羅紋 #87402E 是 0.72、眼鏡與瞳孔的黑相對膚色是 0.05。
S_INK = 0.35


def mix(a: tuple, b: tuple, t: float) -> tuple:
    """a 混向 b，t=0 全 a。"""
    return tuple(x * (1 - t) + y * t for x, y in zip(a, b))


def targets(spec: dict, bg_key: str) -> dict:
    """算出九個錨點各自要變成什麼顏色。"""
    R = {k: P.rgb(v["hex"]) for k, v in spec["roles"].items()}
    bg = R[bg_key]
    dark = P.luminance(spec["roles"][bg_key]["hex"]) < P.DARK_THRESHOLD
    # 線稿**一律用深的那支，深底也不反白**。反白線稿的用途是「深底上的圖解元素」，
    # 但角色本身是淺色塊（膚色、毛衣、褲子），輪廓畫在淺色塊的邊界上而不是畫在底上，
    # 深色線反而看得更清楚。反白的實測結果是眼鏡變白框、瞳孔變白點、髮際一圈白邊雜點，
    # 角色直接不像同一個人。（starfield 的線稿本身就是淺色，那組全片一致，不受影響。）
    line = R["線稿"]
    # 只有「要跟底分開」的填色才需要看底色深淺——深底上褲子得往亮的方向走，否則融進去。
    contrast = R["反白線稿"] if dark else R["線稿"]
    return {
        "bg": bg,
        "line": line,
        # 頭髮跟線稿同一支，混一成八底色，維持原圖裡「頭髮比輪廓淡一階」的階差
        "hair": mix(line, bg, 0.18),
        "sweater": R["角色"],
        # 褲子與鞋不在色卡的角色鍵裡，用對比色與底色調出中性階，不要另外引入色相
        "trousers": mix(contrast, bg, 0.55),
        "shoes": mix(contrast, bg, 0.30),
        # 皮膚原樣保留。臉與手兩個錨點只差 12（#EEC09E / #F3C8A7），同一塊皮膚會被
        # 切成兩半，交界在臉上顯出一條淡邊——正好落在腮紅原本的位置，看起來像沒擦乾淨。
        # 兩者給同一個目標色，交界就不存在了。
        "face": ANCHORS["face"],
        "hand": ANCHORS["face"],
        # 腮紅移除：目標色改成臉，那一塊就平掉了。仍然保留 blush 這個錨點——
        # 拿掉錨點的話腮紅會被判成別的塊（離毛衣與鞋都不遠），變成一團髒色。
        # 移除是 2026-08-07 指定的，`character.json` 的 base_en 也同步拿掉了那一句，
        # 否則參考圖沒有腮紅、prompt 還在要，模型會自己補回來。
        "blush": ANCHORS["face"],
    }


def _luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def recolour(img: Image.Image, tgt: dict) -> Image.Image:
    """換色：先判這個像素屬於哪一塊填色，再按它相對該塊的明暗重新上色。

    **不要用「每個像素找最近的錨點、換成對應目標色」那種做法**（前兩版都是，都壞）。
    原圖的線條大部分**不是黑色，而是同一塊填色的深色版**：毛衣輪廓 #7B3623、
    領口羅紋 #87402E。這兩個顏色離「鞋子」錨點 #7C4F21 只有 25 與 19，離毛衣錨點
    反而有 76——於是整條線被判成鞋子，換色後毛衣的輪廓與羅紋**整條消失**，
    只剩零星暗點。反鋸齒過渡像素也會被夾在中間的錨點劫走，邊緣長出雜點與虛線。

    改成兩件事分開處理：

      **哪一塊** — 拿中值濾波過的圖去分類。中值會把細線換成周圍的填色，所以線上的
      像素會繼承它所在那一塊的身分，不會自成一類。

      **多暗** — 用原圖亮度除以該處填色的亮度，得到一個 0–1 的比值。比值 1 是填色本身，
      越小代表越接近線。輸出 = 目標填色乘上這個比值，再依「有多接近線」往色卡的線稿色
      拉。於是填色精準等於色卡、深色線自動變成新填色的深色版、真正的黑線變成線稿色，
      而且整條連續——沒有任何分類斷點，也就不會斷線。
    """
    keys = list(ANCHORS)
    src = np.array(img.convert("RGB"), dtype=np.float32)
    med = np.array(img.convert("RGB").filter(ImageFilter.MedianFilter(MED)),
                   dtype=np.float32)
    anc = np.array([ANCHORS[k] for k in keys], dtype=np.float32)
    dst = np.array([tgt[k] for k in keys], dtype=np.float32)

    lbl = ((med[:, :, None, :] - anc[None, None, :, :]) ** 2).sum(-1).argmin(-1)
    fill = dst[lbl]                                    # 這一塊換色後該有的填色

    # 相對明暗。分母用中值圖（就地的填色亮度），不用錨點——這樣填色本身有漸層也不會歪。
    s = _luma(src) / np.maximum(_luma(med), 1.0)
    s = np.clip(s, 0.0, 1.2)[:, :, None]

    # 腮紅移除後，原本腮紅與臉的交界仍會留下一圈淡痕——那圈像素的亮度比臉低一點，
    # 相對明暗一算就成了「很淺的線」。把腮紅區（往外擴 3px 涵蓋交界）裡**只有輕微
    # 變暗**的像素拉回填色本身。門檻 0.78 是為了不要動到真正的線：眼鏡框下緣就在
    # 腮紅旁邊，它的比值只有 0.1 左右，碰不到。
    i_blush = keys.index("blush")
    near = np.array(Image.fromarray(((lbl == i_blush) * 255).astype(np.uint8))
                    .filter(ImageFilter.MaxFilter(7)), dtype=np.float32) > 127
    s = np.where((near[:, :, None]) & (s > 0.78), 1.0, s)

    ink = np.array(tgt["line"], dtype=np.float32)
    k = np.clip((1.0 - s) / (1.0 - S_INK), 0.0, 1.0)    # 越暗越靠向線稿色
    out = fill * s * (1.0 - k) + ink * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def main() -> None:
    ap = argparse.ArgumentParser(description="產生各色卡版本的角色參考圖")
    ap.add_argument("--slug", help="只做這一組，預設全部")
    ap.add_argument("--preview", action="store_true",
                    help="另外輸出一張三種底並排的對照圖")
    a = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(SRC)
    for p in sorted((ROOT / "assets" / "palette").glob("*.json")):
        spec = json.loads(p.read_text(encoding="utf-8"))
        if a.slug and spec["slug"] != a.slug:
            continue
        made = []
        for tag, role in BG_ROLES.items():
            out = recolour(img, targets(spec, role))
            dest = OUT_DIR / f"{spec['slug']}_{tag}.png"
            out.save(dest)
            made.append(out)
            print(f"{spec['slug']:<15} {role:<4} -> {dest.relative_to(ROOT)}")
        if a.preview:
            w, h = made[0].size
            sheet = Image.new("RGB", (w * 3, h), "#FFFFFF")
            for i, m in enumerate(made):
                sheet.paste(m, (i * w, 0))
            dest = OUT_DIR / f"_preview_{spec['slug']}.png"
            sheet.resize((w * 3 // 3, h // 3), Image.LANCZOS).save(dest)
            print(f"{'':<15} 預覽 -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
