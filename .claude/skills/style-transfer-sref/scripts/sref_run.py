"""Sref LoRA 執行層 —— 風格參考圖 + 中文題材詞 → 用該畫風畫出新題材。

skill：style-transfer-sref。對照官方 qwen_image_edit_2509_vl_sref.json 轉寫成 API 呼叫，
並把官方那顆沒裝的 AILab_QwenVL 節點換成 scripts/sref_prompt.py。

流程：
  1. Qwen2.5-VL 看風格圖 + 目標題材 → 中文編輯指令（官方指令逐字照抄）
  2. 圖壓到 1 MP（官方 ImageScaleToTotalPixels），上傳 ComfyUI
  3. sref LoRA + Lightning 4steps，euler/simple/steps4/cfg1/denoise1
  4. 量測並回報

用法：
  python -X utf8 scripts/sref_run.py --styles assets/ref.png --target "粉色八爪鱼" --tag T1
診斷用對照組：
  --no-sref   拿掉 sref LoRA（驗證它到底有沒有生效）
  --no-vlm    不用 VLM，prompt 直接用題材詞（驗證 VLM 那段的貢獻）
"""
import argparse, io, json, math, pathlib, sys, time, urllib.request, uuid

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
HOST = "http://127.0.0.1:8188"
CID = str(uuid.uuid4())
WF = SKILL_DIR / "workflow" / "sref_2509.json"
OUTDIR = pathlib.Path.cwd() / "output" / "sref"

# 雙圖模式必掛的第二顆 LoRA。實測 sref 單掛時 image2 完全無效，見 references。
STACK_LORA = "qwenstyle_v1_2509_diffusers.safetensors"

# 雙圖模式的 prompt。用 QwenStyle 官方 Space 的英文原句——實測中文「图1／图2」措辭
# 效果沒有比較好，而這句是 qwenstyle LoRA 訓練時的措辭，配對才對。
DUAL_PROMPT = ("Style Transfer the style of Figure 2 to Figure 1, "
               "and keep the content and characteristics of Figure 1.")


# ---------- ComfyUI ----------
def _get(p, t=60):
    return json.loads(urllib.request.urlopen(HOST + p, timeout=t).read())


def _post(p, payload, t=60):
    r = urllib.request.Request(HOST + p, data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read())


def upload_bytes(data, name):
    b = "----sref" + uuid.uuid4().hex
    bb = b.encode()
    parts = [b"--" + bb,
             f'Content-Disposition: form-data; name="image"; filename="{name}"'.encode(),
             b"Content-Type: image/png", b"", data,
             b"--" + bb, b'Content-Disposition: form-data; name="overwrite"', b"", b"true",
             b"--" + bb + b"--", b""]
    req = urllib.request.Request(HOST + "/upload/image", data=b"\r\n".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    urllib.request.urlopen(req, timeout=120).read()


def run(wf, timeout=600):
    pid = _post("/prompt", {"prompt": wf, "client_id": CID})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = _get(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st.get("messages", []), ensure_ascii=False)[:1200])
            for _, o in h[pid].get("outputs", {}).items():
                for img in o.get("images", []):
                    q = (f"/view?filename={img['filename']}&subfolder={img.get('subfolder','')}"
                         f"&type={img.get('type','output')}")
                    return urllib.request.urlopen(HOST + q, timeout=120).read(), time.time() - t0
        time.sleep(0.8)
    raise TimeoutError()


# ---------- 量測 ----------
def measure(path):
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((256, 256))
    px = list(im.getdata()); n = len(px)
    L = sum(0.299*r + 0.587*g + 0.114*b for r, g, b in px) / n
    WB = sum(r - b for r, g, b in px) / n
    S = sum(0 if max(p) == 0 else (max(p)-min(p))/max(p) for p in px) / n
    return L, WB, S


def sharpness(path):
    """欠煮偵測：邊緣能量。Lightning LoRA 沒生效時這個值會明顯偏低。"""
    from PIL import Image, ImageFilter
    im = Image.open(path).convert("L").resize((256, 256))
    d = list(im.filter(ImageFilter.FIND_EDGES).getdata())
    m = sum(d) / len(d)
    return math.sqrt(sum((v - m) ** 2 for v in d) / len(d))


