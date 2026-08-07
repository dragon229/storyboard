---
name: storyboard-staging
description: 寫出每一格畫框裡實際有什麼——主體、動作、空間關係、道具。由 storyboard 呼叫，或使用者說畫面內容漏了東西時使用。
disable-model-invocation: true
---

# storyboard-staging｜場面調度

**輸入**：`depiction_mode` ＋ `framing` ＋ `source`
**輸出**：`staging`（英文描述）＋ `needs_post_text`

場面調度是**被攝物的決定**：畫框裡放什麼、誰在哪、在做什麼、道具的物理狀態。
跟取景（攝影機的決定）是兩件事。

---

## 核心約束：受景別限制

**先定取景，再寫內容。** 內容必須符合已定的景別，寫超過畫框的東西會讓景別作廢。

### 反向約束（實測，最容易踩）

**場面調度寫錯了會反殺景別。**

最典型的：**prompt 只要提到鞋子，模型就必須畫全身**，寫好的特寫直接變成全身小人。

**但「拿掉觸發詞」修不好它。**（2026-08-06 實測）s27 是中景格卻畫成全身，把
`one ankle crossed over a knee` 整句刪掉、其餘完全不動、同 seed 重跑 —— **還是全身**。

真正的機制是：**姿態本身決定了畫框的下界**。「斜躺在躺椅上」「跪在地上刷馬桶」「站在門口」
這些是全身姿態，中景根本畫不下，模型只能退回全身。鞋子只是這個機制最顯眼的一個例子。

所以規則不是「別提鞋子」，而是：

> **中景格的姿態必須是上半身能表達完的**——坐直、傾身向前、雙手放在桌上、舉起某物、
> 轉頭看向某處。凡是躺、跪、盤腿、斜靠、走動、蹲下，一律改成全身景，或換一個姿態。

判斷方法：把你寫的姿態畫成一個腰部以下被切掉的人，還讀得出他在幹嘛嗎？讀不出來就改。

所以主持角色的服裝描述拆成三段（見 `assets/character.json`），依景別決定用到哪一段：

| 景別 | 用到 |
|---|---|
| 特寫、近景 | `costume_upper_en` |
| 中景 | `costume_upper_en` + `costume_mid_en` |
| 全身、遠景 | 三段全用 |

**同時：選到的段落必須整句用上。** 只寫上衣的話模型會自己配下半身的色，角色會變成全身同色。

同樣的道理適用於所有主體：特寫格不要描述背景空間，全身格不要描述臉部細節。

---

## 主持角色的寫法

角色是「觀察者」，設定在 `assets/character.json`。

- **外觀**：`base_en` 逐字照抄，不要改寫。鎖定特徵（圓頭、一撮翹髮、圓框眼鏡、點狀眼、腮紅、赭紅主色）不可調整。
- **服裝**：依 `era`（現代／科幻／遠古）選對應那組，再依景別取段。
- **姿態動作**：這一格新寫的部分。

### ★帶角色的格，背景必須寫具體（實測）

參考圖 `character_ref.png` 是米白素底，**這個素底會滲進輸出**，讓整張圖褪色發白。

背景寫得夠具體就撐得住；寫成模糊指涉就會被素底吃掉：

> ✗ `standing on that same empty street`
> → 整張褪成米白，跟沒有角色的格擺在一起明顯不同調
>
> ✓ `standing on an empty city street at dawn, rows of low shopfronts receding into the distance on both sides, warm orange sky above the vanishing point`
> → 飽和度與相鄰的純文字格一致

**規則：帶角色的格，背景至少要寫出「場所 + 兩個具體元素 + 色調方向」。**
不可以用「同一個地方」「前述場景」這類指涉——模型看不到前一格，只看得到參考圖的素底。

**定位是體驗者**：他被丟進推演出來的世界裡，親自遭遇後果。寫他在**經歷什麼**，
不是寫他在**說明什麼**。

> ✗ `the observer pointing at a diagram of a flip phone`
> ✓ `the observer standing on a 2026 street holding a strangely shaped phone, staring at it with a puzzled expression`

---

## 寫實景時要回答的四個問題

動作與空間關係最容易寫得含糊。下筆前答完：

1. 主體在哪裡？（站著？坐著？靠著什麼？）
2. 其他元素從哪個方向來？（左側？正面？上方？）
3. 接觸點是什麼？（手握著？擋在前面？壓在上面？）
4. 關鍵道具在哪個位置？

> ✗ `the observer confused in a strange city`
> ✓ `the observer standing at a crosswalk, a row of shopfronts receding to the left, holding a bulky rectangular phone in both hands at chest height, head tilted down at it`

---

## 寫圖解時的五條硬規則 ★

