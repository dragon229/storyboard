# 頻道色卡候選

每個檔案是一組完整色卡，七個角色鍵一致，因此可以整組抽換而不動下游。
同名的 `.png` 是預覽圖，直接看資料夾縮圖就能比。

| slug | 名稱 | 一句話 |
|---|---|---|
| `warm-teal` | 暖米青 | 從現有出圖裡挑對的部分立成規則，親切、補色關係 |
| `cool-slate` | 冷灰藍 | 理性資料感，但跟頻道定位偏冷 |
| `bright-pop` | 高彩紙感 | 縮圖最跳，撐一整支片會吵 |
| `blueprint-lab` | 藍圖實驗室 | 科學。工程藍圖而非白袍實驗室 |
| `starfield` | 星空 | 深底淺線稿，識別度最高，也最好守一致性 |
| `whimsy` | 天馬行空 | 讓紫色扛「這是想像的」 |
| `retro-future` | 過去未來 | 上一代人想像的未來 |

## 角色鍵

底色三選一，由分鏡稿的資料決定，不是逐格美感判斷：

| 條件 | 用哪個底 |
|---|---|
| `is_speculation = true` | `推演底` |
| `framing.vocabulary = 圖解` | `圖解底` |
| 其餘 | `現實底` |

`角色` 每格都套。`高亮` 一格最多一個——否則就沒有高亮。

線稿有兩支：底色亮時用 `線稿`，底色暗時（多半是圖解格，`starfield`
則是每一格）用 `反白線稿`，否則線會糊進背景。這條可以由亮度自動判斷，
不必逐格寫，`scripts/palette_preview.py` 的 `luminance()` 就是這樣做的。

## 欄位

- `hex` — 給編輯器與人看的。
- `en` — 實際串進 prompt 的句子。色名在前、hex 在後，是因為還沒實測
  `qwen_3_4b` 對 hex 的遵守程度。若實測 hex 無效甚至干擾，就把括號拿掉，
  只留色名。

## 重畫預覽

```
python -X utf8 scripts/palette_preview.py [--slug warm-teal]
```

## 出圖時指定色卡

```
python -X utf8 scripts/render.py --series <系列> --palette whimsy --no-transfer
```

圖出到 `output/<系列>/images/content_whimsy/`——**不會蓋掉原本的 `content/`**，
同一份分鏡稿可以並排比好幾組色卡。分鏡稿檔本身不動，prompt 只在記憶體裡重組。

色卡句組在 `scripts/palette.py`（角色鍵選擇＋亮度判斷線稿），
接在 `compose.py` 的風格尾綴之後。`assets/style.json` 的 `palette` 欄位
可以設頻道預設；`null` 代表不套，行為與加色卡之前一致。

## 顏色的三個來源，只留一個

2026-08-07 對 if_test_2 whimsy 的 22 格逐格量測，色卡失守有三個來源，
已經一起收掉：

| 來源 | 症狀 | 處理 |
|---|---|---|
| `staging` 逐格寫死顏色 | 7 格底色完全失守，色差最高 236 | `storyboard-staging` 立規則：**不寫任何色相詞** |
| `character.json` 寫死赭紅毛衣 | 8 格帶著 `muted dusty terracotta` 跟色卡對撞 | 服裝與外觀的色相全部拿掉 |
| 參考圖經 ReferenceLatent 帶進自己的顏色 | 有完整人物的格，線稿一律變回黑、毛衣變回赭紅 | 每組色卡各出一套參考圖，見下 |

改完之後同樣那幾格重出：推演底的色差從 193 / 227 / 236 降到 18 / 21 / 17。

## 各色卡版本的角色參考圖

```
python -X utf8 scripts/character_palette.py [--slug whimsy] [--preview]
```

產出 `assets/character_ref/<slug>_<real|spec|diagram>.png`，每組色卡三張，
對應三種底——參考圖的素底會滲進輸出，底色不一致的話圖解格會被米白拉淡。
`render.py --palette` 會自動依每一格的底色挑對應那張上傳，規則跟色卡選底色同一條。

原圖 `assets/character_ref.png` **不要動**，那是所有版本的來源；換了它就要重取
`character_palette.py` 裡的九個錨點色。`_preview_<slug>.png` 是三種底並排的對照圖。

換色是逐像素重映射，不是換色相濾鏡，所以角色的造型與線條完全不動。皮膚不進色卡
（色卡沒有膚色這個角色鍵，臉一起換掉角色就不像人了）。
