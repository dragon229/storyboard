# Qwen_Image_Edit_2509_Sref_Lora 研究日誌

對象：https://huggingface.co/svjack/Qwen_Image_Edit_2509_Sref_Lora
目標：搞懂怎麼用，做成 skill `style-transfer-sref`。

---

## 階段 0 · 對齊

**這個 LoRA 做的事，跟 `style-transfer-qwenstyle` 不一樣。** 這是最重要的一句話。

| | qwenstyle | sref |
|---|---|---|
| 輸入 | content 圖 + style 圖 | **只有 style 圖**（+ 一句中文目標題材） |
| 保留 | content 圖的構圖、人物、物件 | 只保留**畫風**，題材整個換掉 |
| 用途 | 「把我這張圖轉成那個風格」 | 「用這個風格，畫一隻粉色八爪魚」 |

成功判準（可量測）：
1. 給 1 張風格圖 + 1 個中文題材詞，跑完不報錯，出圖 —— 二元
2. 輸出的**題材**確實換成指定的（人工看，至少 3 個不同題材都對）
3. 輸出的風格統計量（亮度 L / 暖色 WB / 飽和 S）貼近參考圖，且**明顯優於「拿掉 sref LoRA」的對照組**
4. 失敗定義：(a) 輸出還是參考圖的原題材 → 沒換成功；(b) 糊／欠煮 → Lightning 沒生效

## 階段 1 · 盤點

已有：
- ComfyUI 0.25.1 @127.0.0.1:8188（RAM 34G，loras 目錄 `C:\Users\User\ComfyUI-Shared\models\loras`）
- 底模 `qwen_image_edit_2509_fp8_e4m3fn.safetensors` ✓
- `Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors` ✓
- VLM `D:\models\Qwen2.5-VL-7B-Instruct` + 專用 venv `D:\models\qwen_vl_venv` ✓
- 節點 `CFGNorm` / `ImageScaleToTotalPixels` / `TextEncodeQwenImageEditPlus` ✓

缺：
- `Qwen_Image_Edit_2509_sref_lora_000007000.safetensors`（590 MB）→ 已下載
- **`AILab_QwenVL` 節點沒裝**（`/object_info/AILab_QwenVL` 回 `{}`）→ 不裝，改用本機 Qwen2.5-VL 在 ComfyUI 外面跑

## 階段 2 · 求真：官方檔案 vs 我的實作

權威來源＝ repo 內的 `qwen_image_edit_2509_vl_sref.json`（UI 格式）。model card 的文字幾乎沒有可用資訊，全部靠讀這個檔。

| 項目 | 官方 | 我的實作 | 判定 |
|---|---|---|---|
| 底模 | qwen_image_edit_2509_fp8_e4m3fn | 同 | 相同 |
| sref LoRA | `..._000007000.safetensors` @1.0 | 同 | 相同 |
| LoRA 順序 | UNET → sref → Lightning | 同 | 相同 |
| Lightning LoRA | `Qwen-Image-Edit-Lightning-4steps-V1.0-bf16`（**非 2509 版**） | `Qwen-Image-Edit-2509-Lightning-...` | **不同**（本機沒官方那顆；換成與底模同代的版本） |
| 取樣 | euler / simple / steps 4 / cfg 1.0 / denoise 1.0 | 同 | 相同 |
| ModelSamplingAuraFlow shift | 3.0 | 同 | 相同 |
| CFGNorm | strength 1.0 | 同 | 相同 |
| 輸入圖 | 1 張（image1），image2/3 的 LoadImage 是 bypass | 1 張 | 相同 |
| 尺寸 | ImageScaleToTotalPixels lanczos 1.0 MP | 同 | 相同 |
| latent | VAEEncode(縮放後的風格圖) | 同 | 相同 |
| 負向 prompt | 空字串，一樣接風格圖 | 同 | 相同 |
| VLM | AILab_QwenVL + Qwen3-VL-4B-Instruct，seed 固定 | 本機 Qwen2.5-VL-7B，greedy | **不同**（節點沒裝；指令文字逐字照抄） |
| VLM 指令 | 見下 | 逐字照抄 | 相同 |

### 官方 VLM 指令（節點 397 + 394 串接，逐字）

```
使用中文描述这个图片是如何根据这个图片用相同的画风进行编辑得到“{目標題材}”的,不要指出人物的名字或出处或其它猜测，只严格描述进行了哪些在同一画风下的编辑和改变，注意要将这个照片中与上一张照片中画风相对应的部分进行提及，对物体取代、色彩变化、整体画风遵循进行对应描述。以'进行下面的修改：'开头"
```

