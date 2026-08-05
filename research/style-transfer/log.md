# 風格轉換 workflow 實驗日誌

> 目標：`content 圖 + style 圖 → 保留 content 的構圖/人物/線條，套上 style 圖的畫風`。
> 用途：把 71 格分鏡圖收斂到同一個風格，解決 flux2 出圖六種畫風並存的問題。
> 成功標準：(1) 風格來源是**圖片**不是文字色票 (2) 構圖完整保留 (3) 不同題材（人物／幾何示意／夜戲／場景）都收斂到同一調性 (4) 可腳本化批次。
>
> 開始日期：2026-08-04。前置：ComfyUI 0.25.1 @ 127.0.0.1:8188，RTX 4090 Laptop 16GB，底模 Qwen-Image-Edit-2511-FP8。

---

## 量測方式

所有數據都用同一套（`styletest.py::measure`，縮到 256×256 取平均）：

| 指標 | 意義 | 目標值（`assets/style_ref.png`）|
|---|---|---|
| **L** | 亮度 0–255 | 203（明亮） |
| **暖 (R−B)** | 冷暖，正=暖 | **+72** |
| **S** | 飽和度 0–1 | 0.32 |

探針原圖基準：

| 格 | 題材 | L | 暖 | S |
|---|---|---|---|---|
| s01 | 人物特寫（醫療艙，藍調） | 192 | −77 | 0.36 |
| s08 | 純幾何示意圖 | 待測 | | |
| s59 | 夜戲綠光 | 待測 | | |
| s70 | 場景插畫 | 待測 | | |

---

## 候選盤點（2026-08-04 調查）

使用者原本點名兩個：QwenStyle、Sref LoRA。調查後實際可用的有四個，其中**兩個是原清單沒有的**：

| # | 名稱 | HF repo | 底模 | 大小 | 架構 | 判定 |
|---|---|---|---|---|---|---|
| 1 | **dx8152 Style-Transfer** | `dx8152/Qwen-Image-Edit-2511-Style-Transfer` | **2511（原生！）** | 225 MB | content=圖1, style=圖2 | ⭐ 最對症，已測 |
| 2 | **QwenStyle V1**（學術正解） | `witcherderivia/Qwen-Image-Style-Transfer` | 2509 | 450 MB | content=圖1, style=圖2 | 待測 |
| 3 | **InStyle**（Sref 路線） | `peteromallet/Qwen-Image-Edit-InStyle` | Qwen-Image-Edit **v1**（更舊） | 141 MB | style 圖 + **文字描述內容** | ⚠️ 架構不符，見下 |
| 4 | zooeyy Style-Transfer | `zooeyy/Style-Transfer` | 2511 | 563 MB | 未查 | 備案 |
| 5 | svjack Sref LoRA | `svjack/Qwen_Image_Edit_2509_Sref_Lora` | 2509 | 563 MB ×28 checkpoint | 未查 | 備案 |

### 教訓 0：InStyle 架構跟需求不符（不用實測就能判掉一半）

InStyle 的 README 寫得很清楚，prompt 格式是：

```
Make an image in this style of <描述你要的內容>
```

也就是 **style 圖 + 文字描述 → 生成新圖**，它是「用參考圖的風格畫一張新的」，**不是「把既有的圖改成這個風格」**。內容來自文字，不來自 content 圖。這跟我們要的 content-preserving style transfer 是兩件事。

而且它的底模是最初代 `Qwen-Image-Edit`，比機器上的 2511 隔了兩代。

→ **仍會測，但期望值低**，主要是驗證「它是否也能吃 content 圖」。

### 教訓 1：關鍵節點 `FluxKontextMultiReferenceLatentMethod`

上個 session 的結論是「image2 參考圖路線全滅（8 種措辭都失敗），模型把 image2 當合成素材」。

看了 dx8152 的官方 workflow 才發現原因：conditioning 送進 KSampler 之前要先過

```
FluxKontextMultiReferenceLatentMethod(reference_latents_method="index_timestep_zero")
```

這個節點改變多張 reference latent 的索引方式。**沒有它，模型就會把 image2 當成「要合成進畫面的第二個素材」**——正是上個 session 觀察到的「把參考圖的盆栽/水壺搬進畫面」。

本機 ComfyUI 已內建此節點（options: `offset` / `index` / `uxo/uno` / `index_timestep_zero`），不需裝外掛。

→ **上個 session「image2 路線全滅」的結論應該作廢**，那是接線缺件，不是路線錯誤。

---

## 產物

