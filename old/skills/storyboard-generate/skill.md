---
name: storyboard-generate
description: 從語音稿生成分鏡稿圖片並用「看圖驗證」確保每張圖符合提示詞。當使用者說「生成軍人分鏡稿」「生成 X 分鏡稿」「把語音稿轉成分鏡」「重新生成分鏡稿」「生成並驗證分鏡稿」「storyboard generate」等需求時，務必使用此 skill。四階段流程：語音稿→場景清單→完整prompt+claims（LLM）→圖片→看圖驗證。需要 ComfyUI 在 127.0.0.1:8188 運作。
---

# storyboard-generate（分鏡稿生成＋看圖驗證）

工作目錄固定為 `D:\Cowork\分鏡稿`。

## 核心心智模型：四階段，每階段都是 A + B + C = D

整條流程是四個「輸入 + 工具/規範 + 執行者 = 產物」的轉換串起來。每個階段的產物是下一階段的輸入。**出問題時，先定位是哪一個階段的產物錯了，再回到那一階段修**。

| 階段 | A（輸入） | B（規範/工具） | C（執行者） | = D（產物） |
|------|----------|----------------|-------------|-------------|
| **一 切分** | 語音稿全文 | `場景切分規範.md` | LLM（預設 **opus**） | 場景清單（`id`/`scene`/`dialogue`/`source`/`focus_hint`） |
| **二 寫提示詞** | 場景清單 ＋ `分鏡稿規範.json`（參考） | `語音稿轉提示詞規範.md` | LLM（預設 **sonnet**） | 完整 `prompt`（含世界觀/環境/供電/角色/喪屍的智能組合）＋ `claims` |
| **三 生成** | `prompt` | — | `generate.py`（無 LLM） | 圖片 |
| **四 驗證** | 圖片 ＋ `claims` | — | LLM（預設 **sonnet**，看圖＋比對） | 逐條 pass/fail |

## 檔案分工

| 角色 | 檔案 | 負責 |
|------|------|------|
| **切分規範** | `場景切分規範.md` | 階段一：語音稿 → 場景清單 |
| **提示詞規範** | `語音稿轉提示詞規範.md` | 階段二：場景 → 完整 `prompt` + `claims`（含 block 組合判斷規則） |
| **參考資料** | `分鏡稿規範.json` | 階段二 LLM 的參考資料：風格前綴、環境描述、供電門檻、角色外觀、喪屍分型、破壞素材 |
| **執行器** | `generate.py` | 階段三（送 ComfyUI 出圖）＋ 階段四輔助（`--emit-claims`、sidecar） |

## 參數

主要輸入是**一份語音稿**（例如 `軍人視角_v2.md`）。從使用者訊息取得語音稿檔案；再決定一個**系列名稱**（例如 `軍人_v3`），用來命名各階段的產物：

- 語音稿（階段一輸入）：使用者指定的 `.md` / `.txt` 檔
- 場景清單 / 提示詞（階段一～二產物）：`json/<系列>/s01.json` … `sNN.json`（逐格獨立 JSON，每格一檔）；Stage 3 前 merge 為 `json/prompt_list_<系列>.json`
- 圖片（階段三產物）：`images_<系列>`
- 生成模式：每場景一張用 `--variants 1`（明說要 4 張變體才用 `--batch 4`）

語音稿或系列名稱不明確時先問清楚。若使用者已有現成的 `json/<系列>/` 場景資料夾（只要重生/重驗證），可從對應階段接手，不必從語音稿重跑。

## 指令判讀：「根據 XXX 生成分鏡稿」該從哪一階段起跑

這是最容易判斷錯誤的地方——同一句話可能對應「從語音稿全新跑五階段」或「用既有系列重新出圖」兩種完全不同的動作，**判斷依據是使用者給的名稱究竟指向哪一種檔案，不能用字串相似度亂猜**：

