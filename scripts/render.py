"""分鏡稿 → ComfyUI 出圖，兩個階段。

階段 1  生成 content image：依每格 workflow 欄位分流送件 → images/content/<id>.png
階段 2  統一畫風：呼叫 style-transfer-qwenstyle skill      → images/transfer/<id>.png

用法:
    python -X utf8 scripts/render.py --series <系列名> [--ids s01,s07] [--seed N] [--no-skip]
    python -X utf8 scripts/render.py --series <系列名> --no-transfer     # 只跑階段 1
    python -X utf8 scripts/render.py --series <系列名> --transfer-only   # 圖已出好，只轉風格

**階段 2 預設開啟**（style.json 的 style_ref 留空時會自動略過）。
兩個階段刻意分開跑完（不逐格交錯）——flux2 與 Qwen-Image-Edit 不能同時待在 VRAM 裡，
交錯等於每格換兩次模型。

兩份產物並存：content 是原圖（可換風格重轉、轉壞時回頭比對），transfer 是交付品。
"""
import argparse, hashlib, json, pathlib, sys, time, urllib.request, urllib.error, uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import compose as C     # noqa: E402  色卡要在出圖前把 prompt 重組一次
import palette as P     # noqa: E402

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


def upload_character(style, src=None, name=None):
    """把角色參考圖上傳為 ComfyUI input，供參考圖 workflow 使用。"""
    name = name or style["model"]["character_input_name"]
    src = src or ROOT / "assets" / "character_ref.png"
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
    print(f"已上傳角色參考圖 {pathlib.Path(src).name} -> {name}")


def character_inputs(pal):
    """指定色卡時，準備三張對應該色卡的參考圖，回傳 {底色角色鍵: ComfyUI input 名稱}。

    參考圖的顏色會經 ReferenceLatent 一起帶進輸出（實測：線稿與毛衣色完全由它決定），
    所以色卡換了，參考圖也要跟著換，否則畫面上有人的格永遠守不住色卡。
    素底同理——圖解格配米白素底的參考圖會被拉淡，所以三種底各一張。
    """
    if not pal:
        return None
    import character_palette as CP
    out = {}
    for tag, role in CP.BG_ROLES.items():
        src = CP.OUT_DIR / f"{pal['slug']}_{tag}.png"
        if not src.exists():
            sys.exit(f"找不到 {src}。請先跑：\n"
                     f"  python -X utf8 scripts/character_palette.py --slug {pal['slug']}")
        out[role] = f"input_character_{tag}.png"
    return out


def build(shot, style, seed, char_inputs=None):
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
        # 用色卡時依這一格的底色挑參考圖，規則跟色卡選底色完全同一條
        wf["10"]["inputs"]["image"] = m["character_input_name"] if not char_inputs \
            else char_inputs[P.background_role(shot)]
    return wf


def run_one(shot, style, seed, outdir, filename=None, char_inputs=None):
    wf = build(shot, style, seed, char_inputs)
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


SKILL_DIR = ROOT / ".claude" / "skills" / "style-transfer-qwenstyle"
VLM_PYTHON = pathlib.Path(r"D:\models\qwen_vl_venv\Scripts\python.exe")


def ensure_content_captions(paths):
    """content caption 是內容保留的主要錨點，缺了會讓輸出退化成 style 圖的複製品。

    caption 必須用 VLM venv 產生（系統 python 的 transformers 太舊載不動 VLM），
    但真正跑轉換的 qwenstyle_run.py 是系統 python——所以在這裡先一次補齊快取，
    後面每格才拿得到。回傳 False 代表補不了，呼叫端應中止。
    """
    def key(p):
        """跟 style_caption._cache_key 同規則，但基準固定在 ROOT。

        原本用 cwd，於是「誰的 cwd」決定了 key——編輯器 server 從別的目錄啟動時，
        這裡算出的 key 跟 qwenstyle_run 查的 key 不同，快取永遠 miss，
        子行程只好自己載 VLM，用系統 python 直接 ImportError。
        兩邊都釘死在 ROOT（子行程也帶 cwd=ROOT）才會對得上。
        """
        p = pathlib.Path(p).resolve()
        try:
            return p.relative_to(ROOT).as_posix()
        except ValueError:
            return str(p)

    cache = SKILL_DIR / "data" / "style_profiles.json"
    have = set()
    if cache.exists():
        have = set(json.loads(cache.read_text(encoding="utf-8")).get("content", {}))
    missing = [p for p in paths if key(p) not in have]
    if not missing:
        return True
    if not VLM_PYTHON.exists():
        print(f"\n階段 2 中止：{len(missing)} 格缺 content caption，且找不到 VLM venv")
        print(f"  預期路徑 {VLM_PYTHON}")
        print("  （要跳過 caption 請加 --no-transfer-content-prompt，但內容保留會大幅變差）")
        return False

    import subprocess
    print(f"補 content caption（{len(missing)} 格，用 VLM venv）…")
    free_vram()          # VLM 與 ComfyUI 的模型不能同時佔著 16GB
    r = subprocess.run(
        [str(VLM_PYTHON), "-X", "utf8", str(SKILL_DIR / "scripts" / "style_caption.py"),
         "--kind", "content", "--images", *[str(p) for p in missing]],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"  ! caption 產生失敗: {(r.stderr or r.stdout or '')[-400:].strip()}")
        return False
    # 補完再驗一次。key 對不上時子行程會自己去載 VLM，用系統 python 撞
    # ImportError（transformers 太舊），錯誤訊息完全看不出真正原因——在這裡擋掉
    have = set(json.loads(cache.read_text(encoding="utf-8")).get("content", {})) \
        if cache.exists() else set()
    still = [p for p in missing if key(p) not in have]
    if still:
        print(f"\n階段 2 中止：補完後仍有 {len(still)} 格查不到 caption，快取 key 對不上。")
        print(f"  期望的 key 例如 {key(still[0])}")
        return False
    print(f"  完成 {len(missing)} 格")
    return True


