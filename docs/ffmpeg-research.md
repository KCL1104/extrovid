# FFmpeg 評估結論（2026-06）

> 問題：「不確定是否需要使用到 FFmpeg，請研究看看。」

## 結論：需要，而且專案早已在用 — 正確方向是「強化」而不是「導入」

`backend/app/services/rough_cut_service.py` 從 Phase-1 起就用 FFmpeg
（透過 `imageio-ffmpeg` 內建的靜態 binary）完成 rough cut 的全部渲染：
正規化（scale/pad/30fps/yuv420p）、逐鏡 xfade 轉場 + acrossfade 音訊、
SRT 字幕燒錄（libass）、合成環境音床、失敗時降級成 plain concat。

研究確認（2025–2026 最佳實務）：**server-side FFmpeg subprocess 是這類產品的
正確架構**，與 Runway / Kapwing / LTX Studio 的做法一致 — 瀏覽器負責預覽，
雲端負責最終輸出。

### 否決的替代方案

| 方案 | 否決原因 |
|---|---|
| `moviepy` | RAM-bound、慢；只是 FFmpeg 的厚包裝 |
| `ffmpeg-python` | 已無維護 |
| PyAV | filter-graph 工作沒有幫助，徒增複雜度 |
| `ffmpeg.wasm`（瀏覽器端） | 整檔載入記憶體、2GB 上限、需要 SharedArrayBuffer CORS headers、~10x 慢；結果還是得上傳回伺服器供 gallery 使用 |
| WebCodecs export | 沒有 muxer、Safari/Firefox 缺口 |
| Remotion | 為「渲染 React 合成」設計，不適合拼接 provider 產出的 mp4，且公司授權收費 |

### 各功能是否需要 FFmpeg

| 功能 | 需要? | 狀態 |
|---|---|---|
| 轉場拼接（xfade/acrossfade） | ✅ | 既有 |
| 字幕燒錄 | ✅（libass 已在 binary 內） | 既有 |
| 合成音床 / 未來音樂混音（amix） | ✅ | 既有 |
| 最終 15–60s mp4 匯出 | ✅（gallery 需要伺服器端成品） | 既有 + 本次加 `+faststart` |
| 逐 clip 精準 trim | ✅（stream-copy 只能切 keyframe，誤差 2–5s 不可用；短 clip 重編碼成本極低） | **本次新增**（`-ss`/`-t` input seek） |
| 縮圖 / poster frame | ✅ | **本次新增**（ingest 時抽取，餵 storyboard 卡片、queue、ReviewAgent 視覺輸入） |
| Last-frame 抽取 → 鏡頭續接 | ✅ | **本次新增**（前一鏡最後一幀成為下一鏡 i2v 種子 — `-sseof`） |
| 時長 / metadata probe | ✅ | **本次強化**：imageio-ffmpeg 不含 ffprobe（上游 issue #23），原本用 regex 解析 stderr;現在優先用真 ffprobe（JSON 輸出），fallback 保留 |
| 瀏覽器內 timeline 預覽 | ❌ | 用逐鏡 `<video>` 播放 + 客戶端 trim 標記即可，不需伺服器渲染 |
| mock 模式（開發/測試） | ❌ | `USE_MOCK_VIDEO` 直接回 placeholder bytes，CI 不需要 binary |

### 本次落地的整合強化

1. **Dockerfile pin 版本**：`COPY --from=mwader/static-ffmpeg:7.1 /ffmpeg /ffprobe /usr/local/bin/`
   + `IMAGEIO_FFMPEG_EXE` / `FFPROBE_EXE` 環境變數 — dev（wheel）與 prod（pinned）走同一條程式路徑,
   並避開 imageio-ffmpeg 在 Docker 的執行權限問題（上游 issue #45）。`apt-get install ffmpeg`
   被否決（slim image 會拉 300MB+ 依賴且版本浮動）。
2. **`app/services/media_service.py`**：probe（ffprobe JSON 優先）、poster 抽取、last-frame 抽取，
   全部 best-effort（mock bytes 不可解碼時回 None）。
3. **`render_rough_cut` 支援 per-clip in/out**（重編碼路徑上 frame-accurate）+ 輸出加
   `-movflags +faststart`（網頁播放即點即播）。
4. **測試**：`tests/test_media_ffmpeg.py` 用 bundled binary 離線產生迷你 clip,
   實際跑 probe / 抽幀 / 渲染（含 trim 與字幕+音床）— 補上原本零覆蓋的生產渲染路徑。
5. **配額保護**：ffmpeg 衍生資產（poster/continuation frame, `source_model="ffmpeg:*"`）
   不計入使用者每日 image 配額。

### 之後（規模成長時）再做

- Rough cut 渲染目前仍在 HTTP request 內（`asyncio.to_thread`）。5–10 個 720p 短 clip
  幾秒即完成，Railway 撐得住;若未來支援 1080p/更長輸出或並發用戶成長，
  把 assemble 移進既有的 GenerationJob/reconciler 模式（status=rendering + 進度）。
- `_run()` 加 stderr 記錄與 timeout，讓 Railway log 能看到渲染失敗原因。
- 真音樂檔上傳後直接進既有 amix chain。

### 主要來源

- Remotion docs（WebCodecs misconceptions、SSR 比較、license）
- ffmpeg.wasm repo / 客戶端剪輯實戰文（記憶體上限、SAB 需求）
- imageio-ffmpeg issues #23（不含 ffprobe）、#45（Docker exec 權限）
- mwader/static-ffmpeg（pinned 靜態 binary 的 Docker 慣例）
- FFmpeg trim/concat 無損 vs 重編碼（keyframe snap 行為）
- 本 repo 實測：bundled binary 為 johnvansickle static ffmpeg 7.0.2,
  含 libass / libx264 / xfade / acrossfade / tremolo
