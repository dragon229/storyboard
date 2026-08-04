# ComfyUI 角色工作流：參考圖生成 + 一致性生成

技術路線：**Flux.1-dev + Redux（身分/風格注入）**，動漫畫風。
兩個工作流用「圖片檔案」串接：需求一輸出的分視圖，直接當需求二的參考圖。

- `角色參考圖生成.json` — 需求一：單一角度圖 → 多角度參考圖
- `角色一致性生成.json` — 需求二：多角度參考圖 + 文字 → 一致性場景圖

---

## 一、要補齊的模型（放對資料夾）

你已裝好 ComfyUI，只缺模型。以下是這兩個工作流會用到的檔案與存放位置（相對於 ComfyUI 根目錄）。

| 檔案 | 放置資料夾 | 用途 | 來源 |
|---|---|---|---|
| `flux1-dev.safetensors` | `models/unet/` | Flux 主模型 | HuggingFace `black-forest-labs/FLUX.1-dev`（需同意授權） |
| `t5xxl_fp16.safetensors`（VRAM 不足用 `t5xxl_fp8_e4m3fn.safetensors`） | `models/clip/` | 文字編碼 | `comfyanonymous/flux_text_encoders` |
| `clip_l.safetensors` | `models/clip/` | 文字編碼 | 同上 |
| `ae.safetensors` | `models/vae/` | Flux VAE | FLUX.1-dev 倉庫內 |
| `flux1-redux-dev.safetensors` | `models/style_models/` | **Redux：把角色特徵注入生成** | `black-forest-labs/FLUX.1-Redux-dev` |
| `sigclip_vision_patch14_384.safetensors` | `models/clip_vision/` | Redux 的視覺編碼器 | ComfyUI 官方 Redux 範例頁有連結 |

> 動漫效果加強（強烈建議）：到 Civitai 抓一個 **Flux 動漫風 LoRA**（搜尋 "anime flux" / "flux anime style"），放 `models/loras/`。用法見下方「動漫畫風調校」。

檔名若和上表不同，載入工作流後在對應節點的下拉選單改選你實際的檔名即可。

---

## 二、需求一：角色參考圖生成

**輸入**：一張角色圖（任一角度）
**輸出**：多角度參考圖（提示詞已設定成 turnaround / model sheet，含正面、側面、背面、3/4 側等）

### 用法
1. 把你的角色圖放到 `ComfyUI/input/`，命名例如 `input_character.png`。
2. ComfyUI 選單 → Load → 選 `角色參考圖生成.json`。
3. 若有節點變紅：用 **ComfyUI-Manager → Install Missing Custom Nodes**，這份工作流全是原生節點，通常不會缺；紅的多半是「模型檔沒選到」，點下拉重選即可。
4. `LoadImage` 節點選你的角色圖。
5. 按 **Queue**。輸出存到 `ComfyUI/output/charref/`。

### 產出你要的「精確角度」（重點）
單一張 sheet 沒辦法保證剛好切出「臉部 8 向每 45°」。要**精確角度**，改成「一角度跑一張」最可靠：把正向提示詞（節點 8）換成單一角度描述，逐一 Queue 即可。可直接複製：

**全身 4 向**
- `full body, front view, standing, T-pose, white background`
- `full body, side view (profile), standing, white background`
- `full body, back view, standing, white background`
- `full body, three-quarter front view, standing, white background`

**臉部 8 向（每 45°）**
- `face close-up, front view (0 degrees)`
- `face close-up, turned 45 degrees to the left`
- `face close-up, left profile (90 degrees)`
- `face close-up, turned 135 degrees, back-left`
- `face close-up, back of head (180 degrees)`
- `face close-up, turned 135 degrees, back-right`
- `face close-up, right profile (90 degrees)`
- `face close-up, turned 45 degrees to the right`

每張都靠 Redux 從你的輸入圖鎖住角色身分，所以 12 張會是同一個角色。臉部視圖把 `EmptySD3LatentImage`（節點 12）改成 `1024 x 1024`，全身視圖用 `896 x 1152`（直式）較好。

