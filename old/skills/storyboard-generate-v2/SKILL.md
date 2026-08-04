---
name: storyboard-generate-v2
description: v2 分鏡稿生成（平塗風格、固定角色、固定場景庫）。當使用者說「用 v2 生成分鏡稿」「生成 X 分鏡稿 v2」「新流程生成分鏡」等需求時使用。四階段：語音稿→場景清單→六段式prompt→出圖→看圖驗證。需要 ComfyUI 在 127.0.0.1:8188。舊系列（軍人等）請改用 storyboard-generate。
---

# storyboard-generate-v2

工作目錄 `D:\Cowork\分鏡稿`。**與舊版 `storyboard-generate` 並存**，舊版規範（`語音稿轉提示詞規範.md`、`分鏡稿規範.json`）v2 完全不使用，也不要去改它們。

## 與舊版的差別

| | 舊版 | v2 |
|---|---|---|
| 模型 | anima-base-v1.0 | `flux-2-klein-base-4b` |
| 風格 | 靠長串 style token 描述，每張漂移 | 寫死的平塗尾綴，風格高度穩定 |
| 提示詞 | token 堆疊 ＋ 否定詞塞正向 | 六段式自然語言，否定詞全在 negative |
| 角色 | 具名角色 ＋ 參考圖 | 單一主角，純文字描述複用 |
| 環境 | 每格即興 | 場景庫，同場景共用同一段描述 |
| 內容 | 抽象隱喻 | 具體場景優先 |

## 固定資產（不要每格重寫，逐字複用）

| 檔案 | 內容 |
|---|---|
| `v2/style.json` | 模型、尺寸、平塗尾綴、negative、**量化景別詞表** |
| `v2/character.json` | 主角外觀 ＋ 現代／科幻／遠古三套服裝 |
| `v2/scene_library.json` | 場景庫（`env_en` ＋ `palette_en`），累積式 |
| `v2/PROMPT_RULES.md` | 六段式結構、內容規則、驗證清單 |

## 流程

### 0. 前置
`curl -s http://127.0.0.1:8188/queue` 確認 ComfyUI 在線，離線就請使用者啟動，不要硬跑。

### 階段一：語音稿 → 場景清單
沿用舊版的 `場景切分規範.md`（切分邏輯 v2 沒有改變）。額外要做兩件事：

1. **先決定這支影片的 3–6 個場景**，寫進 `v2/scene_library.json`（含 `env_en` 與 `palette_en`）。已存在的場景直接複用，不要新建近似的。
2. 每格指定它屬於哪個場景。

輸出 `v2/json/<系列>/s01.json` … `sNN.json`，每格欄位：
```json
{"id":"s01","scene":"標題","dialogue":"…","source":"…","focus_hint":"…","scene_key":"夜晚書房","era":"現代"}
```
`scene_key` 必須對得上 `scene_library.json` 的鍵。

### 階段二：場景 → 六段式 prompt
讀 `v2/PROMPT_RULES.md` ＋ 三個固定資產檔，逐格處理：讀 `sXX.json` → 寫 `prompt` 與 `claims` → 跑驗證清單（A1–A3、B1–B3、C1–C4）→ 立即寫回同檔。

**只啟動一個 subagent 跑完全部場景。**

### 階段三：出圖
merge 成單一清單後執行（風格參數全部來自 `style.json`）：
```
python generate.py --input v2/json/prompt_list_<系列>.json --output v2/images_<系列> --workflow image_flux2_text_to_image_9b --width 1600 --height 900 --variants 1 --negative "<style.json 的 negative>"
```
**不要用 `Start-Process`**；用一般 `run_in_background`。

### 階段四：看圖驗證
逐格 Read 圖片，比對 `claims`。任一不成立就重生：**先診斷原因、調 prompt，再換 seed**，每格最多 5 次。5 次仍不過就記進 `_verify/FAILED.json`，把失敗圖移到 `failed/`，繼續下一格。

驗證重點（POC 已知會出問題的地方）：
- 景別是否符合指定的量化描述（最常跑掉）
- 角色臉型／髮型是否明顯走鐘
- 是否出現左右分割的拼貼構圖
- 服裝是否變成全身同色

## 選配：換風格（預設關閉）

平塗是預設成品。要換畫風才用：
```
python v2/style_transfer.py --content <平塗圖> --anchor v2/anchors/anc1_texture.png --out <輸出> --seed <N>
```
錨圖**必須是質感區塊**，不能是完整錨圖——完整錨圖會把裡面的道具一起搬進成品。

## 注意事項

- 內嵌 `python -c` 加 `-X utf8`，避免 Windows cp950 編碼錯誤。
- 驗證以圖為準：圖中沒明確呈現的 claim 就判「否」。
- 改了 `character.json` 或 `scene_library.json` 之後，**要回階段二重寫受影響場景的 prompt**，否則出圖用的還是舊描述。