1. **預設規則：沒給副檔名時，把名稱當成語音稿檔名，即 `<name>.md`。**
   例如「根據 軍人視角_v2 生成分鏡稿」→ 先檢查 `軍人視角_v2.md` 是否存在。存在就代表這是**全新四階段流程的起點**（語音稿→場景清單→prompt+claims→出圖→驗證），系列名稱另外跟使用者確認或依語意合理推斷（例如去掉「視角」等修飾詞、或直接問）。
   - **不要**因為 `json/` 底下有名稱相近的資料夾（例如 `軍人_v2/`、`軍人_v2_pro/`）就誤判成「使用者要重跑既有系列」。資料夾名稱相近 ≠ 同一份東西；`<name>.md` 存在就以它為準，這是唯一可靠訊號。
2. **只有下列情況才視為「接手既有系列」（跳過階段一，甚至跳過階段二）**：
   - 使用者明確給的名稱**精確對應**一個已存在的 `json/<系列>/` 資料夾（資料夾名稱完全相符，不是相似），**且**
   - 使用者話裡有「重生」「重新出圖」「重新驗證」「compose」「這個系列」等明確指向既有產物的字眼，而不是單純「生成分鏡稿」。
3. **兩者都可能成立時（`<name>.md` 與同名資料夾都存在）**：先問使用者是要「從語音稿整條重跑」還是「用既有場景資料夾重新出圖」，不要自行猜測。
4. **`<name>.md` 不存在、也找不到精確同名資料夾** 時，列出候選（有的 `.md`、有的 `json/<系列>/` 資料夾）請使用者選，不要挑一個相似的直接用。

> 這條規則存在的原因：曾發生使用者說「根據 軍人視角_v2 生成分鏡稿，輸出目錄 images_軍人_v2_pro_v2」，但因為 `json/軍人_v2/`（舊系列）名稱相近而被誤用，導致直接跳到階段四用舊格式生成，完全繞過階段一～三、也沒套到最新規範。正確做法應該是發現 `軍人視角_v2.md` 存在 → 這是語音稿 → 從階段一開始跑完整四階段。

## 各階段入口參數（可從任一階段接手）

這條流程不必每次都從語音稿跑到底。使用者若指出「某階段有問題」，直接從**那一階段**接手，只重跑它與其下游。先判斷使用者的請求對應哪一階段，再取所需輸入：

| 從這階段起跑 | 需要的輸入（A） | 使用者可能的說法 | 執行 |
|--------------|-----------------|------------------|------|
| **一 切分** | 語音稿檔（`.md`/`.txt`）＋系列名 | 「把這份語音稿轉成分鏡」「重新切場景」「場景切太細/太粗」 | 讀 `場景切分規範.md` 重切 → 逐格寫出 `json/<系列>/s01.json`…`sNN.json`（id/scene/dialogue/source/focus_hint） |
| **二 寫提示詞** | `json/<系列>/` 資料夾＋要處理的場景範圍；`分鏡稿規範_slim.json`（參考） | 「s16 的焦點不對」「重寫這幾張」「提示詞有問題重寫」「改了角色/環境/供電後重寫」 | 讀 `語音稿轉提示詞規範.md` + `分鏡稿規範_slim.json`，逐格讀 `json/<系列>/sXX.json`、加入 `prompt`/`claims`/`no_characters`、立即寫回同檔 |
| **三 生成** | `json/prompt_list_<系列>.json`（merge 後）＋系列名；可指定場景子集與 `--seed` | 「重生 s16」「全部重新出圖」「換 seed 再生一張」 | 先 merge `json/<系列>/` → `json/prompt_list_<系列>.json`，再 `python generate.py --input <清單> --output images_<系列> --variants 1 [--no-skip --seed N]` |
| **四 驗證** | `images_<系列>/` 圖片 ＋ `json/<系列>/sXX.json` 的 `claims`（或 `_verify/<id>.json`） | 「驗證這些圖」「檢查 s16 有沒有符合提示詞」 | 逐場景 Read 圖片，逐條比對 claims |