### 更強的角度控制（選配）
要更硬的角度控制（例如背面很難用文字逼出來），加裝 Flux 姿勢 ControlNet：
- 模型：`Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro`（放 `models/controlnet/`）
- 節點包：`ControlNet-Union` 用 **ComfyUI-eesahesNodes**（提供 Union ControlNet 載入 + `SetUnionControlNetType`，選 `pose` 模式）；姿勢圖用 **comfyui_controlnet_aux** 的 OpenPose 預處理器。
- 接法：`ControlNetApplyAdvanced` 接在 Redux 之後、KSampler 之前的 conditioning 上。

---

## 三、需求二：角色一致性生成

**輸入**：需求一的參考圖（全身 + 臉部各一張）＋ 文字 prompt
**輸出**：依文字生成的場景圖，角色與參考一致

工作流內建**雙參考**：一張全身（管身形/服裝）、一張臉部特寫（管長相），兩個 Redux 串接，一致性比單張強。

### 用法（含與需求一的串接）
1. 從 `ComfyUI/output/charref/` 挑最好的兩張：一張全身、一張臉部特寫。
2. **複製到 `ComfyUI/input/`**（LoadImage 只讀 `input/`），命名 `ref_body.png`、`ref_face.png`。
   → 這一步就是「需求一 ➜ 需求二」的串接。
3. Load `角色一致性生成.json`。
4. 兩個 `LoadImage` 分別選 `ref_body.png` / `ref_face.png`。
5. 正向提示詞（節點 10）寫你要的場景，例：`anime style, character sitting in a cafe by the window, warm afternoon light, ...`。
6. 按 Queue，輸出在 `ComfyUI/output/consistent/`。

### 一致性 vs 創意的旋鈕
- 兩個 `StyleModelApply` 的 **strength**（第一個欄位，預設全身 0.9 / 臉部 0.7）：**調高＝更像參考、更死板**；**調低＝更聽文字、變化更大**。臉部先動就好。
- 只想保臉、身體隨場景：把全身那個 StyleModelApply strength 降到 0.4~0.5。
- 動作/構圖也要指定：同樣可加 OpenPose ControlNet（見上）。

---

## 四、動漫畫風調校（兩個工作流通用）
1. 抓 Flux 動漫 LoRA 放 `models/loras/`。
2. 在 `UNETLoader` 之後插一個 `LoraLoaderModelOnly`，`MODEL` 串進去再接 KSampler。
3. 提示詞保留 `anime style, ...`；覺得太寫實就把 LoRA 權重調到 0.8~1.0。

---

## 五、選配：PuLID-Flux（真人臉才建議）
PuLID 對**寫實人臉**鎖定最強，但對**純動漫臉**容易把畫風拉向寫實，所以本方案預設用 Redux。若你的角色偏 2.5D 或想額外鎖臉：
- 節點包：`ComfyUI-PuLID-Flux-Enhanced`（需 InsightFace、EVA-CLIP、`pulid_flux` 權重）。
- 節點：`Load PuLID Flux Model` + `Apply PuLID Flux`（weight 建議 0.8~1.0），接在 MODEL 線上。

---

## 六、疑難排解
- **節點變紅/缺節點**：ComfyUI-Manager → Install Missing Custom Nodes，再 Restart + 重整瀏覽器。
- **StyleModelApply 只有 conditioning 欄位、沒有 strength**：你的 ComfyUI 較舊，把 `widgets_values` 多的參數忽略即可，或更新 ComfyUI。
- **爆顯存 (OOM)**：t5xxl 換 fp8 版；Flux 主模型改用 GGUF 量化版（`models/unet/`，需 `ComfyUI-GGUF` 的 `UnetLoaderGGUF`）。
- **角色不夠像**：需求二調高 StyleModelApply strength；或參考圖換成更乾淨、背景單純的分視圖。

---

## 檔案清單
- `角色參考圖生成.json`
- `角色一致性生成.json`
- `README_安裝與使用.md`（本檔）
