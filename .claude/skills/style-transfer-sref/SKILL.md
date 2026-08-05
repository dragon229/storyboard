---
name: style-transfer-sref
description: "content 圖 + style 圖 → 把 content 圖轉成 style 圖的畫風，構圖與物件保留。當使用者說「把這張圖轉成那個風格」「用這張當風格參考」「風格轉換」「style transfer」「sref」時使用。也支援只給一張風格圖 + 中文題材詞，用該畫風畫出新題材。基於 Qwen_Image_Edit_2509_Sref_Lora + QwenStyle LoRA 雙掛，需要 ComfyUI 在 127.0.0.1:8188 運作。"
---

# style-transfer-sref

content 圖 + style 圖 → 輸出 content 的內容、style 的畫風。

底層是 [Qwen_Image_Edit_2509_Sref_Lora](https://huggingface.co/svjack/Qwen_Image_Edit_2509_Sref_Lora)，
但**做雙圖時必須再疊一顆 QwenStyle LoRA**——這不是選配，理由見下面的陷阱 1。

## 前置條件

1. ComfyUI 在 `127.0.0.1:8188`：`curl -s http://127.0.0.1:8188/queue`，沒回應就請使用者先開
2. 模型檔：
   - 底模 `qwen_image_edit_2509_fp8_e4m3fn.safetensors`（`diffusion_models/`）
   - `loras/`：`Qwen_Image_Edit_2509_sref_lora_000007000.safetensors`、
     `qwenstyle_v1_2509_diffusers.safetensors`、
     `Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors`
3. 只有走 `--text-bridge` 或單圖模式才需要 VLM venv：`D:\models\qwen_vl_venv\Scripts\python.exe`

## 主要用法：content 圖 → style 圖的畫風

```bash
python -X utf8 .claude/skills/style-transfer-sref/scripts/sref_run.py \
  --content <內容圖> --styles <風格圖1> [<風格圖2> ...] --tag <本次標籤>
```

不需要 VLM，不需要寫 prompt。輸出到 `<目前目錄>/output/sref/<tag>_<風格圖名>.png`，
每格約 30 秒。輸出比例跟**內容圖**走。

`--styles` 可以一次給多張，逐張跑，方便一次比較多種風格。

### 看結果

每批至少開 1–2 張人工看。指標怎麼讀：

| 指標 | 怎麼看 |
|---|---|
| `構圖保留` | **越高越好**。0.4 以上算保住了；低於 0.15 代表畫面被重新想像過，不是轉風格 |
| `L` / `暖` / `S` | 跟同行的「參考」（＝風格圖）比。完全不動＝風格沒進去 |
| `銳利` | 低於 30 要懷疑 Lightning LoRA 沒生效（欠煮） |

## 次要用法：一張風格圖 + 題材詞

sref LoRA 的原生用法——不給 content 圖，用文字指定題材，畫出新題材：

```bash
# 步驟 1：釋放 VRAM 後用 VLM 產生中文編輯指令
curl -X POST -H "Content-Type: application/json" -d '{"unload_models":true,"free_memory":true}' http://127.0.0.1:8188/free
D:/models/qwen_vl_venv/Scripts/python.exe -X utf8 \
  .claude/skills/style-transfer-sref/scripts/sref_prompt.py --style <風格圖> --target "粉色八爪鱼"

# 步驟 2：人工複核指令（見下），沒問題再出圖
python -X utf8 .claude/skills/style-transfer-sref/scripts/sref_run.py \
  --styles <風格圖> --target "粉色八爪鱼" --tag T1
```

**步驟 2 的人工複核不可省略。** VLM 會寫出直接毀掉畫風的句子，實測踩過：

- 「替换为一个简单的白色背景」→ 出圖整片漂白
- 「调整为适合的环境，如草地或公园」→ 原本的暗色室內全沒了
- 「调整颜色使其符合自然颜色」→ 原圖的綠色調被還原掉
- 「添加一些装饰元素，如铃铛或蝴蝶结」→ 憑空多出東西

看到就覆寫，每一條都要指名「沿用原圖的哪個特徵」（只寫「保持画风一致」太抽象，模型接不住）：

```bash
python -X utf8 .claude/skills/style-transfer-sref/scripts/sref_prompt.py \
  --style <風格圖> --target "粉色八爪鱼" --set "进行下面的修改：
- 将<原主體>替换为<新題材>，占據原本的位置與比例；
- 完整保留原有的<背景>，不要更換背景，不要使用純色背景；
- 严格延续原图的<色調/曝光>，不要还原成自然颜色；
- 保留原图的<顆粒/失焦/暗角>；光源方向與原图一致。"
```

## 常用旋鈕

| 參數 | 說明 |
|---|---|
| `--strength 0.8` | sref LoRA 權重 |
| `--extra-strength 0.8` | qwenstyle LoRA 權重（雙圖模式）。風格太搶戲時調低 |
| `--text-bridge` | 備案模式：VLM 把 content 圖描述成文字再重畫。**構圖會失真**，只在雙圖效果不好時用 |
| `--lora ..._000003000.safetensors` | 換 sref checkpoint。repo 有 250–7000 共 28 顆，預設 7000（風格最強） |
| `--megapixels 1.0` | 輸出尺寸（官方值） |
| `--seed 123` | 同 seed 可重現 |
| `--no-stack` / `--no-sref` | 診斷用對照組，見陷阱 1 |

## 已知陷阱（都實測踩過）

1. **雙圖模式沒疊 qwenstyle LoRA 的話，style 圖會被完全忽略——而且不會報錯。**
   實測：只掛 sref、或完全不掛 LoRA，換三張性質天差地遠的風格圖
   （L65 暖+38 / L69 暖−11 / L180 S0.07 近乎白圖），輸出統計量**一模一樣**（L34、暖−25、S0.85）。
   雙圖風格轉換的能力只存在於 qwenstyle 那顆 LoRA 裡，sref 和裸底模都沒有。
   `--no-stack` 可以重現這個現象。
2. **sref LoRA 在雙圖模式是配角。** 它負責把風格咬得更緊，主力是 qwenstyle。
   實測差異：漫畫網點風格下，只用 qwenstyle 會把手臂畫成鵝卵石亂紋；
   疊上 sref 才是乾淨的漫畫排線。
3. **風格圖的「內容」會漏進輸出。** 實測拿一張「手握綠色發光裝置」的圖當風格參考去轉天平圖，
   結果那隻手和裝置整個被畫進天平裡，蓋掉右盤的金幣。
   **選風格圖時挑主體單純、構圖乾淨的**；主體強烈搶眼的圖（大面積前景物件）容易洩漏。
   出圖後檢查有沒有多出風格圖裡的東西。
4. **照片類風格（實拍、底片顆粒）轉不太動。** 三個驗收案例裡，3D 公仔與漫畫網點都成功，
   顆粒感綠調底片那張幾乎沒變化。這類風格建議改用 `--text-bridge`，或接受效果有限。
5. **`--text-bridge` 會失真。** content 經過文字必然掉資訊——實測構圖保留只有 0.03，
   手的位置、物件細節都被重新想像。只在雙圖模式效果不好時當備案。
6. **輸出糊 / 銳利低於 30 → 先懷疑 Lightning LoRA 沒生效**，不要先調 prompt。
   絕對不要換成 `diffsynth_*` 那顆——key 是 diffsynth 格式，ComfyUI 靜默不載入、log 零警告。
7. **底模必須 2509。** 兩顆 LoRA 都訓練在 2509 上。
8. steps=4 / cfg=1.0 / denoise=1.0 是定值，**denoise 絕對不能降**（會退化成複製機）。
9. **不要照抄官方 workflow 裡節點 111 的 widget 文字**——那是執行時會被連線覆蓋的死資料。
   官方檔還是 UI 格式、一半節點是 bypass 的另一條分支。已轉寫好在 `workflow/sref_2509.json`。

## 跟 style-transfer-qwenstyle 的關係

`style-transfer-qwenstyle` 是純 QwenStyle 的忠實複現（英文 prompt + VLM caption + minedge 旋鈕）。
本 skill 在它之上疊了 sref LoRA，並多了「一張圖 + 題材詞」的模式。
兩者都要用時，構圖保留與風格強度會有差異，值得各跑一次比較。

## 相關檔案

- [scripts/sref_run.py](scripts/sref_run.py) — 執行層
- [scripts/sref_prompt.py](scripts/sref_prompt.py) — VLM 層（content 描述、編輯指令、護欄、`--set` 覆寫）
- [workflow/sref_2509.json](workflow/sref_2509.json) — ComfyUI API workflow
- [data/sref_prompts.json](data/sref_prompts.json) — 快取（可直接手改）
- [references/implementation-notes.md](references/implementation-notes.md) — 與官方的逐項差異、完整實驗數據