- workflow：[qwen_edit_2511_style_lora_dx8152.json](../../comfyUI_workflow/qwen_edit_2511_style_lora_dx8152.json)
- 實驗跑台：scratchpad `styletest.py`（參數化：--lora / --strength / --steps / --prompt / --refmethod / --styleref）
- 輸出：`output/錢可以買到時間/images/style_lab/<tag>_<shot>.png`
- LoRA 落地位置：`C:\Users\User\ComfyUI-Shared\models\loras\`
  - `qwen_edit_2511_style_transfer_dx8152.safetensors`
  - `qwenstyle_v1_2509_diffusers.safetensors`
  - `qwen_edit_instyle_0.5.safetensors`

---

## 實驗記錄

### R1 — dx8152 LoRA，預設參數

| 項目 | 值 |
|---|---|
| LoRA | dx8152 style-transfer @ 0.8（掛在 CFGNorm 之後） |
| 加速 | 2511-Lightning-4steps @ 1.0 |
| KSampler | 8 步 / cfg 1 / euler / simple / **denoise 1.0** |
| refmethod | `index_timestep_zero` |
| prompt | `style transfer,将图1的画风改为图2的风格` |
| style_ref | `assets/style_ref.png`（暖砂平塗室內） |
| 耗時 | 53 秒／格 |

**數據（s01）**

| | L | 暖 | S | 尺寸 |
|---|---|---|---|---|
| 原圖 | 192 | −77 | 0.36 | 1600×896 |
| 輸出 | **101** | **−42** | 0.38 | 1368×760 |
| 目標 | 203 | +72 | 0.32 | |

**目視**：構圖、人物姿勢、機器面板、管線位置**完整保留**，臉部特徵、銀髮都在。但畫風跑去做了**寫實動畫賽璐珞上色＋大量陰影漸層**，整體壓暗，藍調保留。**完全沒有沾到 style_ref 的暖砂平塗調性**。

**結論**：
- ✅ 內容保留能力極強（比路線 A 文字重上色好）
- ✅ `FluxKontextMultiReferenceLatentMethod` 讓 image2 不再被當合成素材（畫面裡沒有出現盆栽/水壺，這是相對上個 session 的明確進步）
- ❌ **但風格沒有跟 style_ref 走**，而是套上了 LoRA 自己的「預設動畫風」
- ❌ 亮度反向（192→101，目標 203）

**下一步假設**：需要確認 image2 到底有沒有在影響輸出。若換一張冷色 style_ref 輸出不變 → image2 被無視，問題在注入；若有變 → 問題在 style_ref 本身的風格訊號太弱。

### R2 / R3 / R4 — 診斷組

s01 全部，dx8152，8 步（R4 為 4 步）：

| tag | 變因 | style_ref 的 (L/暖/S) | 輸出 L | 輸出 暖 | 輸出 S |
|---|---|---|---|---|---|
| R1 | 基準 str 0.8 | 203 / +72 / 0.32 | 101 | −42 | 0.38 |
| R2_coldref | ref 換冷／中性 | 219 / **+20** / 0.10 | 103 | **−46** | 0.41 |
| R3_str10 | str 0.8→**1.0** | 203 / +72 / 0.32 | 102 | **−27** | **0.30** |
| R4_nolora | **拿掉 style LoRA** | — | 127 | **−89** | 0.58 |

**判讀**：

1. ✅ **LoRA 確實有載入生效**：R4（無 LoRA）跑出 暖−89 / S0.58，與 R1–R3 的 −27~−46 / 0.30~0.41 差距巨大。排除「key 格式不合被靜默略過」的疑慮。
2. ✅ **strength 是強力槓桿**：0.8→1.0 讓暖從 −42 拉到 −27（+15），飽和度 0.38→0.30（**已達標 0.32**）。
3. ❌ **但 image2 幾乎沒作用**：R1 vs R2 的參考圖差了 52 個暖度單位，輸出只差 4 個單位。三張圖目視**幾乎一模一樣**——同樣的寫實動畫賽璐珞上色、同樣壓暗。

### R5 — 極端參考圖（決定性測試）★ 轉折點

把 style_ref 換成 `s59.png`（夜戲綠光，L41 / 暖−48 / S0.86），與原本的暖砂平塗板天差地遠：

| | L | 暖 | S |
|---|---|---|---|
| 參考圖 s59 | 41 | −48 | 0.86 |
| 輸出 | **57** | **−50** | **0.61** |
| （對照 R3 用暖砂板） | 102 | −27 | 0.30 |

**目視**：構圖完整保留，整體壓成深藍綠夜色，明顯吃到 s59 的色調。

**結論（推翻 R1–R3 的初判）**：**image2 有在被讀**，只是傳遞率低。在 str 1.0 下，參考圖 120 個暖度單位的差異 → 輸出只有 23 個單位的差異，**傳遞率約 19%**。content 圖自身的顏色仍然主導。

而且要分清楚兩件事：
- **色調／光線**：會從 image2 傳過來（R5 證明）
- **筆觸／渲染方式**：**不會**，一律套用 LoRA 自己烘焙的「寫實動畫賽璐珞」風

→ 這對「71 格一致」其實**是好事**：渲染方式被 LoRA 強制統一，正是我們要的收斂機制。

### R6 — QwenStyle V1（2509 LoRA 硬掛 2511）

| | L | 暖 | S | 耗時 |
|---|---|---|---|---|
| 輸出 | 143 | −61 | 0.42 | 33s |

有載入生效（跟 R4 無 LoRA 的 127/−89/0.58 明顯不同），但**收斂力比 dx8152 弱得多**（暖只從 −77 拉到 −61，dx8152 能到 −27）。推測是跨版本（2509 LoRA vs 2511 底模）＋ diffusers key 格式的損耗。

→ **不如 2511 原生的 dx8152，降為備案。**

### R7 — InStyle（Sref 路線）❌ 判死

| | L | 暖 | S |
|---|---|---|---|
| 輸出 | 164 | −33 | 0.20 |

**目視：構圖被完全摧毀**——背景變成馬賽克格子布、人物換成長髮、醫療艙整個消失。

完全符合調查階段的預判：InStyle 是「用參考圖的風格**生成新圖**」，內容來自文字。它根本沒有 content-preserving 的能力。

→ **Sref／InStyle 路線正式排除，不需再測。**

---

## 目前結論（第一輪）

| 候選 | 內容保留 | 跟隨參考圖 | 風格統一力 | 判定 |
|---|---|---|---|---|
| **dx8152（2511 原生）** | ✅ 極佳 | ⚠️ 僅色調，約 19% | ✅ 強（強制統一渲染） | **🏆 主線** |
| QwenStyle V1 | ✅ 佳 | ⚠️ 更弱 | ⚠️ 弱 | 備案 |
| InStyle / Sref | ❌ 摧毀 | — | — | ❌ 排除 |

**主要缺口**：亮度收不上去（輸出 L≈102，目標 203），暖度只到 −27（目標 +72）。

---

### R8–R13 — 加強組（s01）

| tag | 變因 | L | 暖 | S | 耗時 |
|---|---|---|---|---|---|
| R3 | 純圖鎖（str 1.0） | 102 | −27 | 0.30 | 53s |
| **R8_combo** | **圖鎖 ＋ 文字色票** | 135 | **+44** | 0.40 | 54s |
| R9_str14 | str 1.4 超載 | 90 | −17 | 0.28 | 55s |
| R10_4step | 純圖鎖，4 步 | 107 | −26 | 0.28 | **28s** |
| R11_bright | R8 ＋ 亮度語彙 | **151** | +45 | 0.40 | 51s |
| R12_combo4 | R8 配方，4 步 | 138 | +48 | 0.40 | **27s** |
| R13_str08 | R8 配方，str 0.8 | 140 | +49 | 0.40 | 50s |

**判讀**：

1. ⭐ **R8 是關鍵突破**：加上文字色票後，暖度從 −27 直接跳到 **+44**（目標 +72）。**圖鎖與文字不是二選一，是互補的**——LoRA 負責統一渲染風格，文字負責定調色盤。
2. **亮度靠文字語彙救**：加 `bright / high-key / luminous and airy / no dark shadows / no haze` 後 L 從 135 → 151。
3. **strength 過載無用**：1.4 反而更暗更冷（L90 暖−17）。**1.0 是甜蜜點**，且文字介入後 0.8 與 1.0 幾乎無差（暖 +49 vs +48）。
4. ⭐ **4 步 = 8 步**：R12 vs R8 數據幾乎相同，但 **27 秒 vs 54 秒**。配 4-step Lightning 就跑 4 步，多跑純浪費。

### R14 — 最佳配方 × 四種題材（一致性驗收）★

配方：dx8152 @1.0、4 步、image2 = `style_ref.png`、R11 的 prompt。

| 格 | 題材 | 原 L→新 | 原暖→新 | 原 S→新 |
|---|---|---|---|---|
| s01 | 人物特寫 | 192 → 153 | −77 → **+48** | 0.36 → 0.40 |
| s08 | 純幾何示意 | 240 → 214 | +17 → **+74** | 0.12 → 0.33 |
| s59 | 夜戲綠光 | 41 → 179 | −48 → **+88** | 0.86 → 0.44 |
| s70 | 場景插畫 | 197 → 174 | +58 → **+78** | 0.45 → 0.40 |

**離散度收斂**：

| 指標 | 原圖幅度 | 轉換後幅度 | 收斂倍數 |
|---|---|---|---|
| L | 199 | **61** | 3.3× |
| 暖 | 135 | **40** | 3.4× |
| S | 0.74 | **0.11** | 6.7× |

**但目視發現嚴重問題**：

- ❌ **s08（純幾何）**：style_ref 的**窗戶、盆栽、水壺全部被合成進畫面**。原本是一張乾淨的箭頭示意圖，變成「房間裡有一支箭頭」。
- ❌ **s59（夜戲）**：背景冒出 style_ref 的盆栽與窗戶。
- ✅ s01、s70：正常，無滲透。

→ 上個 session 的「image2 被當合成素材」故障**沒有被 `FluxKontextMultiReferenceLatentMethod` 完全消除**，只是被壓低。當 content 圖**稀疏（大片留白）或偏暗**時仍會復發——模型缺乏內容可對齊，就去抓 image2 的物件填空。

### R15 — 拿掉 image2（LoRA ＋ 純文字）★ 最終配方

同樣四題材，同樣 prompt（尾句改成 `Keep the exact composition, subjects and line work of the original.`），**移除 image2 與整條 style_ref 支線**：

| 格 | L | 暖 | S | 耗時 |
|---|---|---|---|---|
| s01 | 149 | **+65** | 0.37 | 20s |
| s08 | 228 | **+52** | 0.23 | 21s |
| s59 | 173 | **+93** | 0.46 | 20s |
| s70 | 178 | **+87** | 0.43 | 21s |

**對照 R14**：

| | 暖度幅度 | 平均暖度（目標 +72） | 耗時 | 物件滲透 |
|---|---|---|---|---|
| R14（有 image2） | 40 | +72 | 30s | ❌ 兩格滲透 |
| **R15（無 image2）** | 41 | **+74** | **20s** | ✅ **零滲透** |

**目視**：s08 保持乾淨的純幾何箭頭（無盆栽窗戶）、s59 保持原構圖（手臂＋綠光），全部四格無異物。

→ **image2 是淨負面**：貢獻約 19% 的色調傳遞，卻帶來物件滲透風險並多花 50% 時間。**拿掉它，一致性不變甚至更好。**

---

## 🏁 第一輪最終結論

### 對使用者原始需求的直接回答

> 「輸入一張 content 圖 + 一張 style 圖，把 content 轉成目標 style」

**實測結論：這個架構在目前可得的工具下不是最佳解。** 兩個原始候選：

- **QwenStyle（學術正解）**：可用但收斂力弱（暖只到 −61），且 2509 LoRA 跨版本掛 2511 有損耗。**降為備案。**
- **Sref / InStyle**：❌ **架構根本不符**，它是「用 style 圖的風格生成新圖」，內容來自文字。實測直接摧毀構圖（背景變格子布、人物換臉）。**排除。**

**真正可用的是第三個（原清單沒有的）**：`dx8152/Qwen-Image-Edit-2511-Style-Transfer`，2511 原生。

而且最有效的用法是**只用它的 LoRA、不餵 style 圖**——用 LoRA 統一渲染風格 + 用文字定調色盤。風格一致性的來源從「同一張參考圖」換成「同一個 LoRA + 同一段文字」，一樣是硬鎖，而且更穩。

### 推薦配方（R15）

- workflow：[qwen_edit_2511_style_lora_transfer.json](../../comfyUI_workflow/qwen_edit_2511_style_lora_transfer.json)
- LoRA：`qwen_edit_2511_style_transfer_dx8152.safetensors` @ **1.0**
- KSampler：**4 步** / cfg 1 / euler / simple / **denoise 1.0**
- prompt：見 workflow 的 `_prompt_recommended`
- **20 秒/格** → 71 格約 **24 分鐘**

### 已知殘留問題

1. **亮度仍偏低**：平均 L≈182，目標 203。可再調文字或事後提亮。
2. **夜戲格會被轉成白天**：s59 從 L41 變 L173，敘事上不合理。→ 用既定的 `use_transfer` 逐格開關處理，夜戲格關掉。
3. **輕微霧感/發光**：LoRA 先驗會加一點 glow 與漸層，s08 的平塗箭頭變成有漸層。
4. **尺寸**：輸出 1368×760，原圖 1600×896。`ImageScaleToTotalPixels` megapixels 調 1.43 可解，未測。

---

## 第二輪：R16–R22（把參考圖路線探索到底）

> 逐項圖文報告：[report_02.html](report_02.html)

### 與官方 workflow 的接線比對（使用者要求釐清）

逐節點拆解 dx8152 官方 workflow JSON 後：**接線結構完全相同**（refmethod、image1/image2 對應、latent 來源、1MP 縮圖、cfg/sampler/scheduler/denoise 全部一致）。只有兩項不同：

| 項目 | 官方 | 本專案 | 影響 |
|---|---|---|---|
| Lightning LoRA | 2512-Lightning-4steps | 2511-Lightning-4steps | 2512 版在 lightx2v 官方 repo 不存在；2511 才是配 2511 底模的正解 |
| UNET 量化 | `QWEN_Image_Edit_2511_fp8mixed` | `Qwen-Image-Edit-2511-FP8_e4m3fn` | 量化方式不同，未測影響 |
| 步數 / 強度 | 8 / 0.8 | 4 / 1.0 | R10/R12/R13/R19 已驗證兩者皆可 |

⚠️ **但查到一件比接線更重要的事**：Civitai 官方教學明說這個 LoRA 的用途是 **lineart → styled illustration**（「Clean outlines work best」）。餵已上色的完整圖是離開訓練分佈的用法。→ R21 據此測了線稿路線，結果見下。

### R16–R19：用 prompt 攻擊物件滲透（全數失敗）

探針 s01（人物）＋ s08（滲透最嚴重）。

| tag | 變因 | s08 暖 | s08 目視 |
|---|---|---|---|
| R16 | 換官方英文 prompt | +73 | ❌ 窗戶盆栽水壺全在 |
| R17 | ＋英文明確禁搬物件 | +71 | ❌ 照樣全搬 |
| R18 | ＋中文明確禁搬物件 | +70 | ❌ 照樣全搬 |
| R19 | 純官方原味（無色票、str0.8、8步） | **+15** | ⚠️ 幾乎沒變化 |

**結論**：
1. ❌ **文字禁止指令對滲透完全無效**。三種措辭（英文、中文、明確列舉「不要搬植物／窗戶／家具」）全部無用。這是模型層級行為，prompt 管不到。
2. ⚠️ **沒有色票文字時，LoRA 對稀疏圖幾乎不動作**。所以不是「參數太猛才滲透」——是**要嘛沒作用、要嘛整組搬過來**，中間沒有安全地帶。
3. 官方英文與中文 prompt 在數據與目視上無可觀察差異。

### R20 — 無物件風格板 ★★ 命中根因

把 `assets/style_ref.png` 右側的**牆面＋地板**裁出來鏡像拼接成 `assets/style_image/style_ref_abstract.png`（L215 暖+91 S0.37），**沒有任何可辨識物件**，但保留原本的筆觸與配色。

| 格 | 暖 原→新 | 目視 |
|---|---|---|
| s01 | −77 → +55 | ✅ 正常 |
| s08 | +17 → **+68** | ✅✅ **滲透完全消失**，乾淨的幾何箭頭配暖米背景 |

→ **滲透的元兇不是「餵參考圖」這個機制，而是「參考圖裡有可辨識的物件」。**

### R21 — 線稿路線（LoRA 官方用途）❌ 不可用

content → 線稿 → dx8152 上色（配 `style_ref.png`），60 秒/格。

暖度數據最漂亮（s01 **+70**、s08 **+71**，最貼近目標 +72），但代價太大：

- ❌ **人物識別跑掉**：s01 的銀髮變成棕髮，臉也年輕了
- ❌ **幾何圖被重新詮釋**：s08 的箭頭被畫成一塊木板
- ❌ **滲透照舊**（因為參考圖仍是有物件的 style_ref）
- ❌ 60 秒/格，是 R22 的兩倍

線稿階段丟失的顏色與材質資訊回不來，上色階段就自由發揮。

### R22 — 無物件風格板 × 四題材（參考圖路線完整驗收）★

| 格 | L 原→新 | 暖 原→新 | S 原→新 | 目視 |
|---|---|---|---|---|
| s01 | 192 → 157 | −77 → **+56** | 0.36 → 0.39 | ✅ 銀髮、藍衣藍椅、機器面板全保留 |
| s08 | 240 → 222 | +17 → **+68** | 0.12 → 0.29 | ✅ 乾淨幾何箭頭，無異物 |
| s59 | 41 → 172 | −48 → **+90** | 0.86 → 0.46 | ✅ 構圖完整，無異物（但夜戲轉白天） |
| s70 | 197 → 174 | +58 → **+89** | 0.45 → 0.44 | ✅ 最佳 |

**三個候選配方正面對比**：

| 配方 | 參考圖 | 亮度幅度 | 暖度幅度 | 秒/格 | 物件滲透 | 符合原架構 |
|---|---|---|---|---|---|---|
| R14 | style_ref（有物件） | 61 | 40 | 30 | ❌ 兩格中鏢 | ✅ |
| R15 | 無 | 79 | 41 | **20** | ✅ 零 | ❌ |
| **R22** ★ | **無物件風格板** | **65** | **34** | 31 | ✅ **零** | ✅ |

**R22 同時滿足三件事**：符合 content＋style 雙圖架構、零滲透、離散度三者最小。代價是比 R15 慢 50%（71 格 37 分鐘 vs 24 分鐘）。且**可換性更高**——換風格只要換一張風格板，不用重寫 prompt，對之後做「推測格第二套色票」很有用。

---

## 第三輪：工程迭代（S / P / G / Q 系列，約 40 次實驗）

> 逐項圖文報告：[report_03.html](report_03.html)
> 實驗台：scratchpad `lab.py`（全參數化）、`colorxfer.py`（色彩轉移）、`pipeline.py`（兩階段管線）

### 新增自動量測

- **內容分數**：輸入與輸出的 Sobel 邊緣圖正規化互相關。校準值：InStyle 摧毀構圖 = 0.060、s08 有滲透 = 0.682、乾淨 = 0.773。**只能同格互比**。
- **風格分數**：與參考圖在 (L, 暖, S) 空間的貼合度。**後來證實會被 gaming**，見教訓 21。

### S1 — `reference_latents_method` 全掃描 ★

用**有物件的 style_ref.png**（真實使用情境）測四種模式：

| refmethod | s08 內容分數 | 滲透 |
|---|---|---|
| **offset** | **0.864** | ✅ 無 |
| **uxo/uno** | **0.867** | ✅ 無 |
| index | 0.697 | ❌ 有 |
| off | 0.680 | ❌ 有 |
| index_timestep_zero（官方指定） | 0.693 | ❌ 有 |

→ **只換一個下拉選項，滲透就消失**。不需要 report 02 的特製無物件板。官方指定的 `index_timestep_zero` 反而是最糟的。
→ 代價：offset 的風格傳遞較弱，且**夜戲格完全收不動**（L41→50）。

### S2–S3 — 自建 `ReferenceLatent` 架構

假設：滲透來自 style 圖的**空間 reference latent**，不是 VLM 的語義理解。

| 架構 | 內容均 | 風格均 | 暖幅 | 秒 |
|---|---|---|---|---|
| S2 官方接法＋offset | 0.547 | 0.587 | 47 | 28 |
| **S3 `vlm_content_ref`** — encoder 不接 vae（兩圖只進 VLM）＋ `ReferenceLatent` 只補 content 空間 latent | **0.620** | 0.682 | 36 | **19** |
| S3b `vlm_only` — 完全不給空間 latent | 0.317 | **0.853** | **20** | **14** |

→ **取捨軸**：空間 latent 給越多 → 內容越保留、風格越收不動；給越少 → 反之。`vlm_content_ref` 是最佳折衷（s08 內容 0.940、銀髮保住、19 秒）。

### S4 — cfg > 1 讓 negative prompt 生效

發現 **cfg=1.0 代表 negative prompt 從頭到尾無效**。拉到 1.5–3.0 後內容分數小幅提升（0.62→0.66），但 **Lightning LoRA 配 cfg>1 會產生畫面邊緣亮框瑕疵**，耗時加倍。不採用。

### S5–S6 — 分離「圖的貢獻」與「文字的貢獻」★★★ 核心診斷

把 prompt 裡所有顏色字眼拿掉，只留 `Change the style of Figure 1 to the style of Figure 2.`：

| 設定 | s01 暖 | s59 L | 暖幅 |
|---|---|---|---|
| 有色票文字 | +56 | 172 | **34** |
| 無色票・offset | **−60** | **30** | 135 |
| 無色票・index | −33 | 73 | 112 |
| 無色票・uxo/uno | −60 | 30 | 135 |
| 無色票・index_timestep_zero | −24 | 33 | 93 |
| 無色票・vlm_content_ref | −48 | 36 | 63 |

→ **拿掉顏色文字後，沒有任何一種接線能收斂。真正在驅動風格的是文字，不是圖。**
→ style 圖只以 384×384 視覺 token 進 VLM，色彩訊息太弱，在內容豐富的圖上完全推不動。唯一例外是 s08（幾乎全白）。

### S7–S9 — 放大 style 訊號（六種手段全滅）

QwenStyle 官方正方 1024／style 餵兩次／解析度加倍／插槽反轉／雙 LoRA 疊加／`ImageStitch` 拼接——**全部無效或更糟**。

→ style 訊號弱不是「量」的問題，是**模型根本沒學會從圖萃取色盤並套用到複雜內容上**。

### 第十三組 — 換路：確定性色彩轉移（自寫，不靠模型）

寫了 LAB 色彩空間的統計轉移（`colorxfer.py`，毫秒級、不用 GPU）：

| 方法 | 暖幅 | 內容均 | 目視 |
|---|---|---|---|
| reinhard 全匹配 | **3** | — | ❌ 全部洗白、s59 變米糊 |
| keep_luma=1.0（只搬色度） | 15 | 0.95–0.999 | ⚠️ 局部色彩壓成單一米黃 |
| **grade（只搬平均色偏，保留原圖色彩變化幅度）** | **13** | **0.97–0.999** | ✅ 局部色彩全保留、整體暖化 |

→ ★★ **色盤統一用程式做比用模型做好一個量級**：暖幅 13（模型最好 34）、內容 0.99（模型最好 0.62）、0 秒（模型 20–31 秒）。
→ 而且它**真的是圖驅動**，換任何一張 style 圖都自動適應。
→ s59 夜戲維持夜戲、綠光還在——正中 Q1 的決策「只統一調色」。

### 第十四組 P/G — 兩階段管線（色彩轉移 × 擴散）

| 管線 | 暖幅 | 內容均 | 風格均 | 目視 |
|---|---|---|---|---|
| P2/P3 擴散 → reinhard | 3–5 | 0.42–0.49 | **0.98** | ❌ 洗白 |
| G2/G3 擴散 → grade | 2–5 | 0.40–0.43 | 0.98 | ❌ 綠斑、色調分離 |
| G1 grade → 擴散 | 56 | 0.486 | 0.427 | ✅ 乾淨但調色被推回 |
| G5/G6 grade → 擴散（LoRA 0.6/0.3） | 63–79 | 0.47–0.51 | — | ❌ s08 被漂白 |

→ ❌ **擴散之後再調色一定會壞**（擴散輸出直方圖窄，再拉伸就 8-bit 量化爆掉）。
→ ✅ 調色放擴散之前畫質乾淨，但擴散會把調色成果推回去。
→ **色彩與筆觸這兩件事在這套模型上無法同時最佳化。**

### 第十五組 Q — 依 QwenStyle 論文修正（使用者提供）

[論文](https://openreview.net/forum?id=Cgb7JpOA5Q)就是我們下載的模型的原始技術報告。三項明文規定：

1. 訓練/推論固定 prompt：`Style Transfer the style of Figure 2 to Figure 1, and keep the content and characteristics of Figure 1.`
2. 失敗時的加強句型：`Transfer Figure 1 into XXX style.`（XXX = 已知風格名，例 Van-Gogh），可強化風格保真度
3. **⚠️ 我原本做錯的**：style 圖必須縮成 **min(輸出高, 輸出寬) 的正方形**（我們是 760×760）。我之前用 1024×1024 或等比例 1MP

| # | 設定 | 暖幅 | 判定 |
|---|---|---|---|
| Q1 | QwenStyle 完全照論文（760 正方） | 56 | ❌ 仍收不動 |
| Q2 | 加強句型含 "warm sand" | **39** | ❌ **s01 變成仙人掌沙漠** |
| Q4 | 純風格名詞 `flat vector illustration style` | 97 | ❌ 收不動 |
| Q5 | `Transfer Figure 1 into the style of Figure 2.` | 204 | ❌ 收不動 |
| Q6 | dx8152 ＋ 760 正方 ＋ 純風格名詞 | 105 | ❌ 收不動 |

→ 760 正方確實是我原本的錯誤，改正後 QwenStyle 有進步但**仍收不動**。
→ Q2 的加強句型能改善收斂，但那本質仍是文字驅動，且踩到物件幻覺地雷。
→ **連論文作者自己的模型、照論文自己的設定，也做不到純圖驅動。**

---

## 🏁 第三輪最終結論

1. ★★★ **「content 圖 + style 圖 → 圖驅動的風格轉換」在目前這兩個模型上做不到。** 不是接線問題——refmethod 四種、空間 latent 三種架構、插槽五種排列、拼接、雙 LoRA 疊加、解析度加倍、論文官方設定全部試過。只要 prompt 沒有顏色文字，一律收不動。
2. ✅ **但「色盤統一」可以完全由 style 圖驅動**——用程式讀 LAB 統計做 grade 轉移。暖幅 13、內容 0.99、0 秒。
3. ⚠️ **「筆觸/畫風統一」只能靠 LoRA 擴散**，但它套的是 LoRA 自己烘焙的風格，與給的 style 圖無關。
4. ❌ 兩者串接沒有免費午餐。

| 方案 | 色盤由 style 圖驅動 | 畫風統一 | 暖幅 | 內容 | 秒/格 | 目視 |
|---|---|---|---|---|---|---|
| **grade 色彩轉移（純程式）** | ✅ **完全** | ❌ | **13** | **0.99** | **0** | ✅ |
| S3 `vlm_content_ref` ＋ 色票文字 | ⚠️ 弱 | ✅ | 36 | 0.62 | 19 | ✅ |
| R22 無物件板 ＋ 色票文字 | ⚠️ 弱 | ✅ | 34 | 0.48 | 31 | ✅ |
| S1 offset ＋ 色票文字 | ⚠️ 弱 | ✅ | 47 | 0.55 | 28 | ✅（夜戲收不動） |
| G1 grade → 擴散 | ⚠️ 部分 | ✅ | 56 | 0.49 | 27 | ✅ |

---

## 第四輪：QwenStyle 忠實複現 ★ 前三輪的結論被推翻

> Skill 說明：[implementation-notes.md](../../.claude/skills/style-transfer-qwenstyle/references/implementation-notes.md)
> 新測試素材：`assets/style_image/style_ref_1~6.png`（六種截然不同的強特徵畫風）

### ⚠️ 重大更正：前三輪「模型做不到圖驅動風格轉換」的結論是錯的

前三輪一律用 `assets/style_ref.png` 當風格參考——**那是一張七成空白、近乎單色、低對比的米色牆**，風格訊號本來就極弱。用它下的通則性結論不成立。

換成六張有明確特徵的風格圖後，**同一個架構、同一批模型，六種風格全部轉換成功**。

**這是本專案最大的方法錯誤：用單一且病態的樣本下通則性結論。**

### 從官方 Space 原始碼挖到的實作真相

[Space app.py](https://huggingface.co/spaces/witcherderivia/QwenStyle/blob/main/app.py) 逐行拆解後，發現三件事：

**1. 用 Qwen2.5-VL 跑兩次 caption**（就是 `pipe.text_encoder` 本身，同一顆模型兼任 caption 與 text encoding）。兩句指令：

```
content : describe main objects (fewer than 3) with separated words,
          each word is separated by comma,  the total number of words is strictly fewer than 3
