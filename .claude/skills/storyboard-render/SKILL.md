---
name: storyboard-render
description: 把分鏡稿送進 ComfyUI 出圖，並自動接第二階段統一畫風。當使用者說「出圖」「生成圖片」「重新出圖」「重生某幾格」「統一畫風」「轉風格」時使用。需要 ComfyUI 在 127.0.0.1:8188 運作。
---

# storyboard-render｜出圖

**輸入**：`output/<系列>/<系列>.json`
**輸出**：`output/<系列>/images/content/` ＋ `output/<系列>/images/transfer/`

獨立於分鏡稿生成，因為**失敗性質完全不同**——前面壞是「規範沒寫清楚」，
這裡壞是「ComfyUI 沒開／模型沒載／seed 不好」。分開才知道哪層壞了。

---

## 兩個階段

| 階段 | 做什麼 | 產物 | 預設 |
|---|---|---|---|
| **1 生成 content image** | 文字 prompt（＋角色參考圖）→ 新畫面 | `images/content/<id>.png` | 開 |
| **2 統一畫風** | content image ＋ 風格參考圖 → 換畫風 | `images/transfer/<id>.png` | **開** |

階段 2 在 `style.json` 的 `style_ref` 留空時會自動略過，所以「預設開」不會在沒設風格圖時卡住。

階段 2 是**呼叫 `style-transfer-qwenstyle` skill**，不是在這裡重寫一份實作。
風格轉換自己的坑（caption 看錯、LoRA 靜默不載入）由那支 skill 負責，這裡只負責編排。

**兩階段刻意分開跑完，不逐格交錯**——flux2 與 Qwen-Image-Edit 不能同時待在 16GB VRAM 裡，
交錯等於每格換兩次模型。階段 1 全部跑完才進階段 2，中間會請 ComfyUI 卸載模型。

---

## 怎麼跑

```bash
python -X utf8 scripts/render.py --series <系列名>
```

這一行就會**兩階段都跑完**。其他用法：

```bash
python -X utf8 scripts/render.py --series <系列名> --ids s07,s12 --seed 4242 --no-skip
python -X utf8 scripts/render.py --series <系列名> --no-transfer     # 只跑階段 1
python -X utf8 scripts/render.py --series <系列名> --transfer-only   # 圖已出好，只轉風格
```

腳本會自動：檢查 ComfyUI 在線 → 上傳角色參考圖 → 依 `workflow` 欄位分流 →
跳過 `needs_post_text` 與已存在的圖 → 存成 `output/<系列>/images/content/<id>.png` →
卸載 flux2 → 逐格轉風格存成 `output/<系列>/images/transfer/<id>.png`。

ComfyUI 離線時腳本會直接停下並要求啟動，**不會硬跑**。重啟後 port 可能變動，
連不上先 `netstat -ano | grep LISTENING` 找實際 port。

---

## 階段 1：生成 content image

### 兩條 workflow（已實測跑通）

| `workflow` | 檔案 | 用於 |
|---|---|---|
| `text_only` | `comfyUI_workflow/flux2_text_to_image.json` | 畫面上**完全沒有人**的格 |
| `text_with_character` | `comfyUI_workflow/flux2_text_image_to_image.json` | 畫面上**有任何人**的格（含路人、群眾、一隻手） |

**兩條共用 `flux-2-klein-base-4b`**，參考圖經 `ReferenceLatent` 掛進正向條件。
同模型 → 線條、描邊、上色邏輯天然一致。約 40–50 秒／張。

被腳本改寫的節點：`20` 正向、`21` 負向、`43` seed、`40`/`41` 尺寸、`10` 參考圖檔名。
改 workflow 時**不要動這些節點編號**，否則腳本會找不到。

### 三條實測結論

**1. 文字描述產不出一致的人。**
純文字路徑畫出來的觀察者會走鐘成完全不同的東西。
**路人也一樣**——比例、五官簡化程度、線條密度都會跟參考圖路徑畫出來的不同調，
一支影片裡有人的格分走兩條路徑，人就會有兩種畫法。
**凡是畫面上有人的格，一律走 `text_with_character`，沒有例外。**

> ⚠ 代價：**掛了參考圖的格，畫面上的人都會長得像觀察者**，連 staging 一個字都沒提他的格
> 也會憑空長出他的臉。這是已知且接受的行為，用文字排除無效（實測見
> `storyboard-depiction` 的「決定 workflow」）。看到路人同臉不要重出換 seed，換不掉。

