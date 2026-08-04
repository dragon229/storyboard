---
name: storyboard-compose
description: 把場面調度、取景、情緒與風格規範組裝成送 ComfyUI 的最終提示詞。由 storyboard 呼叫，或改了風格規範後要重組 prompt 時使用。
disable-model-invocation: true
---

# storyboard-compose｜組裝

**輸入**：`staging` ＋ `framing` ＋ `emotional_shift` ＋ `is_speculation` ＋ `assets/style.json`
**輸出**：`prompt`

薄，但不是純字串拼接——有幾條條件判斷。

**組裝本身已經實作在 `scripts/compose.py`**，編輯器與批次流程共用。
只要前面各步驟的欄位填對，直接跑就好，不要自己手拼字串：

```bash
python -X utf8 scripts/compose.py --series <系列名>
```

它會先驗證 `framing` 的每個鍵值都在 `style.json` 裡（填錯會擋下並指出哪一格），
再重算所有 `prompt`。標了 `prompt_manual: true` 的格會跳過，除非加 `--force`。

下面的規則是**這支 skill 的判斷依據**——填欄位時要照著判，`compose.py` 只負責機械拼接。

---

## 組裝順序

```
[取景句] , [場面調度] , [推演調性?] , [風格尾綴] , [情緒語句] , [全域禁止]
```

| 段 | 來源 | 條件 |
|---|---|---|
| **取景句** | `style.json` 的 `shot_sizes` / `angles` / `compositions` / `layouts` 等，依 `framing` 逐字取用 | 每格必有 |
| **場面調度** | `staging` 欄位 | 每格必有 |
| **推演調性** | `style.json` → `speculation_clause.text` | **僅** `is_speculation = true` |
| **風格尾綴** | `style.json` → `style_suffix` | 每格必有，逐字 |
| **情緒語句** | 由 `emotional_shift` 譯成英文片語 | 每格必有（無偏移就用符合頻道基調的中性片語） |
| **全域禁止** | `style.json` → `global_bans` 的 `text` 與 `frame` | **每格都加，兩條都加** |

`negative` 不寫進 prompt，出圖時另外送（見 `storyboard-render`）。

---

## 條件判斷

- **`is_speculation = true`** → 加推演調性子句。這是讓觀眾分辨真假的唯一機制，不能漏。
- **畫面無人物** → 加 `no people visible`。
- **`needs_post_text = true`** → prompt 裡明確保留空白區域的描述，且該格不送出圖。
- **`workflow = text_with_character`** → 場面調度裡必須含角色的 `base_en` 與依景別取段的服裝描述。

---

## 情緒語句

寫在風格尾綴之後，是一個簡短的英文名詞片語或形容詞組。

**不是裝飾**——它讓模型在光影、構圖、表情上做出情緒一致的選擇。沒有它，模型會選最中性的詮釋。

| 情緒偏移 | 片語範例 |
|---|---|
| 懸念 | `a held breath before the answer`, `quiet unresolved curiosity` |
| 意外 | `the small jolt of being wrong`, `an unexpected reversal` |
| 恍然 | `everything clicking into place`, `quiet satisfaction of understanding` |
| 餘韻 | `a thought left open`, `lingering quiet wonder` |
| 無偏移（基調） | `light everyday curiosity`, `easy inquisitive warmth` |

規則：
- 一格一個主要情緒，不要堆三個以上
- 避免直接把情緒當主語（✗ `sadness fills the room`）；改成狀態或氛圍（✓ `grief held silent`）
- 即使是資訊性的格也要有情緒，只是強度低

---

## 自檢清單

寫完每格逐條核對。**任一不過 → 改寫後重驗，最多 5 次；第 5 次仍失敗標記人工確認。**

| # | 檢查 |
|---|---|
| A1 | 取景句是否逐字取自 `style.json`，沒有自己改寫？ |
| A2 | 景別是否用**裁切位置**描述，而非「佔畫面幾分之幾」？ |
| A3 | 風格尾綴是否逐字寫入？ |
| A4 | 是否加了 `no text, no labels, no letters, no numbers`？ |
| A5 | 是否加了 `no letterboxing, no black bars, full bleed 16:9 frame`？ |
| B1 | `is_speculation = true` 的格，有沒有加推演調性？`false` 的格有沒有誤加？ |
| B2 | prompt 裡有沒有任何會產生文字的東西（招牌、螢幕內容、書名、標籤、數字）？ |
| B3 | 有角色的格：服裝是否依景別取對段落、且該段**整句**用上？ |
| B4 | 特寫／近景的格，prompt 有沒有提到鞋子或全身姿態？（提到就會反殺景別） |
| B5 | 場面調度是否只有**一個**焦點，沒有把兩件事塞進同一張？ |
| C1 | 結尾有沒有情緒語句？ |
| C2 | 原文提到的關鍵物件／動作，prompt 有沒有涵蓋？ |
| C3 | prompt 有沒有出現原文未提及、憑空加入的人物或元素？ |

---

## 輸出

逐格處理，寫完立刻存回 `output/<系列>/<系列>.json`。

跑完回報：完成格數、標記人工確認的格、標 `needs_post_text` 的格。