def free_vram():
    """請 ComfyUI 卸載模型。階段 1 的 flux2 不放掉，階段 2 的 Qwen 會塞不下 16GB。"""
    req = urllib.request.Request(
        HOST + "/free",
        data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()   # 回空 body，不要當 JSON 解
        print("已請 ComfyUI 釋放 VRAM")
    except Exception as e:
        print(f"釋放 VRAM 失敗（不致命，繼續）: {e}")


def check_style_caption(ref_path):
    """階段 2 需要風格參考圖的 caption。沒有快取就得先用 VLM venv 產生——
    本腳本用系統 python 跑，transformers 版本太舊載不動 VLM，所以先擋下來給明確指示。"""
    cache = SKILL_DIR / "data" / "style_profiles.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        for k in d.get("style", {}):
            if pathlib.Path(k).name == ref_path.name:
                return d["style"][k]
    print(f"\n階段 2 中止：{ref_path.name} 還沒有 style caption。")
    print("  請先用 VLM venv 產生（並人工複核，VLM 會看錯）：")
    print(f'    D:/models/qwen_vl_venv/Scripts/python.exe -X utf8 \\')
    print(f'      {SKILL_DIR / "scripts" / "style_caption.py"} \\')
    print(f'      --kind style --images "{ref_path}"')
    return None


def run_transfer(shots, content_dir, transfer_dir, style, wanted,
                 force=False, content_prompt=False):
    """階段 2：呼叫 style-transfer-qwenstyle skill 把 content image 轉成目標畫風。

    讀 images/content/<id>.png，寫 images/transfer/<id>.png。

    逐格用分鏡稿的 use_transfer 欄位控制（沒寫視為 true）。
    夜戲格轉換後會被打亮成白天，這種格要在分鏡稿裡設 use_transfer: false。
    """
    import subprocess

    runner = SKILL_DIR / "scripts" / "qwenstyle_run.py"
    if not runner.exists():
        print(f"\n階段 2 中止：找不到 style-transfer-qwenstyle skill（{runner}）")
        return

    ref = style.get("style_ref")
    if not ref:
        print("\n階段 2 略過：assets/style.json 沒有設定 style_ref。")
        print('  請填入風格參考圖路徑，例如 "style_ref": "assets/style_image/style_ref_3.png"')
        return
    ref_path = pathlib.Path(ref)
    if not ref_path.is_absolute():
        ref_path = ROOT / ref
    if not ref_path.exists():
        print(f"\n階段 2 中止：找不到風格參考圖 {ref_path}")
        return
    cap = check_style_caption(ref_path)
    if cap is None:
        return

    targets = []
    for shot in shots:
        sid = shot["id"]
        if wanted and sid not in wanted:
            continue
        if not shot.get("use_transfer", True):
            print(f"{sid}  不轉換（use_transfer: false）")
            continue
        if not (content_dir / f"{sid}.png").exists():
            continue
        if (transfer_dir / f"{sid}.png").exists() and not force:
            print(f"{sid}  跳過（transfer 已存在）")
            continue
        targets.append(sid)

    if not targets:
        print("\n階段 2：沒有要轉換的格。")
        return

    print(f"\n=== 階段 2：統一畫風（{len(targets)} 格）===")
    print(f"  skill      style-transfer-qwenstyle")
    print(f"  風格參考圖  {ref_path.name}")
    print(f"  style caption  {cap}")
    if content_prompt and not ensure_content_captions(
            [content_dir / f"{sid}.png" for sid in targets]):
        return
    free_vram()

    transfer_dir.mkdir(parents=True, exist_ok=True)
    tmp = transfer_dir / "_tmp"
    tmp.mkdir(exist_ok=True)
    ok = fail = 0
    for sid in targets:
        cmd = [sys.executable, "-X", "utf8", str(runner),
               "--content", str(content_dir / f"{sid}.png"),
               "--styles", str(ref_path),
               "--tag", sid, "--outdir", str(tmp)]
        if not content_prompt:
            cmd.append("--no-content-prompt")
        # cwd 必須是 ROOT：style_caption 的快取 key 以 cwd 為基準算相對路徑，
        # 換一個 cwd 就查不到剛補好的 caption
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        produced = tmp / f"{sid}_{ref_path.stem}.png"
        if r.returncode == 0 and produced.exists():
            produced.replace(transfer_dir / f"{sid}.png")
            print(f"{sid}  OK  -> transfer/{sid}.png")
            ok += 1
        else:
            print(f"{sid}  失敗: {(r.stderr or r.stdout or '')[-300:].strip()}")
            fail += 1

    for junk in tmp.iterdir():
        junk.unlink(missing_ok=True)
    tmp.rmdir()
    print(f"\n階段 2 完成 {ok} / 失敗 {fail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--ids", help="只出這幾格，逗號分隔，例 s01,s07")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-skip", action="store_true", help="已存在的圖也重出")
    ap.add_argument("--storyboard", help="分鏡稿路徑，預設 storyboard/<系列>.json")
    ap.add_argument("--outdir", help="圖片根目錄，預設 output/<系列>/images"
                                     "（底下自動分 content/ 與 transfer/）")
    ap.add_argument("--transfer", action="store_true",
                    help="（已是預設行為，保留相容）出圖後接階段 2 統一畫風")
    ap.add_argument("--no-transfer", action="store_true",
                    help="只跑階段 1，不做統一畫風")
    ap.add_argument("--transfer-only", action="store_true",
                    help="跳過階段 1，只跑階段 2（圖已經出好時用）")
    ap.add_argument("--transfer-redo", action="store_true",
                    help="階段 2 連已存在的 _transfer.png 也重做")
    ap.add_argument("--transfer-content-prompt", action="store_true",
                    help="（已是預設行為，保留相容）階段 2 用 VLM 產生每格 content caption")
    ap.add_argument("--no-transfer-content-prompt", action="store_true",
                    help="關掉 content caption。**內容保留會大幅變差**，只在診斷時用")
    ap.add_argument("--palette", help="指定色卡 slug（assets/palette/*.json），"
                                      "例 whimsy。出到 content_<slug>/，不覆蓋原本的 content/")
    args = ap.parse_args()

    check_online()
    style = json.loads((ROOT / "assets" / "style.json").read_text(encoding="utf-8"))
    sb = pathlib.Path(args.storyboard) if args.storyboard \
        else ROOT / "output" / args.series / f"{args.series}.json"
    shots = json.loads(sb.read_text(encoding="utf-8"))

    # 色卡版另開一個資料夾。同一份分鏡稿要能出好幾組色卡並排比較，
    # 蓋掉 content/ 就沒得比了。分鏡稿本身不改，prompt 只在記憶體裡重組。
    pal = C.load_palette(style, args.palette)
    suffix = f"_{pal['slug']}" if pal else ""
    if pal:
        for s in shots:
            if s.get("prompt_manual"):
                # 手改過的 prompt 不重組（重組等於把人工修改丟掉），只把色卡句補在後面
                cl = P.clause(s, pal)
                if cl and s.get("prompt"):
                    s["prompt"] = s["prompt"] + ", " + cl
            else:
                s["prompt"] = C.compose_prompt(s, style, pal)
        print(f"套用色卡「{pal['name']}」（{pal['slug']}）：{len(shots)} 格 prompt 已重組")

    imgroot = pathlib.Path(args.outdir) if args.outdir \
        else ROOT / "output" / args.series / "images"
    outdir = imgroot / ("content" + suffix)
    transfer_dir = imgroot / ("transfer" + suffix)
    outdir.mkdir(parents=True, exist_ok=True)

    wanted = set(args.ids.split(",")) if args.ids else None

    if args.transfer_only:
        run_transfer(shots, outdir, transfer_dir, style, wanted,
                     force=args.transfer_redo,
                     content_prompt=not args.no_transfer_content_prompt)
        return

    print("=== 階段 1：生成 content image ===")
    char_inputs = character_inputs(pal)
    if any(s.get("workflow") == "text_with_character" for s in shots):
        if char_inputs:
            import character_palette as CP
            for tag, role in CP.BG_ROLES.items():
                upload_character(style, CP.OUT_DIR / f"{pal['slug']}_{tag}.png",
                                 char_inputs[role])
        else:
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

        # ⚠ 不要改回 `abs(hash(sid))`。Python 的 str.__hash__ 每個 process 重新加鹽
        # （PYTHONHASHSEED 隨機），同一格每次跑都是不同 seed —— 出了問題無法原樣重現，
        # 改 prompt 之後也分不清是改動生效還是 seed 運氣。用穩定雜湊。
        seed = args.seed if args.seed else \
            int(hashlib.sha1(sid.encode()).hexdigest()[:8], 16) % (2 ** 31)
        dest, info = run_one(shot, style, seed, outdir, char_inputs=char_inputs)
        if dest:
            print(f"{sid}  OK  {info:.1f}s  seed={seed}  -> {dest.name}")
            done += 1
        else:
            print(f"{sid}  失敗: {info}")
            failed += 1

    print(f"\n階段 1 完成 {done} / 失敗 {failed} / 跳過 {skipped}")

    if not args.no_transfer:
        run_transfer(shots, outdir, transfer_dir, style, wanted,
                     force=args.transfer_redo,
                     content_prompt=not args.no_transfer_content_prompt)


if __name__ == "__main__":
    main()