**2. 參考圖的米白素底會滲進輸出。**
帶角色的格若背景寫得模糊（「同一條街」），整張會褪色發白，跟相鄰的純文字格明顯不同調。
背景寫具體就撐得住。這條規則寫在 `storyboard-staging`——出圖端無法補救，
**看到褪色要回 staging 改，不要在這裡換 seed 硬試。**

**3. 構圖詞的控制力弱。**
`rule-of-thirds composition with the subject on the left third` 常被忽略，主體仍置中。
景別與視角的控制力則正常。要主體偏一邊時，改用場面調度描述空間關係，別只靠構圖詞。

### 參數

- 尺寸、步數、cfg、sampler 全部取自 `assets/style.json` 的 `model` 區塊
- `negative` 逐字取自 `style.json`，不要自己加減
- 不指定 `--seed` 時，每格用 id 推導出固定 seed（同一格重跑會得到同一張）

---

## 階段 2：統一畫風

用來解 flux2 的固有問題：**同一支影片的格之間畫風會漂移**。
這在階段 1 補救不了（換 seed、改 prompt 都改不動），只能靠第二階段收斂。

### 前置設定

1. **`assets/style.json` 的 `style_ref`** 指向風格參考圖。**留空則階段 2 自動略過**
2. 該張參考圖要先有 style caption。沒有的話腳本會擋下來並印出指令：

```bash
D:/models/qwen_vl_venv/Scripts/python.exe -X utf8 \
  .claude/skills/style-transfer-qwenstyle/scripts/style_caption.py \
  --kind style --images "<風格參考圖>"
```

⚠️ **產完一定要人工複核**——VLM 會看錯（實例：把壓縮噪點讀成 pixelated，輸出就真的變像素風）。
錯了用 `--set` 覆寫。細節見 `style-transfer-qwenstyle`。

### 逐格開關

分鏡稿加 `use_transfer` 欄位控制，**沒寫視為 true**。

**夜戲格要設 `false`**——實測夜景轉換後會被打亮成白天（亮度 41 → 172），敘事上不對。

### 旗標

| 旗標 | 作用 |
|---|---|
| `--no-transfer` | 只跑階段 1（快速迭代 prompt 時用） |
| `--transfer-only` | 跳過階段 1，只跑階段 2 |
| `--transfer-redo` | 連已存在的 `transfer/<id>.png` 也重做 |
| `--transfer-content-prompt` | 也用 VLM 產生每格的 content caption（**71 格會很慢且需 VLM venv**，預設關） |
| `--transfer` | 已是預設行為，保留只為相容舊指令 |

### 成本

階段 2 約 34 秒／格，71 格多花約 40 分鐘。
反覆調 prompt、重生單格時記得加 `--no-transfer`，最後定稿再跑完整的一輪。

### 兩個目錄都留

`images/content/<id>.png` 與 `images/transfer/<id>.png` 並存，**transfer 是交付品**。
原圖留著才能換風格重轉、或在轉壞時回頭比對。

檔名兩邊一致（都是 `<id>.png`），靠目錄分辨，不用 `_transfer` 後綴。

---

## 重生單格

使用者說「重生 s07」時：

1. 只取那幾格組成單場景清單
2. 換 seed 重出
3. 若是 prompt 本身有問題（不是 seed 運氣），**回 `storyboard-compose` 改 prompt**，
   不要在這裡臨時改字串——改了不寫回分鏡稿，下次重跑又會跑掉

若該格已有 `transfer/s07.png`，重出後要加 `--transfer-only --ids s07 --transfer-redo` 重轉，
否則交付品還是舊風格的那張。

---

## 注意事項

- **不要用 `Start-Process` 脫離工作階段**；用一般 `run_in_background`
- 內嵌 `python -c` 加 `-X utf8`，避免 Windows cp950 編碼錯誤
- 跑完回報：階段 1 的出圖／跳過（含 `needs_post_text`）／失敗張數；有跑階段 2 就一併回報轉換成功與失敗數
- 階段 2 的產物**不要拿去比對 prompt**（`storyboard-verify-image` 要看的是 `content/<id>.png`，
  轉換後的圖畫風已經不同，比對會誤判）
