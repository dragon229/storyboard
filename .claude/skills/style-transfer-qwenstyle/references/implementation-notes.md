# Skill：content 圖 + style 圖 → 風格轉換

把 ComfyUI workflow 做不到的兩件事包在外面：**用 VLM 看圖寫 prompt**、**論文規定的尺寸規則**。
對使用者只暴露「兩張圖」這個介面。

實作依據：[QwenStyle 官方 Space 的 app.py](https://huggingface.co/spaces/witcherderivia/QwenStyle/blob/main/app.py)
逐行對照，而非只看論文文字（Space 較新，三處與論文不同，見下）。

---

## 一句話

```bash
python -X utf8 scripts/qwenstyle_run.py \
  --content "output/錢可以買到時間/images/s01.png" \
  --styles assets/style_image/style_ref_*.png \
  --tag RUN1
```

---

## 五個步驟

| # | 步驟 | 做什麼 | 實作 |
|---|---|---|---|
| 1 | **content caption** | Qwen2.5-VL 看 content 圖，輸出 **≤3 個詞**的主體清單 | `style_caption.py` |
| 2 | **style caption** | Qwen2.5-VL 看 style 圖，輸出 **5 個詞**的風格描述，**且指令明令 not objects** | `style_caption.py` |
| 3 | **人工複核** | 檢查 caption 是否誤判，錯的用 `--set` 覆寫（**必要步驟，見「已知失效模式」**） | `style_caption.py --set` |
| 4 | **組 prompt** | `固定句 , content caption , style caption`（逗號串接） | `style_caption.assemble` |
| 5 | **尺寸 + 送件** | 兩張圖都等比例縮到最短邊 = `minedge`，長邊取 16 的倍數 | `qwenstyle_run.py` |

固定句（論文的訓練 prompt，一字不改）：

```
Style Transfer the style of Figure 2 to Figure 1, and keep the content and characteristics of Figure 1.
```

VLM 的兩句指令（照抄 Space，一字不改）：

```
content : describe main objects (fewer than 3) with separated words, each word is
          separated by comma,  the total number of words is strictly fewer than 3
style   : describe only the artistic style, material and stroke in 5 words, not objects.
```

---

## 為什麼 style 指令結尾一定要有 `not objects.`

官方把這句寫進指令裡是有原因的。本專案實測過反例：prompt 裡寫 `warm sand`，
模型把醫療艙場景整個換成**仙人掌沙漠**——`sand` 被當成實體沙子畫了出來。

→ **style caption 只能是風格／材質／筆觸的形容詞，絕不能出現可被當成畫面物件的名詞。**
覆寫 caption 時也必須遵守這條。詳見 `research/style-transfer/log.md` 教訓 25。

---

## 已知失效模式：VLM 會看錯，所以第 3 步不能省

實測案例：`style_ref_1.png` 是賽璐珞動畫的霓虹夜景，但 VLM 產出

```
Digital art, pixelated, smooth lines, vibrant colors.
```

它把圖片的**壓縮噪點讀成了「像素風」**。模型忠實照做，輸出變成 8-bit 像素藝術。

覆寫成正確描述後立刻修好：

```bash
python -X utf8 .claude/skills/style-transfer-qwenstyle/scripts/style_caption.py --kind style \
  --images assets/style_image/style_ref_1.png \
  --set "Anime cel shading, neon glow, bold outlines, high contrast."
```

**這是 caption 品質問題，不是模型能力問題。** 每次換新的 style 圖都要看一眼 caption。

caption 快取在 `data/style_profiles.json`（skill 目錄內），可直接編輯。

---

## Space 與論文的三處不同（以 Space 為準，它較新）

| # | 論文寫的 | Space 實際做的 |
|---|---|---|
| 1 | style 圖 resize 成 `min(H,W)` **正方形** | **不是正方形**。app.py 裡 `#style_ref.resize((minedge, minedge))` 被註解掉，改成與 content 相同的等比例縮放 |
| 2 | 未提 | **`minedge` 是風格強度旋鈕**：Space 說明寫「changing the minedge could lead to different style similarity」，預設 1024，範圍 256–2048 |
| 3 | 只有固定句 | 固定句後面可**逗號串接兩段 VLM 自動生成的 caption**（Prompt Enhancer 的兩個 checkbox） |

---

## 模型清單

| 用途 | 檔案 | 位置 |
|---|---|---|
| 底模 | `qwen_image_edit_2509_fp8_e4m3fn.safetensors` | ComfyUI `diffusion_models/` |
| 風格 LoRA | `qwenstyle_v1_2509_diffusers.safetensors` @ 1.0 | ComfyUI `loras/` |
| 加速 LoRA | `Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors` @ 1.0 | ComfyUI `loras/` |
| VLM | `Qwen/Qwen2.5-VL-7B-Instruct` | `D:\models\Qwen2.5-VL-7B-Instruct` |

⚠️ **底模必須是 2509**。QwenStyle 訓練在 2509 上，2511 是不同版本。

⚠️⚠️ **不要用 QwenStyle repo 附的 `diffsynth_Qwen-Image-Edit-2509-Lightning-4steps...`。**
它的 key 是 `lora_A.default.weight`（diffsynth 格式），**ComfyUI 會靜默不載入，log 完全沒有警告**，
結果是 4 步欠煮的糊圖——實測六種風格全部偏軟、低對比、缺乏銳利度。
換成 lightx2v 的 ComfyUI 標準命名版本（`lora_down`/`lora_up`）後立刻正常。

那顆 diffsynth 版本是給 Space 的 diffusers pipeline 用的，不是給 ComfyUI 用的。
兩者也確實不是同一份權重（`lora_A` 的 hash 不同，但 `alpha` 與 `lora_up` 相同）。

---

## 取樣參數（照 Space）

| 項目 | 值 |
|---|---|
| steps | **4** |
| cfg | **1.0** |
| negative prompt | **一個空格** `" "` |
| sampler / scheduler | euler / simple |
| denoise | **1.0**（絕對不能降，見 log 教訓 1） |
| seed | 123 |
| 輸出尺寸 | = content 縮放後的尺寸 |

---

## VLM 執行環境

Qwen2.5-VL 需要 `transformers >= 4.51`，但系統 Python 是 4.46.2。
用 `--system-site-packages` 建了獨立 venv，繼承既有 torch，只裝新版套件，
**沒有動到系統環境**。

```
D:\models\qwen_vl_venv\Scripts\python.exe   # transformers 4.57.6（永久 venv）
系統 python                                  # transformers 4.46.2（未變動）
```

跑 caption 前先讓 ComfyUI 釋放 VRAM（16GB 顯卡塞不下兩個模型）：

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"unload_models":true,"free_memory":true}' http://127.0.0.1:8188/free
```

---

## 常用參數

| 參數 | 說明 |
|---|---|
| `--minedge 1024` | 風格強度旋鈕，256–2048 |
| `--no-style-prompt` | 只用固定句，不加 style caption（用來檢驗「圖」單獨的貢獻） |
| `--no-content-prompt` | 不加 content caption |
| `--refresh-caption` | 忽略快取重新產生 |
| `--unet` / `--lightning` / `--lora` | 覆寫模型檔名，用來做版本對照 |
| `--strength` | 風格 LoRA 強度，預設 1.0 |

---

## 相關檔案

- [scripts/qwenstyle_run.py](../scripts/qwenstyle_run.py) — skill 執行層
- [scripts/style_caption.py](../scripts/style_caption.py) — VLM caption 層
- [comfyUI_workflow/qwenstyle_v1_2509.json](../workflow/qwenstyle_v1_2509.json) — API workflow
- [data/style_profiles.json](../data/style_profiles.json) — caption 快取（可手改）
- [research/style-transfer/log.md](../../../../research/style-transfer/log.md) — 完整實驗日誌與教訓