這五條是 2026-08-06 逐格稽核 24 格圖解 + 同 seed 對照實驗打出來的。
**24 格裡有 16 格壞掉，全部踩在這五條上。** 不是建議，是硬規則。

### G1 同類元素的可變屬性會被同質化 ★最容易踩、也最致命

**模型無法在同一張圖裡讓兩個同類元素帶不同的屬性值。屬性會被同質化成一個，
選中哪一個是隨機的。**

這是本輪最重要的發現，而且**不只發生在方向**。實測收集到三種形態：

| 同類元素 | 想要的差異 | 實際畫出來 |
|---|---|---|
| 兩支箭頭 | 一支向上、一支向下 | 兩支同方向（s33，兩種措辭都試過）|
| 同一個天平的兩個秤盤 | 一盤紅點、一盤鈔票 | **兩盤都是紅點**，鈔票被擠到天平外面（s42，改寫後仍然）|
| 三個格狀面板 | 1/3 滿、半滿、全滿 | 第二個直接跳到全滿（s23，改寫後仍然）|

**判斷方法**：這一格裡有沒有「兩個以上長得一樣的東西，卻要它們在某個屬性上不同」？
有 → 這一格會壞，而且**改措辭修不好**。

**唯一有效的對策是讓它們不再是「同類元素」**：

- 換成**不同的視覺形式**（一個用箭頭、一個用坡道；一個用容器、一個用堆疊）
- 把差異改成**位置**而不是屬性（該多的擺上面、該少的擺下面 —— s33 修正版成功）
- 差異太重要就**拆成兩格**（s42／s23 屬於這一類：一格塞了必須並存的兩組對比）

—— 以下是同質化在「方向」上的具體展開 ——

實測（s33，同 seed 對照）：要求「左邊綠箭頭向上、右邊藍箭頭向下」

> 原措辭 → 兩支**都向上**
> 改成幾何終點「箭尾在下緣、箭頭碰上緣」→ 兩支**都向下**

**改措辭沒有用。** 唯一的解法是不要讓一格出現兩個相反方向：

| 想表達 | ✗ 不要寫 | ✓ 改成 |
|---|---|---|
| 一升一降 | 一支向上的箭頭 ＋ 一支向下的箭頭 | **位置編碼**：該升的物件擺在畫面上緣附近，該降的擺在下緣附近，中間一條素線連起來 |
| 雙向互換 | `a pair of arrows in opposite directions` | **單一封閉環**：`a single closed circular loop of arrows drawn around both of them`（用 `layouts.環形`） |
| 進與出 | 一進一出兩支箭頭 | 只畫其中一支，另一邊用形狀（漏斗／缺口）表示 |

同理，`directionality` 這一欄一格只填一個值，**不要在 staging 裡再寫第二個方向**。

### G2 位置關係要寫成畫面座標或容器，不要寫關係詞

`against` / `beside` / `between` / `next to` / `drawing back from it` 這類關係詞模型解析不了，
元素會跑到錯的地方，或乾脆併進主體裡。

實測（s48，同 seed 對照）：

> ✗ `a balance scale holding a plain pale bar against a modest heap of coins`
> → 兩個秤盤**全空**，硬幣堆掉到天平底座下面
>
> ✓ `a balance scale with a plain pale bar lying in its left pan and a small mound of gold
>    coins in its right pan`
> → 硬幣進到正確的盤裡，左右對比出來了

**每個元素都要能回答「它在畫面的哪裡」**：左半／右半／上緣附近／下緣附近／畫面正中／
從右緣進入／在 X 的裡面。

### G3 傾斜、失衡、大小關係要寫成幾何事實

`contrast_balance: 失衡` 只是版面提示，**模型不會自己把天平畫歪**。

> ✗ `a balance scale tipped hard to one side`（s42／s48 → 畫成水平，失衡語意全失）
> ✓ `the left pan hanging low near the bottom of the frame and the right pan lifted high
>    near the top`（s68 → 成功）

「三倍高」「兩倍寬」這種可量的比例寫得出來就寫（`a mound of coins three times taller`，
s48 修正版成功），寫不出來就用位置。

### G4 抽象幾何元素不要用數詞

`three blocks` / `a pair of arrows` / `three bars` 在抽象色塊上**不可靠**。

實測（s17，同 seed 對照）：要求 3 個橘色方塊 → 原版畫 4 個，改寫後畫 2 個。
基線裡 s03（a pair of arrows → 1 支）、s55（three bars → 2 條）同樣壞掉。

但 `three solid gold coins`（s24）、`three staff`（s51）**成功**——差別是那些有視覺先驗，
色塊沒有。所以：

