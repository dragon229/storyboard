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

## 寫圖解時的三條規則

1. **元素數量控制在 3–5 個。** 越多越糊，資訊反而讀不出來。
2. **每個元素給明確的視覺編碼**：顏色、形狀（實心／空心）、大小、密度。這些取代標籤。
3. **物理狀態要寫清楚**：漂浮的？排列在一條線上？堆疊的？不寫模型自己決定。

---

## 數量的視覺轉換

原文說「很多、擠滿、密密麻麻、成千上萬」時，**不要真的畫一大堆**。畫面越密，個體越模糊，
規模感反而下降。

正確做法：**選 3–5 個代表性個體，每個給明確的差異特徵**（不同顏色、不同狀態、不同朝向），
規模感交給情緒語句傳達。

> 「街上塞滿了各種奇怪的裝置」→ 不畫滿街，畫「三台外型各異的裝置並排，
> 各有不同的旋鈕與指示燈」

---

## 全域禁止文字

畫面不能出現任何文字。所以：

- **不要寫任何會產生文字的東西**：招牌上的字、螢幕上的字、書封上的字、標籤、數字。
- 需要「這是一本書」→ 寫書的形狀與顏色，不寫書名。
- 需要「螢幕上顯示著東西」→ 寫發光的幾何色塊，不寫內容。

**真的需要專有名詞**（人名、年份、學術詞）時：
1. `needs_post_text` 標 `true`
2. staging 裡明確留出空白區域：`a large empty area in the upper third of the frame`
3. 該格不出圖，文字由剪輯後製加上

---

## 輸出

`staging` 是一段英文，只寫**畫框內容**——不含風格前綴、不含景別視角構圖的詞、不含情緒語句。
那些由 `storyboard-compose` 加。

逐格處理，寫完立刻存回 `output/<系列>/<系列>.json`。