def content_score(src, out):
    """跟參考圖的構圖相似度。sref 是『換題材』，這個值**太高反而是壞事**
    （代表沒換成功、只是把參考圖複製一份）。"""
    from PIL import Image, ImageFilter
    def edges(p):
        im = Image.open(p).convert("RGB").resize((192, 192)).convert("L")
        d = list(im.filter(ImageFilter.FIND_EDGES).getdata())
        m = sum(d) / len(d)
        return [v - m for v in d]
    a, b = edges(src), edges(out)
    num = sum(x*y for x, y in zip(a, b))
    da = math.sqrt(sum(x*x for x in a)); db = math.sqrt(sum(y*y for y in b))
    return 0.0 if da == 0 or db == 0 else max(0.0, num/(da*db))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--styles", nargs="+", required=True, help="風格參考圖（可多張，逐張跑）")
    ap.add_argument("--content", default=None,
                    help="內容圖。VLM 先把它描述成文字，再交給 sref 用風格圖的畫風重畫。"
                         "給了就不需要 --target")
    ap.add_argument("--text-bridge", action="store_true",
                    help="改走文字通道：VLM 把 content 圖描述成文字再重畫。"
                         "構圖會失真，只在雙圖模式效果不好時當備案")
    ap.add_argument("--no-stack", action="store_true",
                    help="診斷用：雙圖模式下不疊 qwenstyle LoRA。"
                         "此時 image2 會被完全忽略（等於沒給風格圖）")
    ap.add_argument("--prompt", default=None, help="直接指定 prompt，跳過 VLM")
    ap.add_argument("--target", default=None, help="目標題材，中文短詞，例如「粉色八爪鱼」")
    ap.add_argument("--tag", default="SR")
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--megapixels", type=float, default=1.0)
    ap.add_argument("--shift", type=float, default=3.0)
    ap.add_argument("--strength", type=float, default=1.0, help="sref LoRA 權重")
    ap.add_argument("--lora", default=None, help="換 sref checkpoint（repo 有 250~7000 共 28 顆）")
    ap.add_argument("--extra-lora", default=None,
                    help="在 sref 之後再疊一顆 LoRA（做雙圖時疊 qwenstyle_v1_2509_diffusers 用）")
    ap.add_argument("--extra-strength", type=float, default=1.0)
    ap.add_argument("--lightning", default=None)
    ap.add_argument("--unet", default=None)
    ap.add_argument("--no-sref", action="store_true", help="對照組：拿掉 sref LoRA")
    ap.add_argument("--no-vlm", action="store_true", help="對照組：prompt 只用題材詞")
    ap.add_argument("--no-guard", action="store_true",
                    help="對照組：VLM 指令用官方逐字原文，不加護欄")
    ap.add_argument("--refresh-prompt", action="store_true")
    ap.add_argument("--outdir", default=None)
    a = ap.parse_args()

    outdir = pathlib.Path(a.outdir) if a.outdir else OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import sref_prompt as SP

    wf_base = json.loads(WF.read_text(encoding="utf-8"))
    rows = []
    for spec in a.styles:
        spath = pathlib.Path(spec).resolve()
        if not spath.exists():
            print(f"  ! 找不到 {spath}"); continue

        dual = bool(a.content) and not a.text_bridge
        if a.prompt:
            prompt = a.prompt
        elif dual:
            prompt = DUAL_PROMPT
        elif a.content:
            # content 圖走文字通道：先描述成純內容文字，再當成 target 交給官方那條指令
            target = SP.get_content(a.content, a.refresh_prompt)
            print(f"  content 描述: {target[:120]}{'…' if len(target) > 120 else ''}")
            prompt = SP.get(spath, target, a.refresh_prompt, guard=not a.no_guard)
        elif a.no_vlm:
            prompt = a.target
        else:
            prompt = SP.get(spath, a.target, a.refresh_prompt, guard=not a.no_guard)

        from PIL import Image
        im = Image.open(spath).convert("RGB")
        buf = io.BytesIO(); im.save(buf, "PNG")
        upload_bytes(buf.getvalue(), "sref_style.png")
        if dual:
            cim = Image.open(a.content).convert("RGB")
            cbuf = io.BytesIO(); cim.save(cbuf, "PNG")
            upload_bytes(cbuf.getvalue(), "sref_content.png")

        wf = json.loads(json.dumps({k: v for k, v in wf_base.items() if not k.startswith("_")}))
        for n in wf.values():
            for k in [k for k in n if k.startswith("_")]:
                n.pop(k)
        wf["111"]["inputs"]["prompt"] = prompt
        wf["3"]["inputs"]["seed"] = a.seed
        wf["3"]["inputs"]["steps"] = a.steps
        wf["66"]["inputs"]["shift"] = a.shift
        wf["93"]["inputs"]["megapixels"] = a.megapixels
        wf["389"]["inputs"]["strength_model"] = a.strength
        if a.lora: wf["389"]["inputs"]["lora_name"] = a.lora
        if a.lightning: wf["89"]["inputs"]["lora_name"] = a.lightning
        if a.unet: wf["37"]["inputs"]["unet_name"] = a.unet
        if a.no_sref:                       # 對照組：Lightning 直接吃 UNET
            wf["89"]["inputs"]["model"] = ["37", 0]
            wf.pop("389")
        # 雙圖模式必須疊 qwenstyle LoRA。實測：只掛 sref（甚至完全不掛 LoRA）時
        # image2 被完全忽略——換三張性質天差地遠的風格圖，輸出統計量一模一樣。
        # 雙圖風格轉換的能力只存在於 qwenstyle 這顆 LoRA 裡。
        extra = a.extra_lora or (STACK_LORA if (dual and not a.no_stack) else None)
        if extra:                           # 疊第二顆：插在 sref 與 Lightning 之間
            src = wf["89"]["inputs"]["model"]
            wf["390"] = {"class_type": "LoraLoaderModelOnly",
                         "inputs": {"model": src, "lora_name": extra,
                                    "strength_model": a.extra_strength}}
            wf["89"]["inputs"]["model"] = ["390", 0]
        if dual:
            # 雙圖模式：官方檔的 image2/image3 插槽本來就接好線，只是被 bypass 掉。
            # 這裡把 image1 換成內容圖、image2 接風格圖，latent 改跟內容圖走（決定輸出尺寸）。
            wf["79"] = {"class_type": "LoadImage",
                        "inputs": {"image": "sref_content.png", "upload": "image"}}
            wf["94"] = {"class_type": "ImageScaleToTotalPixels",
                        "inputs": {"image": ["79", 0], "upscale_method": "lanczos",
                                   "megapixels": a.megapixels, "resolution_steps": 1}}
            for n in ("111", "110"):
                wf[n]["inputs"]["image1"] = ["94", 0]
                wf[n]["inputs"]["image2"] = ["93", 0]
            wf["88"]["inputs"]["pixels"] = ["94", 0]

        print(f"\n[{spath.stem}] target={a.target} {im.size}")
        print(f"  prompt: {prompt[:160]}{'…' if len(prompt) > 160 else ''}")
        try:
            data, secs = run(wf)
        except Exception as e:
            print(f"  ! 失敗: {str(e)[:500]}"); continue

        dst = outdir / f"{a.tag}_{spath.stem}.png"
        dst.write_bytes(data)
        L, W, S = measure(dst); rL, rW, rS = measure(spath)
        # 雙圖模式：構圖要跟「內容圖」比（越高越好）；單圖模式跟風格圖比（太高＝沒換題材）
        cmp_src = a.content if a.content else spath
        label = "構圖保留" if a.content else "構圖殘留"
        cs = content_score(cmp_src, dst)
        print(f"  參考 L{rL:5.0f} 暖{rW:+5.0f} S{rS:4.2f}")
        print(f"  輸出 L{L:5.0f} 暖{W:+5.0f} S{S:4.2f} | 銳利{sharpness(dst):5.1f} "
              f"| {label}{cs:.3f} | {secs:.0f}s -> {dst.name}")
        rows.append(dict(style=spath.stem, target=a.target, prompt=prompt, L=L, WB=W, S=S,
                         sharp=sharpness(dst), residual=cs, dual=dual,
                         secs=secs, ref=(rL, rW, rS)))

    meta = outdir / f"{a.tag}_meta.json"
    meta.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {meta}")


if __name__ == "__main__":
    main()