**接手時的注意事項**：
- 從**階段二**改完 `prompt` → 先 merge 再進階段三重生。
- 改了 `分鏡稿規範.json`（角色外觀/環境文字）→ 也要重跑階段二，讓 LLM 用新資料重寫受影響場景的 prompt。
- 只處理部分場景時，直接讀寫 `json/<系列>/sXX.json` 對應的幾個檔案即可，不需要另建整份清單。
- 系列名稱決定產物路徑；使用者沒明說要新系列時，沿用現有 `json/<系列>/` 資料夾就地修改。

## LLM 階段的模型指定

用到 LLM 的三個階段（一切分、二寫提示詞、四驗證），**每個階段只啟動一個 subagent**。模型選擇透過 skill 參數或使用者指定（可選 `opus4.8` / `sonnet4.6` / `sonnet5` / `haiku` / `fable`）；不指定則使用 sonnet4.6 模型。

### 模型 Effort Level 選擇

| 模型 | Effort Level |
|------|-------------|
| opus4.8 | High |
| sonnet4.6 | High |

### 預設指派（起始假設，可實測後調整）

| 階段 | 預設模型 | Effort | 依據 |
|------|---------|--------|------|
| **一 切分** | `opus4.8` | High | 錯誤槓桿最高：切錯會連鎖污染下游全部場景；且一篇只跑一次，用最強模型划算。吃全局理解與判斷。 |
| **二 寫焦點** | `sonnet4.6` | High | 量大（77 格 × 最多 5 次重寫），任務是照規範精確執行、跑驗證清單，指令遵循為主。**若常過不了驗證清單、重寫次數偏高，升級為 `opus`**。 |
| **四 驗證** | `sonnet4.6` | High | 吃視覺理解與仔細比對；最怕弱模型「假陽性」寬鬆放行（該判否卻判是），讓驗證形同虛設，故用可靠的。 |

> 這組是**基於任務特性的推理，不是實測數據**。要驗證是否合適：拿 3–5 個場景，同階段用不同模型各跑一次比對品質，再定案。使用者可隨時覆寫（例如「階段二改用 opus」）。

## 性能監測：模型×Effort 成本追蹤

### 任務開始時宣告設定

每次啟動一個 LLM 階段（一切分、二寫提示詞、四驗證）**都要在回應最前面輸出一行宣告**，讓使用者清楚知道用了哪組設定：

```
[階段X | 模型: sonnet4.6 | Effort: High | 場景範圍: s26–s50]
```

這行宣告讓使用者在 FleetView 一眼能識別目前是哪個階段。

### 階段小結（每個 LLM 階段完成後必須輸出）

每個 LLM 階段完成後，在回應**結尾**輸出一份小結，格式如下：

**階段一（切分）小結：**
```
── 階段一小結 ──────────────────────
切出場景：80 格（s01–s80）
各時間段分布：Day3×8、Day10×4、Day14×9 …
需人工確認：0 格
耗時：6m 52s | tokens：88,288
────────────────────────────────────
```

**階段二（寫焦點）小結：**

若分批執行，每批 subagent 結束後輸出**批次小結**：
```
── 階段二 Batch 1/3 小結（s01–s40）──────
處理場景：40 格
設 no_characters：12 格
需人工確認：0 格
重寫次數：2 次（s07×1、s15×1）
耗時：5m 12s | tokens：38,210
──────────────────────────────────────────
```

全部批次完成後，主代理讀 `_perf_log.jsonl` 彙總，輸出**階段二總小結**：
```
── 階段二小結（全部批次合計）────────────
處理場景：123 格（s01–s123，共 3 批）
  Batch 1  s01–s40   38,210 tokens  5m 12s
  Batch 2  s41–s80   37,450 tokens  4m 58s
  Batch 3  s81–s123  36,890 tokens  5m 03s
設 no_characters：32 格
需人工確認：0 格
重寫次數：總計 5 次
耗時（含批次間隔）：15m 13s | tokens 合計：112,550
每格平均：915 tokens
────────────────────────────────────────
```

**階段四（驗證）小結：**
```
── 階段四小結 ──────────────────────
驗證場景：80 格
通過：74 格 | 失敗（5次仍不過）：2 格（s23、s45）
重生次數：換seed×12、改prompt×3
耗時：15m 04s | tokens：62,480
────────────────────────────────────
```

