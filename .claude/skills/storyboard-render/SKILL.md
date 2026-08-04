---
name: storyboard-render
description: 把分鏡稿送進 ComfyUI 出圖。當使用者說「出圖」「生成圖片」「重新出圖」「重生某幾格」時使用。需要 ComfyUI 在 127.0.0.1:8188 運作。
---

# storyboard-render｜出圖

**輸入**：`output/<系列>/<系列>.json`
**輸出**：`output/<系列>/images/`

獨立於分鏡稿生成，因為**失敗性質完全不同**——前面壞是「規範沒寫清楚」，
這裡壞是「ComfyUI 沒開／模型沒載／seed 不好」。分開才知道哪層壞了。

---

## 怎麼跑

```bash
python -X utf8 scripts/render.py --series <系列名>
```

其他用法：

```bash
python -X utf8 scripts/render.py --series <系列名> --ids s07,s12 --seed 4242 --no-skip
```

腳本會自動：檢查 ComfyUI 在線 → 上傳角色參考圖 → 依 `workflow` 欄位分流 →
跳過 `needs_post_text` 與已存在的圖 → 存成 `output/<系列>/images/<id>.png`。

ComfyUI 離線時腳本會直接停下並要求啟動，**不會硬跑**。重啟後 port 可能變動，
連不上先 `netstat -ano | grep LISTENING` 找實際 port。

---

## 兩條 workflow（已實測跑通）

| `workflow` | 檔案 | 用於 |
|---|---|---|
| `text_only` | `comfyUI_workflow/flux2_text_to_image.json` | 觀察者**不**出現的格 |
| `text_with_character` | `comfyUI_workflow/flux2_text_image_to_image.json` | 觀察者出現的格 |

**兩條共用 `flux-2-klein-base-4b`**，參考圖經 `ReferenceLatent` 掛進正向條件。
同模型 → 線條、描邊、上色邏輯天然一致。約 40–50 秒／張。

被腳本改寫的節點：`20` 正向、`21` 負向、`43` seed、`40`/`41` 尺寸、`10` 參考圖檔名。
改 workflow 時**不要動這些節點編號**，否則腳本會找不到。

---

## 三條實測結論

**1. 文字描述產不出一致的角色。**
純文字路徑畫出來的觀察者會走鐘成完全不同的東西。
**凡是觀察者出現的格，一律走 `text_with_character`，沒有例外。**

**2. 參考圖的米白素底會滲進輸出。**
帶角色的格若背景寫得模糊（「同一條街」），整張會褪色發白，跟相鄰的純文字格明顯不同調。
背景寫具體就撐得住。這條規則寫在 `storyboard-staging`——出圖端無法補救，
**看到褪色要回 staging 改，不要在這裡換 seed 硬試。**

**3. 構圖詞的控制力弱。**
`rule-of-thirds composition with the subject on the left third` 常被忽略，主體仍置中。
景別與視角的控制力則正常。要主體偏一邊時，改用場面調度描述空間關係，別只靠構圖詞。

---

## 參數

- 尺寸、步數、cfg、sampler 全部取自 `assets/style.json` 的 `model` 區塊
- `negative` 逐字取自 `style.json`，不要自己加減
- 不指定 `--seed` 時，每格用 id 推導出固定 seed（同一格重跑會得到同一張）

---

## 重生單格

使用者說「重生 s07」時：

1. 只取那幾格組成單場景清單
2. 換 seed 重出
3. 若是 prompt 本身有問題（不是 seed 運氣），**回 `storyboard-compose` 改 prompt**，
   不要在這裡臨時改字串——改了不寫回分鏡稿，下次重跑又會跑掉

---

## 注意事項

- **不要用 `Start-Process` 脫離工作階段**；用一般 `run_in_background`
- 內嵌 `python -c` 加 `-X utf8`，避免 Windows cp950 編碼錯誤
- 跑完回報：出圖張數、跳過張數（含 `needs_post_text` 的）、失敗張數
