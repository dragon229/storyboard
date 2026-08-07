---
name: storyboard-compose
description: 把場面調度、取景、情緒與風格規範組裝成送 ComfyUI 的最終提示詞。由 storyboard 呼叫，或改了風格規範後要重組 prompt 時使用。
disable-model-invocation: true
---

# storyboard-compose｜組裝

**輸入**：`focus` ＋ `staging` ＋ `framing` ＋ `emotional_shift` ＋ `is_speculation` ＋ `assets/style.json`
**輸出**：`prompt`

`focus`（畫面命題）**不進 prompt**——它是自檢清單 E1–E6 的比對基準。

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
- **畫面無人物** → 加 `no people visible`。這一格同時必然是 `workflow = text_only`。
- **`needs_post_text = true`** → prompt 裡明確保留空白區域的描述，且該格不送出圖。
- **`workflow = text_with_character`** → 表示畫面上有人，**不代表那個人是觀察者**。
  角色描述要不要寫，看的是**觀察者本人在不在畫面上**：

  | 畫面上的人 | staging 要寫 |
  |---|---|
  | 觀察者（不論主角或配角） | 角色的 `base_en` ＋ 依景別取段的服裝描述 |
  | **只有路人／群眾／一隻手** | 照一般人物寫「描述詞＋具體衣物＋顏色」，不寫 `base_en` |

  > ⚠ 掛了參考圖的格，路人的**臉本來就會像觀察者**，這是已接受的代價（實測與理由見
  > `storyboard-depiction` 的「決定 workflow」）。**不要寫排除句去對抗它，無效。**
  > 路人與觀察者的區別靠**服裝與動作**，不靠臉。

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
| B4 | 景別與姿態相容嗎？中景／特寫的格，姿態是不是躺／跪／盤腿／斜靠／走動？（是就會退回全身景。**刪掉「鞋子」「腳踝」這類詞救不回來**，要換姿態或換景別——見 `storyboard-framing`） |
| B4a | `shot_size` 是特寫或近景時，`framing.subject` 填了嗎？（沒填 `compose.py` 會擋下。留空等於讓模型自己補一張臉當主體） |
| B5 | 場面調度是否只有**一個**焦點，沒有把兩件事塞進同一張？ |
| **D1** | **圖解格：有沒有「兩個以上同類元素卻要它們某個屬性不同」？**（兩支反向箭頭、同一天平兩盤裝不同東西、三個面板填充程度遞增……都會被同質化，**改措辭修不好**，見 staging G1） |
| **D2** | 圖解格：每個元素都寫了**畫面位置或容器**嗎？有沒有用 `against` / `beside` / `between` 這種關係詞？（見 G2） |
| **D3** | 圖解格：`contrast_balance = 失衡` 的格，staging 有沒有把失衡寫成**幾何事實**（哪一邊在上緣、哪一邊在下緣）？只填欄位不寫幾何 → 模型畫水平（見 G3） |
| **D4** | 圖解格：抽象幾何元素（方塊／長條／箭頭／圓點）有沒有用數詞？（有語義的實體才能用數詞，上限 3；見 G4） |
| **D5** | 圖解格：有沒有「純抽象形狀」跟「有語義物件」擠在同一格？（抽象的那個會被吃掉，見 G5） |
| **D6** | 圖解格元素數 ≤ 3 嗎？ |
| **D7** | 有沒有寫到時鐘／錶面／鈔票／硬幣正面？（這三個會自己長出文字，`blank` 擋不住，見 staging 的全域禁止文字） |
| C1 | 結尾有沒有情緒語句？ |
| C2 | 原文提到的關鍵物件／動作，prompt 有沒有涵蓋？ |
| C3 | prompt 有沒有出現原文未提及、憑空加入的人物或元素？ |
| **E1** | **`focus` 填了嗎？是一句完整的中文句子（結尾是句號或問號）嗎？** 名詞片語不算，退回 `storyboard-intent` |
| **E2** | 命題的**主詞**是不是畫面的主體？主詞是「你／他／人」時，prompt 裡**有沒有一個人**？（見 staging「起點是命題」） |
| **E3** | 命題的動詞是**對帳型**（同一筆錢／同一段時間的兩種用法之間的得失差：換／虧／賠／划不划算）時，畫面有沒有把**帳的兩邊**都畫出來？只畫單邊、或只把受詞畫成靜物，不算 |
| **E4** | 命題是**量的問句**（多少／幾／幾倍）時，畫面留了明確的未知位（空容器／凹槽／空白泡泡）嗎？有沒有誤填 `directionality` 把未知變成已完成？（「能不能」這類是非問句不適用） |
| **E5** | 命題有**兩個對立子句**（以為 X 其實 Y）時，X 與 Y 兩邊都在畫面上嗎？ |
| **E6** | **回讀測試**：把命題蓋住，只讀 prompt，能不能讀回那一句命題？讀不回來就是失焦，重寫 staging |
| **E7** | 畫面裡**每一個人**都寫了「描述詞＋具體衣物＋顏色」嗎？只寫 `a person` 會畫出沒穿衣服的單色人形（路人也要寫，見 staging） |
| **E8** | 有沒有用 `glowing` / `luminous` 描述色塊？會畫成光暈，跟 `solid unshaded color blocks` 打架 |

> E1–E6 是 2026-08-07 逐格稽核打出來的。`if_test` 前 24 格有 12 格畫錯重點，
> **12 格全部過不了 E2–E5 其中至少一條**，而通過的 12 格一條都沒踩。
> E6 是唯一能抓到「每個元素都對、合起來卻不是那句話」的檢查——單看元素清單抓不到。

---

## 輸出

逐格處理，寫完立刻存回 `output/<系列>/<系列>.json`。

跑完回報：完成格數、標記人工確認的格、標 `needs_post_text` 的格。