（結尾那個孤零零的 `"` 是官方 widget 裡就有的，照留。）

### 讀檔時踩到的坑

- **節點 111 的 widget 裡有一段寫死的舊 prompt（黑貓變小狗那段）。那是殘留物**，它的 `prompt` 輸入有連線會覆蓋掉 widget。照抄 widget 文字＝抄到死資料。
- 官方檔是 **UI 格式**（有 `nodes`/`links`），不能直接送 `/prompt` API，必須轉寫。
- 檔案裡超過一半的節點 `mode=4`（bypass），是另一條「多圖 + raw latent」的分支，不是這條路。

## 階段 3 · 建台

`scripts/sref_run.py` —— 一個實驗 = 一行指令。可調：`--target` / `--styles` / `--seed` / `--megapixels` / `--strength` / `--lora`（換 checkpoint）/ `--no-vlm`（對照組）/ `--no-sref`（拿掉 sref LoRA 的對照組）。

---

## 階段 4 · 診斷（對照組 + 單變因）

**根因一句話：輸出跑掉風格，是 VLM 寫的編輯指令自己發明了新場景，不是 sref LoRA 失效。**

三組實驗支持：

1. **sref 開/關對照（只給名詞當 prompt）** → 幾乎沒差（L 57/55、銳利 51.1/50.8、目視幾乎同圖）。
   一度以為「LoRA 沒生效」。**但這是樣本不夠格**：只給一個名詞走的是底模 2509 原生的編輯能力，
   根本沒踩到 LoRA 的訓練分佈（風格圖 + 長篇中文編輯指令）。
2. **sref 開/關對照（用 VLM 長指令，style_ref_4 公仔風）** → 統計量幾乎一樣（L 110 vs 102），
   **但目視差異巨大**：開 sref 保住光滑塑料質感與大眼高光；關掉直接跑成寫實毛髮照片。
   → LoRA 確實有效，而且**只有睜眼看才看得出來**。
3. **單變因（只改 prompt，其他全不動，style_ref_6 綠調底片）** → L 從 203 掉到 84、
   S 從 0.23 回到 0.77、暖度 +6 → −31（參考值 −11）。隧道、顆粒、暗角全部回來。
   → 根因確定在 prompt。

## 階段 5 · 迭代：加護欄

假設：Qwen2.5-VL-7B 守不住官方那段「只严格描述同一画风下的编辑」的約束（官方是配 Qwen3-VL 調的）。
做法：在官方指令後面接一段硬約束（`sref_prompt.py` 的 `_GUARD`），`--no-guard` 可退回原文。

結果（護欄 vs 無護欄，同圖同題材）：

| 風格圖 | 無護欄 | 有護欄 | 參考值 |
|---|---|---|---|
| ref_6 | L203 暖+6 S0.23 | **L95 暖−10 S0.72** | L69 暖−11 S0.69 |
| ref_4 | L110 暖+47 殘留0.018 | **L81 暖+57 殘留0.594** | L65 暖+38 |

目視：ref_6 隧道／綠調／顆粒／暗角全回來；ref_4 吊燈、暗色室內、三個公仔女孩原樣保留。
假設成立。

護欄**不完美**——7B 仍偶爾寫出「调整颜色使其符合自然颜色」這種違反護欄的句子，
所以人工複核那步不能拿掉。

## 階段 6 · 驗收

三個性質截然不同的案例，全部通過：

| 案例 | 性質 | 結果 |
|---|---|---|
| style_ref_1 | 平塗賽璐璐 anime、霓虹賽博 | 通過（八爪魚，硬邊平塗＋描線保住） |
| style_ref_4 | 3D 黏土公仔、暖色吊燈室內 | 通過（柴犬，塑料質感＋場景保住） |
| style_ref_6 | 顆粒感綠調底片、失焦暗角 | 通過（柴犬，隧道＋綠調＋顆粒保住） |

**結論的適用範圍與反例**：

- 這些結論建立在「VLM 指令品質夠好」的前提上。**指令品質是輸出品質的硬上限**——
  同一顆 LoRA、同一張圖，換一段爛指令就全毀（ref_6 的 L203 那組）。
- 只給名詞的短 prompt **測不出這顆 LoRA**。若有人拿短 prompt 說「這 LoRA 沒用」，
  那個結論不成立。
- 沒驗證的：7000 以外的 checkpoint、`--strength` ≠ 1.0、2511 底模、官方的 Qwen3-VL-4B。