style   : describe only the artistic style, material and stroke in 5 words, not objects.
```

⭐ **style 指令結尾的 `not objects.`** ——官方把「不要描述物件」寫進指令裡。這跟本專案 Q2 踩到的雷（prompt 寫 `warm sand` → 醫療艙變仙人掌沙漠，教訓 25）是同一件事，作者早就知道並堵住了。

組法：`固定句 , content caption , style caption`（逗號串接）。

**2. 論文的「style 圖縮成正方形」已被作者自己推翻。** app.py 裡 `#style_ref.resize((minedge, minedge))` **被註解掉了**，實際做法是 content 與 style 都等比例縮到最短邊 = minedge、長邊取 16 倍數。Space 較新，以 Space 為準。→ 我第三輪 Q 系列照論文做的 760 正方形也是錯的。

**3. `minedge` 是風格強度旋鈕**，Space 說明明寫「changing the minedge could lead to different style similarity」，預設 1024，範圍 256–2048。論文沒提。

### 六種風格實測（底模 2511，非原生 2509）

| # | 風格圖 | VLM 產生的 caption | 結果 |
|---|---|---|---|
| 1 | 賽璐珞霓虹夜景 | `Digital art, pixelated, smooth lines, vibrant colors.` | ❌ 變成像素藝術 → caption 誤判，覆寫後修好 |
| 2 | 黑白漫畫網點 | `Black and white manga, fine lines, detailed shading.` | ✅ 真正的網點漫畫，排線、速度線俱全 |
| 3 | 韓系可愛平塗 | `Cartoonish, digital illustration, smooth lines, pastel colors, whimsical.` | ✅ 乾淨粉彩平塗 |
| 4 | 3D 公仔 | `Cartoonish, plasticine, smooth, detailed, expressive.` | ✅ 整個場景變成黏土定格動畫 |
| 5 | 膠彩工筆 | `Traditional ink wash painting.` | ✅ 水墨潑灑、宣紙質感、自動蓋印章 |
| 6 | 暗調電影 | `Dark, moody, cinematic, grainy, textured.` | ✅ 深青綠、顆粒、厚重 |