各批次 subagent 完成後把統計寫入**暫存檔**；全部批次跑完後主代理從暫存檔彙整進 `_perf_log.jsonl`，再刪除暫存。

### 性能日誌：perf_log.jsonl

主日誌檔案：`D:\Cowork\分鏡稿\_perf_log.jsonl`（一行一筆 JSONL）

每個 LLM 階段完成後，直接 append 一筆到 `_perf_log.jsonl`。

#### 每筆格式

```jsonl
{"ts":"2026-07-02T14:23:05+08:00","series":"軍人_v2_pro_v2","stage":2,"stage_name":"寫提示詞","batch":1,"batch_total":3,"scene_range":"s01-s40","model":"sonnet4.6","effort":"high","scene_count":40,"duration_sec":312,"total_tokens":38210,"input_tokens":31800,"output_tokens":6410,"note":""}
```

| 欄位 | 說明 |
|------|------|
| `ts` | ISO 8601 時間戳（完成時刻） |
| `series` | 系列名稱 |
| `stage` | 階段編號（1–4） |
| `stage_name` | 階段中文名（切分/寫提示詞/生成/驗證） |
| `batch` | 批次序號（1 起算）；階段一/四單批時填 `null` |
| `batch_total` | 本次執行的批次總數；單批時填 `null` |
| `scene_range` | 處理的場景範圍（`s01-s40`） |
| `model` | 實際使用的模型 ID |
| `effort` | 使用的 effort level |
| `scene_count` | 處理場景數 |
| `duration_sec` | 子代理執行秒數（從啟動到完成通知） |
| `total_tokens` | 總 token 用量 |
| `input_tokens` | 輸入 token |
| `output_tokens` | 輸出 token |
| `note` | 備注（可空白） |

**Token 來源**：從 Claude Code 介面的 token 計數取得；無法精確取得時填 `null`。

**目的**：累積足夠樣本後，可按 `stage` + `model` + `effort` + `batch` group by，比較每格平均 token 與品質（驗證通過率），找出性價比最佳組合。

## JSON 結構（每個場景）

```json
{
  "id": "s01",
  "scene": "Day 3｜命令紙送到連部",
  "dialogue": "第二營第三連……",
  "source": "（語音稿原文段落）",
  "focus_hint": "（階段一視覺主軸提示）",
  "location": "（階段一推斷地點，例：軍事連部室內）",
  "no_characters": true,
  "prompt": "完整最終提示詞（由階段二 LLM 組合）",
  "claims": [ {"label": "場景描述", "text": "…"}, … ]
}
```

- `no_characters: true`：物件焦點場景（prompt 含 `no people visible`）時加，讓 Stage 2 跳過角色與人物世界觀 block。
- `location`：階段一根據原文或前後文推斷的地點，**不可留空**。Stage 2 直接用此欄位決定環境 block，避免生圖模型自行填補地點而畫錯場景。
- `prompt` / `claims`：階段二 LLM 寫，直接送 ComfyUI。不再有 `pre_prompt` 欄位。

---

## 步驟

### 0. 前置
確認 ComfyUI 在線：`curl -s http://127.0.0.1:8188/queue`。離線就請使用者啟動（port 8188），不要硬跑。

### 階段一：語音稿 → 場景清單
讀 `場景切分規範.md`，依原則把語音稿切成場景清單。若使用者已有現成的 `json/<系列>/` 資料夾且只要重生，可跳過。

**輸出格式**：每個場景寫一個獨立 JSON 檔到 `json/<系列>/` 資料夾，**每格一個檔案**：

```
json/<系列>/s01.json
json/<系列>/s02.json
...
json/<系列>/sNN.json
```

每個檔案只含該格的六個欄位，不含 `prompt`/`claims`（那是階段二的工作）：

```json
{
  "id": "s01",
  "scene": "Day 3｜命令紙送到連部",
  "dialogue": "第二營第三連……",
  "source": "（語音稿原文段落）",
  "focus_hint": "（視覺主軸提示）",
  "location": "（推斷地點，例：軍事連部室內）"
}
```

