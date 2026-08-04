"""分鏡稿 → ComfyUI 出圖。

用法:
    python -X utf8 scripts/render.py --series <系列名> [--ids s01,s07] [--seed N] [--no-skip]

讀 storyboard/<系列>.json，依每格的 workflow 欄位分流送件，圖存到 images/<系列>/<id>.png。
"""
import argparse, json, pathlib, sys, time, urllib.request, urllib.error, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOST = "http://127.0.0.1:8188"
CLIENT_ID = str(uuid.uuid4())


def _get(path, timeout=60):
    return json.loads(urllib.request.urlopen(HOST + path, timeout=timeout).read())


def _post_json(path, payload, timeout=60):
    req = urllib.request.Request(
        HOST + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def check_online():
    try:
        _get("/queue", timeout=5)
    except Exception:
        sys.exit("ComfyUI 未在 127.0.0.1:8188 回應。請先啟動 ComfyUI，不要硬跑。")


def upload_character(style):
    """把 assets/character_ref.png 上傳為 ComfyUI input，供參考圖 workflow 使用。"""
    name = style["model"]["character_input_name"]
    src = ROOT / "assets" / "character_ref.png"
    body, boundary = [], "----storyboard" + uuid.uuid4().hex
    bb = boundary.encode()
    body.append(b"--" + bb)
    body.append(f'Content-Disposition: form-data; name="image"; filename="{name}"'.encode())
    body.append(b"Content-Type: image/png")
    body.append(b"")
    body.append(src.read_bytes())
    body.append(b"--" + bb)
    body.append(b'Content-Disposition: form-data; name="overwrite"')
    body.append(b"")
    body.append(b"true")
    body.append(b"--" + bb + b"--")
    body.append(b"")
    data = b"\r\n".join(body)
    req = urllib.request.Request(
        HOST + "/upload/image", data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(req, timeout=60).read()
    print(f"已上傳角色參考圖 -> {name}")


def build(shot, style, seed):
    m = style["model"]
    key = "workflow_with_character" if shot.get("workflow") == "text_with_character" \
        else "workflow_text_only"
    wf = json.loads((ROOT / m[key]).read_text(encoding="utf-8"))

    wf["20"]["inputs"]["text"] = shot["prompt"]
    wf["21"]["inputs"]["text"] = style["negative"]
    wf["43"]["inputs"]["noise_seed"] = seed
    for node in ("40", "41"):
        wf[node]["inputs"]["width"] = m["width"]
        wf[node]["inputs"]["height"] = m["height"]
    wf["41"]["inputs"]["steps"] = m["steps"]
    wf["44"]["inputs"]["cfg"] = m["cfg"]
    wf["42"]["inputs"]["sampler_name"] = m["sampler"]
    if key == "workflow_with_character":
        wf["10"]["inputs"]["image"] = m["character_input_name"]
    return wf


def run_one(shot, style, seed, outdir, filename=None):
    wf = build(shot, style, seed)
    pid = _post_json("/prompt", {"prompt": wf, "client_id": CLIENT_ID})["prompt_id"]

    t0 = time.time()
    while time.time() - t0 < 900:
        hist = _get(f"/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                return None, status.get("messages", [])
            for out in entry.get("outputs", {}).values():
                for img in out.get("images", []):
                    raw = urllib.request.urlopen(
                        f"{HOST}/view?filename={img['filename']}"
                        f"&subfolder={img.get('subfolder','')}&type={img['type']}",
                        timeout=120).read()
                    dest = outdir / (filename or f"{shot['id']}.png")
                    dest.write_bytes(raw)
                    return dest, time.time() - t0
            return None, ["完成但沒有輸出圖片"]
        time.sleep(3)
    return None, ["逾時 900 秒"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--ids", help="只出這幾格，逗號分隔，例 s01,s07")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-skip", action="store_true", help="已存在的圖也重出")
    ap.add_argument("--storyboard", help="分鏡稿路徑，預設 storyboard/<系列>.json")
    ap.add_argument("--outdir", help="圖片輸出目錄，預設 images/<系列>")
    args = ap.parse_args()

    check_online()
    style = json.loads((ROOT / "assets" / "style.json").read_text(encoding="utf-8"))
    sb = pathlib.Path(args.storyboard) if args.storyboard \
        else ROOT / "output" / args.series / f"{args.series}.json"
    shots = json.loads(sb.read_text(encoding="utf-8"))

    outdir = pathlib.Path(args.outdir) if args.outdir \
        else ROOT / "output" / args.series / "images"
    outdir.mkdir(parents=True, exist_ok=True)

    wanted = set(args.ids.split(",")) if args.ids else None
    if any(s.get("workflow") == "text_with_character" for s in shots):
        upload_character(style)

    done = failed = skipped = 0
    for shot in shots:
        sid = shot["id"]
        if wanted and sid not in wanted:
            continue
        if shot.get("needs_post_text"):
            print(f"{sid}  跳過（needs_post_text，交後製）")
            skipped += 1
            continue
        if not shot.get("prompt"):
            print(f"{sid}  跳過（無 prompt，請先跑 storyboard-compose）")
            skipped += 1
            continue
        if (outdir / f"{sid}.png").exists() and not args.no_skip:
            print(f"{sid}  跳過（圖已存在）")
            skipped += 1
            continue

        seed = args.seed if args.seed else abs(hash(sid)) % (2 ** 31)
        dest, info = run_one(shot, style, seed, outdir)
        if dest:
            print(f"{sid}  OK  {info:.1f}s  seed={seed}  -> {dest.name}")
            done += 1
        else:
            print(f"{sid}  失敗: {info}")
            failed += 1

    print(f"\n完成 {done} / 失敗 {failed} / 跳過 {skipped}")


if __name__ == "__main__":
    main()