六格的構圖、人物、椅子、機器面板、氣瓶、管線**全部保留**。

### 圖 vs 文字的貢獻（NOCAP 對照組）

拿掉兩段 caption、只留固定句：

| | 只給圖 | 圖 + caption |
|---|---|---|
| ref_4 黏土 | 3D 卡通渲染，但**沒有黏土質感** | 全場景黏土紋理 |
| ref_2 黑白漫畫 | 漫畫線稿，但**還是藍色的** | 真正的黑白網點 |

→ **style 圖傳遞「大類別」（3D 渲染／線稿），caption 釘死「決定性屬性」（黏土材質／黑白）。兩者都有實質貢獻。**

這比前三輪「只有文字有效」的結論精確得多——前三輪的錯誤源於參考圖太弱，圖那一半根本沒機會表現。

### caption 誤判是真實且必須處理的失效模式

`style_ref_1.png` 是賽璐珞霓虹夜景，VLM 把**壓縮噪點讀成「pixelated」**，模型忠實照做輸出 8-bit 像素藝術。覆寫成 `Anime cel shading, neon glow, bold outlines, high contrast.` 後立刻正確。

→ skill 必須保留人工覆寫出口。caption 快取在 `assets/style_profiles.json`，可直接編輯或用 `--set` 覆寫。

