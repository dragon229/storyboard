---
name: storyboard
description: 把科普影片的語音稿轉成分鏡稿並出圖。當使用者說「生成分鏡稿」「把語音稿轉成分鏡」「這篇稿子的分鏡」「storyboard」等需求時使用。六階段：切分→意圖判讀→呈現手法→取景→場面調度→組裝，再交給 storyboard-render 出圖。
---

# storyboard｜語音稿 → 分鏡稿 → 圖

科普／知識型 YouTube 頻道的分鏡稿生成主流程。

專案根目錄：`D:\Cowork\分鏡稿生成`
詞彙定義見 `CONTEXT.md`，整體架構見 `SKILL-MAP.md`。

---

## 參數

- **語音稿**：使用者指定的 `.md` / `.txt` 檔
- **系列名稱**：用來命名產物。不明確就問，不要猜

**產物**：每支影片一個資料夾，所有東西放進去。

```
output/<系列>/
├── <系列>.json          分鏡稿（整份一個檔，不拆格）
└── images/              s01.png … sNN.png
```

**不要**把分鏡稿和圖片散在專案根目錄的不同地方。一支影片＝一個資料夾。

**資產**（讀取，不修改）：
- `assets/style.json` — 風格規範
- `assets/character.json` + `assets/character_ref.png` — 主持角色「觀察者」

---

## 執行順序

**中途不停。** 跑完才交付。使用者要檢視就跑 `storyboard-verify`。

| # | 呼叫 | 粒度 | 說明 |
|---|------|------|------|
| 1 | `storyboard-segment` | 全局 | 切出分鏡格 |
| 2 | `storyboard-intent` | 逐格 | 修辭功能 / 情緒偏移 / 是否為推演 |
| 3 | `storyboard-depiction` | **全局** | **障壁**：必須等 2 全部完成 |
| 4 | `storyboard-framing` | 逐格 | |
| 5 | `storyboard-staging` | 逐格 | |
| 6 | `storyboard-compose` | 逐格 | |
| 7 | `storyboard-render` | 全局 | 出圖 |

**第 3 步是整條流程唯一的障壁**——呈現手法要看整份分鏡稿才能管節奏與跨格對照，
不能逐格邊判邊選。

逐格的步驟（2、4、5、6）用**一個** subagent 跑完全部場景，不要每格開一個。

---

## 分鏡稿格式

```json
[
  {
    "id": "s01",
    "unit": "u01",
    "source": "這一格涵蓋的原文段落",

    "rhetorical_function": "拋出鉤子",
    "emotional_shift": "懸念",
    "is_speculation": false,

    "depiction_mode": "細部放大",

    "framing": {
      "vocabulary": "實景",
      "shot_size": "特寫",
      "angle": "水平",
      "composition": "置中"
    },

    "staging": "畫框內容的英文描述",

    "prompt": "最終送 ComfyUI 的完整提示詞",
    "workflow": "text_only",
    "needs_post_text": false
  }
]
```

| 欄位 | 誰寫 |
|---|---|
| `id` / `unit` / `source` | segment |
| `rhetorical_function` / `emotional_shift` / `is_speculation` | intent |
| `depiction_mode` / `workflow` | depiction |
| `framing` | framing |
| `staging` / `needs_post_text` | staging |
| `prompt` | compose |

每個步驟只寫自己負責的欄位，寫完立刻存回 `output/<系列>/<系列>.json`，不要累積在記憶裡。

---

## 從中途接手

使用者常常只想重跑某一段。判斷他指的是哪一步，只重跑該步與其下游：

| 使用者說 | 從哪步起跑 |
|---|---|
| 「切太細／太粗」「重新切場景」 | 1 → 全部 |
| 「這幾格的功能判錯了」 | 2 → 3,4,5,6,7 |
| 「太多示意圖了」「這格改用隱喻」 | 3 → 4,5,6,7 |
| 「這格鏡頭不對」 | 4 → 5,6,7 |
| 「畫面內容漏了東西」 | 5 → 6,7 |
| 「重新出圖」「換 seed」 | 7 |

改了 `assets/style.json` 或 `assets/character.json` → 回到 6 重組 prompt。

---

## 注意事項

- 內嵌 `python -c` 要加 `-X utf8`，避免 Windows cp950 編碼錯誤
- 出圖前確認 ComfyUI 在線（`storyboard-render` 會檢查）
- `needs_post_text: true` 的格不出圖，交後製