全部格寫完後，輸出總數確認（例：`已切出 s01–s123，共 123 格`）。

### 階段二：場景 → 完整 prompt + claims

**前置（A 優化）**：先執行 `python prepare_stage2.py`，生成 `分鏡稿規範_slim.json`（去除說明欄位，體積約原檔 50%），再給 subagent 讀這份精簡版。

**逐格讀寫（B1 優化）**：subagent 在 session 開始時讀 `語音稿轉提示詞規範.md` ＋ `分鏡稿規範_slim.json` 一次，然後**逐格**執行：

1. 讀 `json/<系列>/sXX.json`（只含該格，不載入其他格）
2. 寫完整 `prompt`（7 個 block 的智能組合）＋ `claims`
3. 跑驗證清單（A1–A6、B1–B5、C1–C6），任一不過就改寫，最多 5 次；第 5 次仍失敗標記人工確認
4. 立即把 `no_characters`/`prompt`/`claims` 寫回 `json/<系列>/sXX.json`（直接 update 同一個檔案）
5. 讀下一格，不在 session 內累積已完成格的完整 prompt 文字

**單一 subagent 策略**：**永遠只啟動一個 subagent 跑完全部場景**，不論場景總數多少。

**不需要 merge 步驟**：每格處理完直接寫回 `json/<系列>/sXX.json`，主代理無需執行額外 merge（Stage 3 前另有 merge 步驟）。

**強制規則：景別 + 視角 + 構圖必須明確寫進 prompt**
每格 prompt 都必須從 `語音稿轉提示詞規範.md`「七大焦點類型 × 取景組合」表中，根據該格的焦點類型選一個組合，把**景別 + 視角 + 構圖**三個詞明確寫入 prompt 文字。不能只用隱含描述。

| 焦點類型 | 範例寫法 |
|---------|---------|
| 物件焦點 | `extreme close-up, front-facing horizontal angle, centered symmetrical framing` |
| 人物焦點 | `medium close-up, eye-level horizontal angle, rule-of-thirds framing with gaze space on one side` |
| 動作焦點（全身） | `medium shot, low-angle, diagonal composition with action direction aligned to the diagonal` |
| 環境焦點 | `wide establishing shot, eye-level, single-point perspective leading lines` |
| 關係焦點 | `medium shot two-shot, eye-level, subjects split left and right on the thirds` |
| 對比焦點 | `medium shot, eye-level, frame-within-frame composition` |

驗證清單新增一條 **C7**：prompt 中是否含有明確的景別詞（close-up / medium shot / wide shot / full shot 等）＋視角詞（eye-level / low-angle / high-angle / bird's-eye 等）＋構圖詞（centered / rule-of-thirds / diagonal / two-shot / over-the-shoulder 等）。三者缺一即不過，回去補寫。

**強制規則：不合理的人事物（物理現實檢查）**
驗證清單新增一條 **D1**：圖中是否出現違反物理現實的情況。以下任一出現即判「否」，進入重生：

- 人體部位扭曲：頭部與身體方向相差超過 90 度、手臂/腿從不可能的角度延伸、四肢數量錯誤
- 人物與物體融合：人體與車輛/牆壁/桌面互相穿插重疊（而非遮擋）
- 物體結構異常：建築物/車輛/武器出現不合理的彎曲、斷裂或多餘結構
- 空間邏輯矛盾：前景物體明顯「浮」在背景上、重力方向矛盾（物體往上掉落等）
- 臉部變形：五官位置錯誤（眼睛長在額頭、嘴巴偏離臉部中線超過明顯程度）

> 感染者的異常動作（低頭、扭曲姿態）屬於劇情設定，**不算違反現實**，不判否。判斷基準是「在這個世界觀下，這個姿勢/空間關係物理上是否可能」。

### 階段三：完整 prompt → 圖片