### 建置的產物

> 2026-08-05 起已全部搬進正式 skill：`.claude/skills/style-transfer-qwenstyle/`（觸發詞：「風格轉換」「把這張圖轉成那個風格」）。以下為搬移後的位置。

| 檔案 | 作用 |
|---|---|
| [.claude/skills/style-transfer-qwenstyle/SKILL.md](../../.claude/skills/style-transfer-qwenstyle/SKILL.md) | skill 入口：流程、旋鈕、陷阱 |
| [scripts/style_caption.py](../../.claude/skills/style-transfer-qwenstyle/scripts/style_caption.py) | VLM caption 層，兩句指令照抄 Space，含 `--set` 人工覆寫 |
| [scripts/qwenstyle_run.py](../../.claude/skills/style-transfer-qwenstyle/scripts/qwenstyle_run.py) | 執行層：caption → 組 prompt → 尺寸規則 → 送件 → 量測 |
| [workflow/qwenstyle_v1_2509.json](../../.claude/skills/style-transfer-qwenstyle/workflow/qwenstyle_v1_2509.json) | 2509 底模 + QwenStyle LoRA + Lightning |
| [references/implementation-notes.md](../../.claude/skills/style-transfer-qwenstyle/references/implementation-notes.md) | 完整實作細節（原 docs/style-transfer-skill.md） |
| `data/style_profiles.json` | caption 快取 |
| `D:\models\qwen_vl_venv\` | VLM 專用永久 venv（transformers 4.57.6） |

VLM 跑在 `--system-site-packages` 的獨立 venv（transformers 4.57.6，對齊 Space 的 4.57.3），**系統 Python 未變動**（仍 4.46.2）。

### ⚠️ 陷阱：官方附的 Lightning LoRA 在 ComfyUI 靜默不載入

QwenStyle repo 附的 `diffsynth_...Lightning-4steps` 與 lightx2v 的同名檔案：`alpha` 與 `lora_up` hash 相同，但 **`lora_A`/`lora_down` 的 hash 與命名都不同**。

一開始我判斷「既然 repo 特地附了自己那顆，就用他們的」——**這個判斷是錯的**。

實測結果：用 diffsynth 版跑 2509，六種風格**全部偏軟、糊、低對比**，明顯不如 2511 的結果。log 完全沒有警告。換成 lightx2v 的 ComfyUI 標準命名版本後，同一組設定立刻銳利（ref_5 變成整段實驗最漂亮的水墨畫）。

原因：diffsynth 格式的 key 是 `lora_A.default.weight`，**ComfyUI 靜默不載入**。4 步沒有加速 LoRA 就是欠煮的糊圖。那顆是給 Space 的 diffusers pipeline 用的，不是給 ComfyUI 用的。

→ 這正是教訓 6 記過的坑，換個位置又踩了一次。**「官方附的」不等於「你的 runtime 能用的」。**

### 2509 vs 2511 最終對照（配正確的 Lightning）

| 指標 | 2511 | 2509 原生 |
|---|---|---|
| 內容分數均值 | 0.207 | **0.333**（高 60%） |
| ref_5 水墨 | 好 | **最佳**：濕筆暈染、飛白、印章 |
| ref_6 電影感 | 好 | **更好**：90 年代賽璐珞質感、底片顆粒與邊框 |
| ref_4 黏土 | 黏土紋理明顯 | 3D 玩具渲染，更乾淨但黏土感略減 |

→ **2509 原生底模確實較佳**，尤其在筆觸細節與內容保留上。跨版本損耗是真的。

---

## 待測 / 待辦

- [ ] **2509 原生底模的對照**（下載中）：同 seed 同 caption 重跑六種風格，量化「跨版本損耗」到底有多大
- [ ] `minedge` 風格強度旋鈕的完整掃描（已測 768/1024/1280，需目視比較）
- [ ] 把這套接回分鏡稿主流程（71 格批次、`use_transfer` 開關、編輯器按鈕）
- [ ] 使用者拍板：純 grade 調色 vs S3 擴散 vs 兩者並存逐格選
- [ ] 若選擴散路線：S3 `vlm_content_ref` 尚未做完整四題材的目視驗收（只看過 s01/s08/s70）
- [ ] 未測的旋鈕：`ModelSamplingAuraFlow` 的 shift（固定 3.0）、Lightning LoRA 強度（固定 1.0）、sampler/scheduler 其他組合
- [ ] 未測：把 grade 的參考統計改成「只取 style 圖的前景區域」，避開大片空白牆造成的偏差
- [ ] 舊有待辦：R22（無物件風格板）vs R15（無參考圖）
- [ ] 亮度再調（目標 L 203，現 182）
- [ ] 霧感/glow 抑制（negative prompt 目前是空字串，可利用）
- [ ] **尺寸**：megapixels 1.43 測試
- [ ] 推測格第二套色票（降飽和偏冷版）
- [ ] 全 71 格試跑 + `scripts/transfer.py`
- [ ] 備案未測：`zooeyy/Style-Transfer`（2511，563MB）、`svjack Sref`（2509）

---

## 累積教訓速查

1. **denoise 必須 1.0**。內容保留靠 `TextEncodeQwenImageEditPlus` 的 reference latent，不是靠低 denoise。低 denoise 會退化成複製機。（前 session）
2. **雙圖風格轉換必須加 `FluxKontextMultiReferenceLatentMethod`**，否則 image2 被當合成素材。（R1）
3. InStyle 這類「Sref」LoRA 是 *style 圖＋文字→生成*，不是 *content 圖＋style 圖→轉換*，選型時要看 prompt 格式而不是看標籤。（R7 實測證實）
4. LoRA 能做到「內容保留」不等於能做到「跟隨參考圖風格」——這是兩個獨立能力，要分開驗證。（R1）
5. **測 image2 有沒有作用，一定要用「極端」參考圖**。用兩張同類型的參考圖（都是暖色平塗板）差異太小，會誤判成「完全無效」——R1/R2 就差點讓我下錯結論，R5 才翻案。（R5）
6. **ComfyUI 的 LoRA key 不合會靜默略過、照樣出圖**。三個候選的 key 前綴各不相同（`transformer.` / 裸 `transformer_blocks.` / `diffusion_model.`），所以每次換 LoRA 都要跑一次「無 LoRA 對照組」確認它真的有生效，不能只看圖有變就當作有效。（R4）
7. **風格轉換要拆成兩個獨立能力來驗收**：色調／光線（可從 image2 傳遞）vs 筆觸／渲染（由 LoRA 的先驗決定，image2 影響不到）。（R5）
8. ⭐ **圖鎖與文字是互補、不是二選一**。單靠 LoRA 讀參考圖只能把暖度拉到 −27；加上文字色票立刻到 +44。LoRA 管「怎麼畫」，文字管「用什麼顏色畫」。（R8）
9. ⭐ **image2 在這個任務上是淨負面**。它只貢獻約 19% 色調傳遞，卻會在 content 稀疏或偏暗時把參考圖的物件合成進畫面，而且多花 50% 時間。拿掉後一致性不變、滲透歸零。（R14 vs R15）
10. **一致性驗收一定要跨題材跑**。只看人物格（s01）會得出「完美」的錯誤結論——s08 純幾何與 s59 夜戲才暴露出物件滲透。單一探針圖會漏掉最嚴重的故障。（R14）
11. **配 4-step Lightning 就跑 4 步**。8 步的數據與 4 步幾乎相同但耗時兩倍，純浪費。（R10/R12）
12. **LoRA strength 過載會反噬**。1.4 比 1.0 更暗更冷，離目標更遠。1.0 是甜蜜點；且一旦文字介入，0.8 與 1.0 差異可忽略。（R9/R13）
13. ⭐⭐ **參考圖必須「無可辨識物件」**。滲透的根因不是餵參考圖這個機制，而是參考圖裡有物件可抄。同一套參數，把參考圖換成無物件的純風格板，滲透從「整個房間搬進來」變成「完全沒有」。**選風格參考圖時，要選只有配色與筆觸、沒有主體的圖。**（R20/R22）
14. ⭐ **文字禁止指令擋不住物件滲透**。英文、中文、明確列舉物件名稱，三種措辭全數無效。這是模型層級行為，不要浪費時間調 prompt 措辭。（R16–R18）
15. **沒有色票文字時，LoRA 對稀疏圖幾乎不動作**。行為是二元的：要嘛沒作用、要嘛整組搬過來，中間沒有安全地帶。所以「調低參數避免滲透」這條路不通。（R19）
16. **線稿路線會丟失身分特徵**。轉線稿時顏色與材質資訊消失，上色階段就自由發揮——銀髮變棕髮、幾何箭頭變木板。暖度數據雖然最漂亮，但不能只看數據。（R21）
17. **要跟官方 workflow 比對時，直接下載它的 JSON 逐節點拆**，不要只讀 model card。dx8152 的 HF card 沒提到 `FluxKontextMultiReferenceLatentMethod`，也沒提到它是為線稿設計的——前者在 workflow JSON 裡，後者在 Civitai 教學裡。（第二輪調查）
18. ⭐⭐ **`reference_latents_method` 要全掃過，官方指定值未必最好**。`offset` / `uxo/uno` 能消除物件滲透，官方指定的 `index_timestep_zero` 反而最糟。這一個下拉選項的影響超過前面調過的所有 prompt。（S1）
19. ⭐⭐⭐ **要判斷「圖」還是「文字」在出力，就把文字裡的目標描述整段拿掉再跑**。這一步之前，所有「成功」案例都可能是文字的功勞被誤記在圖上。做完才發現：40 次實驗裡沒有任何一種接線能靠圖收斂。（S5/S6）
20. **cfg=1.0 時 negative prompt 完全無效**。用 Lightning LoRA 就是 cfg 1，所以 negative 欄位一直是裝飾。拉高 cfg 能讓它生效但會產生邊緣亮框瑕疵。（S4）
21. ⭐⭐⭐ **自動指標會被 gaming，只能拿來篩選不能拿來判定**。風格分數 0.98（全場最高）的 P3/G2，圖是一片糊白加綠色雜斑。每一輪都要抽圖人工看。（P3/G2）
22. ⭐ **確定性的程式解法要先於模型解法考慮**。色盤統一用 LAB 統計轉移，比整套擴散模型好一個量級（暖幅 13 vs 34、內容 0.99 vs 0.62、0 秒 vs 30 秒），而且真的是圖驅動。花了 30 幾次擴散實驗才想到寫 20 行 numpy。（第十三組）
23. **統計匹配要匹配對的東西**。全域均值/標準差匹配會洗白（參考圖是低對比空房間）；只搬「平均色偏」、保留原圖自己的色彩變化幅度，才是「調色」而不是「洗白」。（CX vs CG）
24. **擴散之後不要再做色彩拉伸**。擴散輸出直方圖窄，再拉伸就 8-bit 量化爆掉，出現綠斑與色調分離。要調色就調在擴散之前。（G2/G3）
25. ⭐ **色票文字只能用「純色彩形容詞」，不能用「材質/物質名詞」**。`warm sand` 會被畫成實體沙漠（s01 醫療艙 → 仙人掌沙漠）。terracotta、brass 同樣是地雷。（Q2）
26. **論文的推論設定要逐句照做**。QwenStyle 論文明寫 style 圖要縮成 `min(輸出高,寬)` 的正方形——我原本用 1024 正方或等比例 1MP，兩種都錯。（Q 系列）
27. **降 LoRA 強度不是萬用的「少改一點」旋鈕**。強度 0.6/0.3 時 s08 直接被漂白，比 1.0 更糟。（G5/G6）
28. ⭐⭐⭐ **不要用單一樣本下通則性結論**。前三輪四十幾次實驗都用同一張病態參考圖（近乎單色的空房間），據此判定「模型做不到圖驅動風格轉換」——換成六張強特徵風格圖後全部成立。**測試素材本身的品質，是實驗結論的上限。**（第四輪）
29. ⭐⭐ **要複現一篇論文，去找它的 demo 原始碼，不要只讀論文**。QwenStyle Space 的 app.py 裡有三件論文沒寫或已被推翻的事：VLM 雙 caption 的確切指令、正方形 style 圖已被作者註解掉、minedge 是風格強度旋鈕。論文是快照，demo 才是現況。（第四輪）
30. ⭐ **官方把「not objects」寫進 caption 指令裡**——這跟本專案第三輪自己踩出來的教訓 25 是同一件事。**踩到坑之後，回頭去看官方有沒有早就防範，通常有。**（第四輪）
31. **VLM 會看錯，而且錯得很合理**。它把 JPEG 壓縮噪點讀成「pixelated」，模型忠實照做輸出像素藝術。任何自動 caption 流程都必須留人工覆寫出口，並在每次換素材時檢查一次。（第四輪）
32. **圖與文字各司其職**：style 圖傳遞「大類別」（3D 渲染／線稿／水墨），caption 釘死「決定性屬性」（黏土材質／黑白／筆觸）。只給圖會得到對的類別但錯的材質；只給文字會失去參考圖的細節。（NOCAP 對照組）
34. ⭐⭐ **「官方附的」不等於「你的 runtime 能用的」**。QwenStyle repo 附的 diffsynth 格式 Lightning LoRA 在 ComfyUI **靜默不載入**（log 零警告），六種風格全部變成欠煮糊圖。換成 lightx2v 的 ComfyUI 標準命名版立刻正常。官方檔案是給他們自己的 diffusers pipeline 用的。（第四輪）
35. **糊圖／低對比／缺乏銳利度 = 先懷疑加速 LoRA 沒生效**，不要先去調 prompt 或 shift。4 步取樣沒有 Lightning LoRA 就是欠煮。（第四輪）
33. **邊緣互相關的內容分數不適合跨風格比較**。風格轉換本來就會大幅改變邊緣圖，分數低不代表構圖流失——六種風格的分數都在 0.12–0.48，但構圖其實全部保留。這個指標只能在同一風格內比較。（第四輪）