- 元素是**有語義的實體**（硬幣、人、藥丸、裝置）→ 可以用數詞，上限 3
- 元素是**抽象幾何**（方塊、長條、箭頭、圓點）→ **不要用數詞**，改用質性差異詞：
  `a single small red dot` vs `a cluster of the same small red dots`（s40 → 成功）

### G5 抽象無語義物件要先給它語義

實測：`a plain pale bar`（代表「一條命」）在有硬幣的格裡**兩個版本都消失**——
被有強語義的物件吸收掉了。

同一格裡若同時有「有語義的物件」與「純粹的抽象形狀」，抽象形狀會被吃掉。對策：

- 給抽象形狀一個**具體的物**（一條命 → 一支沙漏／一段發光的綠色刻度；不要用「a pale bar」）
- 或把有語義的物件也抽象化，讓整格是同一個抽象層級

同樣適用於 `a blank card` / `a plain shape` / `an empty tag` 這類「刻意留白以避開文字禁令」
的元素——留白不等於可以沒有形狀特徵。

### G6 元素上限：圖解格 3 個

原本寫 3–5，實測 5 個就開始垮（s11 五個元素，左半人形整個消失）。
3 個以內最穩（s29／s40／s50 都是 3 個以內，全部通過）。

超過 3 個就是這一格塞了兩件事，回 `storyboard-depiction` 拆成兩格。

---

## 數量的視覺轉換

原文說「很多、擠滿、密密麻麻、成千上萬」時，**不要真的畫一大堆**。畫面越密，個體越模糊，
規模感反而下降。

正確做法：**選 2–3 個代表性個體，每個給明確的差異特徵**（不同顏色、不同狀態、不同朝向），
規模感交給情緒語句傳達。

> 「街上塞滿了各種奇怪的裝置」→ 不畫滿街，畫「三台外型各異的裝置並排，
> 各有不同的旋鈕與指示燈」

注意這裡的「三台裝置」是**有語義的實體**，可以用數詞（見 G4）。換成「三個色塊」就不行。

---

## 次要元素會被主體吃掉 ★

一格裡的焦點以外的元素（伸過來的手、旁邊的水桶、背景的門階）**經常整個消失**。
基線裡 s20 的手、s07 的水桶、s04 住戶的手、s65 的門階、s49 的矮牆全部不見。

對策（s20 同 seed 對照驗過有效）：

1. **把次要元素寫在句首**，不要放在主體描述後面當補語
2. **給它明確的入畫位置**：`entering from the right edge of the frame` 而不是 `beside it`
3. **給它一個動作**，不要只給狀態

> ✗ `a large open wallet ... , a smaller desaturated hand drawing back from it with the
>    fingers curled`（手消失）
> ✓ `a hand with the fingers curled entering from the right edge of the frame and pulling
>    back away from a large open wallet, the wallet sitting in the left half of the frame`
>    （手變大而明確）

如果一格有兩個非做不可的元素卻放不下，那是這一格塞了兩件事——回 `storyboard-depiction`。

---

## 全域禁止文字

畫面不能出現任何文字。所以：

- **不要寫任何會產生文字的東西**：招牌上的字、螢幕上的字、書封上的字、標籤、數字。
- 需要「這是一本書」→ 寫書的形狀與顏色，不寫書名。
- 需要「螢幕上顯示著東西」→ 寫發光的幾何色塊，不寫內容。

### ★三個「自己長出文字」的物件（實測，寫 blank 也擋不住）

這三個東西**光是被提到就會長出數字或字元**，`blank-faced` / `plain` 這種形容詞擋不住：

| 物件 | 實測 | 改寫成 |
|---|---|---|
| **時鐘／錶面** | s09 `a round blank-faced wall clock` → 鐘面畫出 11 12 1 2 3 4 5 | 只寫一個圓盤加**一根指針**，或改用沙漏 |
| **鈔票／紙鈔** | s20 `banded currency` → 鈔票上長出偽文字紋路；s42 秤盤裡的鈔票同樣 | 寫 `plain paper notes`（實測乾淨），或改用硬幣 |
| **硬幣正面** | s25 金幣上長出 `$` 符號 | 寫成 `a solid gold disc with a plain rim, no marking on its face` |

計算機按鍵、儀表刻度、收銀機面板同理——能不寫就不寫，非寫不可就只寫外形與顏色。

**真的需要專有名詞**（人名、年份、學術詞）時：
1. `needs_post_text` 標 `true`
2. staging 裡明確留出空白區域：`a large empty area in the upper third of the frame`
3. 該格不出圖，文字由剪輯後製加上

---

## 輸出

`staging` 是一段英文，只寫**畫框內容**——不含風格前綴、不含景別視角構圖的詞、不含情緒語句。
那些由 `storyboard-compose` 加。

逐格處理，寫完立刻存回 `output/<系列>/<系列>.json`。