**前置（merge 步驟）**：先把 `json/<系列>/` 下的所有場景檔組合成 `json/prompt_list_<系列>.json`（generate.py 需要單一清單檔）：
```powershell
python -X utf8 -c "
import json, pathlib
scenes = sorted(pathlib.Path('json/<系列>').glob('s*.json'), key=lambda p: p.stem)
data = [json.loads(f.read_text(encoding='utf-8')) for f in scenes]
pathlib.Path('json/prompt_list_<系列>.json').write_text(
    json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Merged {len(data)} scenes OK')
"
```

merge 完確認輸出行數後，在 `D:\Cowork\分鏡稿` 以**一般背景方式**（run_in_background 綁定 session，**不要用 Start-Process 脫離工作階段**）執行：
```
python generate.py --input json/prompt_list_<系列>.json --output images_<系列> --variants 1
```
- 直接送 JSON 裡已組好的 `prompt`，**不再疊加**。
- 已存在的圖會跳過；要全部重生加 `--no-skip`。
- 每張圖存檔時寫 `images_<系列>/_verify/<id>.json`（優先用 JSON 裡的 `prompt`/`claims`）。
- ⚠ 若某場景無 `prompt` 欄位，生成時會警告並跳過——正常流程應先跑階段二。

### 階段四：看圖驗證（逐場景）

**前置（必讀）**：開始前先讀 `語音稿轉提示詞規範.md`「圖片驗證反覆不過時的構圖升級策略」章節，了解 prompt 調整的三種方向與移除描述的邊界條件。

**單一 subagent 策略**：**永遠只啟動一個 subagent 跑完全部場景**，不論場景總數多少。

對每個場景 `sXX`：
1. 取得 claims：優先讀 `json/<系列>/sXX.json` 的 `claims` 欄位；若該格尚未跑過階段二，改讀 `images_<系列>/_verify/sXX.json`。
2. 用 **Read 工具**讀 `images_<系列>/sXX_a.png`。
3. **逐一判斷每個 claim 是否在圖中成立（是／否）**。claims 涵蓋：場景描述、世界觀、環境、供電光線、破壞素材、喪屍數量、角色外觀。
4. 全部「是」→ 通過。任一「否」→ 進入重生。

### 重生（每場景最多 5 次）
**每次重生前，先分析失敗原因並調整 prompt，再重生**——不要只換 seed。

流程：
1. 根據失敗的 claim，診斷根因，從下列三個方向選擇調整策略（可組合）：
   - **構圖/鏡頭調整**：依 `語音稿轉提示詞規範.md`「構圖升級策略」的推論步驟，調整景別/視角/畫框填充語言
   - **補充細節描述**：在 prompt 補上讓關鍵元素更明確的描述
   - **移除錯誤描述**：移除大方向錯誤的描述（僅限以下兩類，其他一律用改寫取代）：
     - 場景中根本不該存在的人物（source 未提及、Stage 2 憑空加入的背景人物）
     - 違反場景設定的物件狀態（如停電場景中亮著的路燈、有電的螢幕等違反供電邏輯的描述）
2. 將調整後的 prompt 寫回 `json/<系列>/sXX.json`（直接更新同格場景檔），並建立 generate.py 用的單場景清單：
   ```powershell
   python -X utf8 -c "import json,pathlib; d=json.loads(pathlib.Path('json/<系列>/sXX.json').read_text(encoding='utf-8')); pathlib.Path('json/_re_sXX.json').write_text(json.dumps([d],ensure_ascii=False,indent=2),encoding='utf-8')"
   ```
3. `python generate.py --input json/_re_sXX.json --output images_<系列> --variants 1 --no-skip --seed <每次不同>`
4. 回階段四重新驗證。
- **每次重生後（無論成功或失敗）都要記錄調整日誌**，見下方「調整日誌」。

### 調整日誌（驗證失敗→修正的第一手資料）

每次因驗證失敗而調整 `prompt`（換 seed、改文字、改構圖/鏡頭）都要 append 一筆到 `images_<系列>/_verify/adjustment_log.jsonl`（JSONL，一行一筆），欄位：

