"""用 SD3.5 Large 生一份 content image，拿來跟 flux2 版本對照。

prompt 與 negative 逐字取自分鏡稿與 style.json，**不做任何改寫**——
變因只有模型，這樣兩份圖才可比。

與 render.py 的差別：
- SD3.5 沒有 flux2 的 `ReferenceLatent` 路徑，**角色參考圖掛不上**，
  所以 60 格一律走純文生圖，`workflow` 欄位在這裡不分流
- 因此觀察者在這份裡不會保持一致，這是預期中的，不是 bug

用法:
    python -X utf8 scripts/render_sd35.py --series if_test_2
    python -X utf8 scripts/render_sd35.py --series if_test_2 --ids s01,s11 --no-skip
"""
import argparse, json, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render import ROOT, check_online, _get, _post_json, CLIENT_ID  # noqa: E402
import urllib.request  # noqa: E402

WORKFLOW = ROOT / "comfyUI_workflow" / "sd35_text_to_image.json"


def build(shot, style, seed):
    m = style["model"]
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf["20"]["inputs"]["text"] = shot["prompt"]
    wf["21"]["inputs"]["text"] = style["negative"]
    wf["43"]["inputs"]["seed"] = seed
    wf["42"]["inputs"]["width"] = m["width"]
    wf["42"]["inputs"]["height"] = m["height"]
    return wf


def run_one(shot, style, seed, outdir):
    pid = _post_json("/prompt", {"prompt": build(shot, style, seed),
                                 "client_id": CLIENT_ID})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < 900:
        hist = _get(f"/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            if entry.get("status", {}).get("status_str") == "error":
                return None, entry["status"].get("messages", [])
            for out in entry.get("outputs", {}).values():
                for img in out.get("images", []):
                    raw = urllib.request.urlopen(
                        f"http://127.0.0.1:8188/view?filename={img['filename']}"
                        f"&subfolder={img.get('subfolder','')}&type={img['type']}",
                        timeout=120).read()
                    dest = outdir / f"{shot['id']}.png"
                    dest.write_bytes(raw)
                    return dest, time.time() - t0
            return None, ["完成但沒有輸出圖片"]
        time.sleep(3)
    return None, ["逾時 900 秒"]


def main():
    ap = argparse.ArgumentParser(description="用 SD3.5 生一份 content image")
    ap.add_argument("--series", required=True)
    ap.add_argument("--ids", help="只出這幾格，逗號分隔")
    ap.add_argument("--seed", type=int, default=0, help="0 = 依 id 決定，保證可重現")
    ap.add_argument("--no-skip", action="store_true", help="已存在的圖也重出")
    a = ap.parse_args()

    check_online()
    style = json.loads((ROOT / "assets" / "style.json").read_text(encoding="utf-8"))
    shots = json.loads((ROOT / "output" / a.series / f"{a.series}.json")
                       .read_text(encoding="utf-8"))
    if a.ids:
        want = {x.strip() for x in a.ids.split(",")}
        shots = [s for s in shots if s["id"] in want]

    outdir = ROOT / "output" / a.series / "images" / "content_sd3.5"
    outdir.mkdir(parents=True, exist_ok=True)

    ok = fail = skip = 0
    for s in shots:
        if s.get("needs_post_text"):
            print(f"{s['id']}  跳過（needs_post_text）")
            skip += 1
            continue
        dest = outdir / f"{s['id']}.png"
        if dest.exists() and not a.no_skip:
            skip += 1
            continue
        seed = a.seed or (int(s["id"][1:]) * 7919 + 1000)
        p, info = run_one(s, style, seed, outdir)
        if p:
            print(f"{s['id']}  OK  {info:.1f}s  seed={seed}  -> {p.name}", flush=True)
            ok += 1
        else:
            print(f"{s['id']}  失敗  {info}", flush=True)
            fail += 1
    print(f"\nSD3.5 完成 {ok} / 失敗 {fail} / 跳過 {skip}  -> {outdir}")


if __name__ == "__main__":
    main()