---

## 教訓

1. **model card 幾乎沒有可用資訊。** 沒有 trigger word、沒有推薦權重、沒有推論範例。所有實際參數只存在於 repo 附的那個 workflow JSON 裡——直接讀那個檔，不要讀說明。
2. **這顆 LoRA 不是「A 圖套 B 圖的風格」，是「用 B 圖的風格重畫一個新題材」。** 從 model card 的英文描述（"style transfer"）很容易誤判成跟 qwenstyle 同一件事，實際輸入形態完全不同。
3. **官方 workflow 依賴沒裝的自訂節點（AILab_QwenVL）。** 官方附的檔案是給他們自己的環境用的，直接匯入會缺節點。VLM 那步搬到 ComfyUI 外面反而更好：可以人工複核與覆寫 prompt。
4. **官方指定的 Lightning LoRA 是非 2509 版。** 與底模不同代，可能是筆誤或他們環境的殘留。改用 2509 版。
5. **失敗幾乎都在 prompt，不在模型。** VLM 會寫出「替换为白色背景」「如草地或公园」「还原成自然颜色」
   「添加铃铛蝴蝶结」——每一句都直接毀掉畫風。調 LoRA 權重救不了，要改的是那段文字。
6. **「拿掉它結果沒差」不等於「它沒生效」。** 也可能是你的輸入根本沒踩到它的作用範圍。
   判定一個元件無效之前，先確認測試素材有能力顯示它的效果。
7. **統計量幾乎相同的兩張圖，可以是「風格保住」和「風格全毀」。** ref_4 那組 L 110 vs 102、
   S 0.63 vs 0.64，看數字會判定「沒差」，開圖看是公仔 vs 寫實照片。每輪都要看圖。

---

# 第二輪 · 需求變更：改成 content 圖 + style 圖

使用者澄清目標是「把 content image 轉成 style image 的風格」。重跑階段 4。

## 階段 4 · 診斷

**根因：雙圖風格轉換的能力不在 sref LoRA 裡，也不在裸底模裡，只在 qwenstyle LoRA 裡。**

三組實驗：

1. **極端輸入**：content 固定，換三張性質天差地遠的風格圖（L65暖+38／L69暖−11／**L180 S0.07 近乎白圖**）
   → 輸出統計量**完全相同**（L34 暖−25 S0.85）。image2 零影響。
   拿掉 sref（純底模）也一樣。中英文 prompt 措辭都試過，沒差。
   查證節點 optional 插槽確實是 `image1/image2/image3`，接線沒錯 → **靜默失效**。
2. **單變因（只換 LoRA）**：sref → qwenstyle，其他全不動 → L 34 變 55，
   目視手部從線稿變光滑 3D 塑料。**接線正確，缺的是那顆 LoRA。**
3. **疊加**：`UNET → sref → qwenstyle → Lightning` → 構圖保留 0.547（全場最高）、風格確實進去。

## 階段 6 · 驗收（雙圖）

| 風格圖 | 疊加 | 只用 qwenstyle | 判定 |
|---|---|---|---|
| ref_4 3D 公仔 | 構圖0.547 | 0.386 | 疊加勝（單掛較糊） |
| ref_2 漫畫網點 | 構圖0.171 | 0.220 | **疊加勝**（單掛把手臂畫成鵝卵石亂紋，失敗） |
| ref_6 底片顆粒 | 0.404 | 0.255 | 兩者都幾乎沒轉過去 |

2 個明顯成功、1 個無效。**照片／實拍類風格是已知弱項**，這是結論的邊界。

## 教訓（續）

8. **「插槽存在」不等於「模型會用它」。** `TextEncodeQwenImageEditPlus` 有 image1/2/3，
   官方檔甚至接好了線，但沒有對的 LoRA，image2 就是被無視——不報錯、log 無警告。
9. **判定靜默失效要用極端輸入。** 拿性質相近的兩張風格圖去比，輸出差不多會誤判成「有效但很弱」。
   丟一張 L180 的近白圖進去，輸出還是 L34，才能一槌定音。
10. **能力歸屬要靠單變因確認。** 一開始以為是「sref 壓制了 image2」，
    但拿掉 sref 也一樣 → 不是壓制，是底模本來就沒這個能力。差一步就下錯結論。
11. **content 走文字通道必然失真。** `--text-bridge` 風格轉得掉，但構圖保留只有 0.031。
    要保構圖，content 就得走 image 通道。