| 欄位 | 內容 |
|------|------|
| `id` | 場景編號 |
| `attempt` | 第幾次嘗試（從 1 起算） |
| `failed_claims` | 這次驗證失敗的 claim 描述（症狀） |
| `diagnosis` | 為什麼失敗的根因判斷，**特別標注是否為鏡頭/取景/視角問題** |
| `change_type` | 這次調整的類型：`重新生成（同prompt換seed）` / `prompt矛盾修正` / `構圖升級（鏡頭/視角調整）` / 其他 |
| `change_description` | 具體改了什麼 |
| `outcome` | 下一輪驗證後回填：`fixed` / `still failed`（並簡述殘留問題） / `待驗證`（尚未進入下一輪） |

**這份 log 是之後檢討規範的第一手依據**：定期回看 `change_type=構圖升級` 且 `outcome=fixed` 的案例，找出真正有效的構圖手法補進規範；`outcome=still failed` 反覆出現的模式，代表規範目前沒覆蓋到的頑固問題，需要新增規則。

### 標記失敗
某場景 5 次後仍有 claim 不符：
1. 寫入 `images_<系列>/_verify/FAILED.json`（append）：場景 id、最後失敗的 claim、嘗試次數。
2. 將該場景最後一張失敗圖移入 `images_<系列>/failed/` 目錄，命名為 `sXX_a_<嘗試次數>.png`（例如 5 次失敗 → `s07_a_5.png`）。
3. 繼續下一個場景。

### 回報
跑完回報：通過張數／總數、失敗清單（哪些場景、哪個 claim 不符），提醒使用者可單獨處理。

### 任務結束總結

整個四階段流程全部跑完後，**必須向使用者輸出一份任務總結**，包含：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 任務總結｜系列：<系列名稱>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【圖片結果】
  總場景：80 格 | 通過：76 | 失敗：4
  失敗場景：s07、s23、s45、s61

【Token 消耗】
  階段一（切分）     opus4.8     88,288 tokens
  階段二（寫提示詞） sonnet4.6   88,935 tokens
  階段四（驗證）     sonnet4.6   ??,??? tokens
  ─────────────────────────────
  合計                          ???,??? tokens

【耗時】
  階段一：6m 52s
  階段二：10m 18s
  階段三（生成）：約 ?? 分鐘（ComfyUI）
  階段四（驗證）：??m ??s
  ─────────────────────────────
  LLM 總耗時：??m ??s

【每格平均】
  LLM token / 格：約 ?,??? tokens
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**數據來源**：從 `_perf_log.jsonl` 讀取各階段統計後彙總。若某階段尚無 perf 紀錄，標示 `N/A`，不要跳過整個總結。

---

## 修正問題時：定位到階段

| 症狀 | 是哪一階段 | 去改哪裡 |
|------|-----------|----------|
| 場景切太多/太少、主軸選錯 | 階段一 | `場景切分規範.md`＋重切場景清單 |
| 焦點描述不對、取景不對、多了/少了元素 | 階段二 | `語音稿轉提示詞規範.md`＋重寫該場景的 `prompt`（直接改 `json/<系列>/sXX.json`） |
| 世界觀/環境/供電/破壞/喪屍/角色外觀描述錯 | 階段二 | `分鏡稿規範.json` 確認正確描述後，回階段二重寫受影響場景的 `prompt` |
| 提示詞對但圖沒畫出來 | 階段三 | 換 seed 重生／構圖升級 |
| 圖對但驗證判斷有誤 | 階段四 | 以圖為準，claim 圖中沒明確呈現就判「否」 |

## 注意事項

- **不要用 `Start-Process` 脫離工作階段**；用一般 `run_in_background`。
- 內嵌 `python -c` 的 `print` 不要含特殊字元（如 `≤`），Windows cp950 會 `UnicodeEncodeError`；改用 `<=`、英數，或加 `python -X utf8`。
- ComfyUI 重啟後 port 可能變動；預設 8188，連不上先 `netstat -ano | grep LISTENING` 找實際 port。
- 驗證以圖為準：圖中沒有明確呈現某 claim 的內容，就判「否」。
- 改了 `分鏡稿規範.json`（角色外觀/環境文字）後，**務必回階段二重寫受影響場景的 `prompt`**，否則生成用的還是舊的描述。

