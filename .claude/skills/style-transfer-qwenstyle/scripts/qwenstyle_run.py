"""QwenStyle V1 執行層 —— content 圖 + style 圖 → 風格轉換。

skill：style-transfer-qwenstyle。把 ComfyUI 做不到的部分（VLM 看圖寫 prompt、
官方 demo 的尺寸規則）包在 workflow 外面，對使用者只暴露「兩張圖」這個介面。
相對路徑以「目前工作目錄」解析；輸出到 <cwd>/output/style_transfer/。

流程（完全對照官方 Space app.py）：
  1. Qwen2.5-VL 看 content 圖 → content prompt（≤3 個詞）
  2. Qwen2.5-VL 看 style 圖   → style prompt（5 個詞，且指令明令 not objects）
  3. 組 prompt：固定句 , content prompt , style prompt
  4. 尺寸：兩張圖都等比例縮到最短邊 = minedge，長邊取 16 的倍數
  5. 送 ComfyUI，輸出尺寸 = content 縮放後的尺寸
  6. 量測並回報

用法：
  python -X utf8 scripts/qwenstyle_run.py --content output/.../s01.png \\
      --styles assets/style_image/style_ref_*.png --tag QS1
  可選：--minedge 1024（風格強度旋鈕）--no-content-prompt --no-style-prompt
"""
import argparse, io, json, math, pathlib, sys, time, urllib.request, uuid

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
HOST = "http://127.0.0.1:8188"
CID = str(uuid.uuid4())
WF = SKILL_DIR / "workflow" / "qwenstyle_v1_2509.json"
OUTDIR = pathlib.Path.cwd() / "output" / "style_transfer"

BASE_PROMPT = ("Style Transfer the style of Figure 2 to Figure 1, "
               "and keep the content and characteristics of Figure 1.")


# ---------- ComfyUI ----------
def _get(p, t=60):
    return json.loads(urllib.request.urlopen(HOST + p, timeout=t).read())


def _post(p, payload, t=60):
    r = urllib.request.Request(HOST + p, data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read())


def upload_bytes(data, name):
    b = "----qs" + uuid.uuid4().hex
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


# ---------- 尺寸：完全照 Space app.py ----------
def fit_minedge(size, minedge):
    """等比例縮到最短邊 = minedge，長邊取 16 的倍數。照 app.py 的算法。"""
    w, h = size
    if w > h:
        r = w / h
        h2 = minedge
        w2 = int(h2 * r) - int(h2 * r) % 16
    else:
        r = h / w
        w2 = minedge
        h2 = int(w2 * r) - int(w2 * r) % 16
    return w2, h2


def prep(path, minedge):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    tgt = fit_minedge(im.size, minedge)
    return im.resize(tgt, Image.LANCZOS), tgt


# ---------- 量測 ----------
def measure(path):
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((256, 256))
    px = list(im.getdata()); n = len(px)
    L = sum(0.299*r + 0.587*g + 0.114*b for r, g, b in px) / n
    WB = sum(r - b for r, g, b in px) / n
    S = sum(0 if max(p) == 0 else (max(p)-min(p))/max(p) for p in px) / n
    return L, WB, S


def content_score(src, out):
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


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--styles", nargs="+", required=True)
    ap.add_argument("--tag", default="QS")
    ap.add_argument("--minedge", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--shift", type=float, default=3.0)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--no-content-prompt", action="store_true")
    ap.add_argument("--no-style-prompt", action="store_true")
    ap.add_argument("--refresh-caption", action="store_true")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--unet", default=None, help="覆寫底模檔名（用來做 2509 vs 2511 對照）")
    ap.add_argument("--lightning", default=None, help="覆寫加速 LoRA 檔名")
    ap.add_argument("--lora", default=None, help="覆寫風格 LoRA 檔名")
    a = ap.parse_args()

    outdir = pathlib.Path(a.outdir) if a.outdir else OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import style_caption as SC

    cpath = pathlib.Path(a.content).resolve()

    # 1) content caption（只需一次）
    content_prompt = ""
    if not a.no_content_prompt:
        content_prompt = SC.get(cpath, "content", a.refresh_caption)
        print(f"content prompt: {content_prompt}")

    wf_base = json.loads(WF.read_text(encoding="utf-8"))
    rows = []
    for spec in a.styles:
        spath = pathlib.Path(spec).resolve()
        if not spath.exists():
            print(f"  ! 找不到 {spath}"); continue

        style_prompt = ""
        if not a.no_style_prompt:
            style_prompt = SC.get(spath, "style", a.refresh_caption)
        prompt = SC.assemble(BASE_PROMPT, content_prompt or None, style_prompt or None)

        cimg, csize = prep(cpath, a.minedge)
        simg, ssize = prep(spath, a.minedge)
        for im, name in ((cimg, "qs_content.png"), (simg, "qs_style.png")):
            b = io.BytesIO(); im.save(b, "PNG"); upload_bytes(b.getvalue(), name)

        wf = {k: v for k, v in wf_base.items() if not k.startswith("_")}
        wf = json.loads(json.dumps(wf))
        wf["11"]["inputs"]["prompt"] = prompt
        wf["3"]["inputs"]["seed"] = a.seed
        wf["3"]["inputs"]["steps"] = a.steps
        wf["66"]["inputs"]["shift"] = a.shift
        wf["76"]["inputs"]["strength_model"] = a.strength
        if a.unet: wf["37"]["inputs"]["unet_name"] = a.unet
        if a.lightning: wf["89"]["inputs"]["lora_name"] = a.lightning
        if a.lora: wf["76"]["inputs"]["lora_name"] = a.lora

        print(f"\n[{spath.stem}] content {csize} / style {ssize}")
        print(f"  style prompt: {style_prompt}")
        try:
            data, secs = run(wf)
        except Exception as e:
            print(f"  ! 失敗: {str(e)[:400]}"); continue

        dst = outdir / f"{a.tag}_{spath.stem}.png"
        dst.write_bytes(data)
        L, W, S = measure(dst); cs = content_score(cpath, dst)
        rL, rW, rS = measure(spath)
        print(f"  參考 L{rL:5.0f} 暖{rW:+5.0f} S{rS:4.2f}")
        print(f"  輸出 L{L:5.0f} 暖{W:+5.0f} S{S:4.2f} | 內容{cs:.3f} | {secs:.0f}s -> {dst.name}")
        rows.append(dict(style=spath.stem, prompt=prompt, L=L, WB=W, S=S,
                         content=cs, secs=secs, ref=(rL, rW, rS)))

    meta = outdir / f"{a.tag}_meta.json"
    meta.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {meta}")


if __name__ == "__main__":
    main()
