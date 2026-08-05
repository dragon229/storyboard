---
name: style-transfer-qwenstyle
description: "content 圖 + style 圖 → 把 content 圖轉成 style 圖的畫風（構圖、人物、物件保留）。當使用者說「把這張圖轉成那個風格」「用這張當風格參考」「風格轉換」「style transfer」，或給你一張內容圖和一張（或多張）風格圖要你套用風格時，使用這個 skill。基於 QwenStyle V1（Qwen-Image-Edit-2509 + LoRA），需要 ComfyUI 在 127.0.0.1:8188 運作。"
---

# style-transfer-qwenstyle

content 圖 + style 圖 → 輸出 content 的內容、style 的畫風。
實作忠實複現 [QwenStyle 官方 Space](https://huggingface.co/spaces/witcherderivia/QwenStyle) 的 app.py（以原始碼為準，不是論文——兩者有出入，見 references）。

## 前置條件（跑之前先檢查）

1. **ComfyUI 在 `127.0.0.1:8188` 運作**：`curl -s http://127.0.0.1:8188/queue`，沒回應就請使用者先開 ComfyUI，不要硬跑
2. 模型檔已就位（都下載過了）：
   - 底模 `qwen_image_edit_2509_fp8_e4m3fn.safetensors`（ComfyUI `diffusion_models/`）
   - `qwenstyle_v1_2509_diffusers.safetensors` + `Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors`（ComfyUI `loras/`）
   - VLM `D:\models\Qwen2.5-VL-7B-Instruct`
3. VLM 專用 venv：`D:\models\qwen_vl_venv\Scripts\python.exe`（transformers 4.57.6；系統 Python 版本太舊跑不動 VLM）

## 執行流程

### 步驟 1 · 產生 caption（新的 style 圖才需要）

**先讓 ComfyUI 釋放 VRAM**（16GB 塞不下兩個模型）：

```bash
curl -X POST -H "Content-Type: application/json" -d '{"unload_models":true,"free_memory":true}' http://127.0.0.1:8188/free
```

用 **VLM venv** 跑 caption（快取在 `data/style_profiles.json`，已有的會直接沿用）：

```bash
D:/models/qwen_vl_venv/Scripts/python.exe -X utf8 \
  .claude/skills/style-transfer-qwenstyle/scripts/style_caption.py \
  --kind style --images <style圖路徑...>
```

content 圖同理，`--kind content`。

### 步驟 2 · 人工複核 caption ⚠️ 不可省略

把產出的 caption 唸一遍，對照圖片檢查。**VLM 會看錯，而且錯得很合理**（實例：把壓縮噪點讀成「pixelated」，輸出就真的變像素風）。

錯了就覆寫：

```bash
python -X utf8 .claude/skills/style-transfer-qwenstyle/scripts/style_caption.py \
  --kind style --images <那張圖> --set "正確的風格描述"
```

覆寫規則：**只能用風格/材質/筆觸的形容詞，絕不能出現可被當成畫面物件的名詞**（`warm sand` 會被畫成真的沙漠）。

### 步驟 3 · 執行轉換

用**一般 python**（不是 venv）跑：

```bash
python -X utf8 .claude/skills/style-transfer-qwenstyle/scripts/qwenstyle_run.py \
  --content <content圖> --styles <style圖1> [<style圖2> ...] --tag <本次標籤>
```

輸出到 `<目前目錄>/output/style_transfer/<tag>_<style名>.png`，每格約 34 秒。

### 步驟 4 · 抽樣看圖

每批跑完至少開 1–2 張人工看。自動指標（內容分數）**只能同風格內比較**，跨風格的絕對值沒有意義。

## 常用旋鈕

| 參數 | 說明 |
|---|---|
| `--minedge 1024` | **風格強度旋鈕**（官方文件沒寫，Space 說明有）。256–2048，值不同風格相似度不同 |
| `--seed 123` | 預設 123（官方 demo 值）。同 seed 可重現 |
| `--no-style-prompt` / `--no-content-prompt` | 關掉 caption，只用固定句（診斷「圖 vs 文字」貢獻時用） |
| `--refresh-caption` | 忽略快取重新產生 |
| `--unet` / `--lightning` / `--lora` | 覆寫模型檔名（做版本對照時用） |

## 已知陷阱（都實測踩過）

1. **不要用 QwenStyle repo 附的 `diffsynth_...Lightning` LoRA**——ComfyUI 靜默不載入（log 零警告），結果是欠煮糊圖。workflow 已寫死正確的 lightx2v 版本，不要改
2. **輸出糊/軟/低對比 → 先懷疑 Lightning LoRA 沒生效**，不要先調 prompt
3. **caption 含物件名詞 → 那個物件會被畫出來**。步驟 2 的複核就是在擋這個
4. **底模必須 2509**。QwenStyle 訓練在 2509 上，掛 2511 內容保留明顯變差（實測內容分數低 60%）
5. steps=4 / cfg=1.0 / denoise=1.0 是定值，**denoise 絕對不能降**（會退化成複製機）

## 相關檔案

- [scripts/qwenstyle_run.py](scripts/qwenstyle_run.py) — 執行層
- [scripts/style_caption.py](scripts/style_caption.py) — VLM caption 層（含 `--set` 覆寫）
- [workflow/qwenstyle_v1_2509.json](workflow/qwenstyle_v1_2509.json) — ComfyUI API workflow
- [data/style_profiles.json](data/style_profiles.json) — caption 快取（可直接手改）
- [references/implementation-notes.md](references/implementation-notes.md) — 完整實作細節、與論文的出入、環境說明
