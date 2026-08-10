# Full Application Workflow Test — Results

**Date:** 2026-08-10
**Tester:** Live end-to-end testing against a running local instance (real PostgreSQL, real Ollama/local Whisper/BLIP/YOLO/pyannote — no mocks)
**Test videos used:**
- YouTube: `Lg-meK5IU8Q` (12:25 talking-head/blackboard explainer, "AI Agent Skills")
- Local upload: a 3:33 music performance video (re-used from a prior download to test the local-file path)

Status legend: ✅ Real & working · ⚠️ Partially working / notable gap · ❌ Stub — returns a plausible response but does no real work

---

## 1. Video Ingestion

| Feature | Status | Notes |
|---|---|---|
| YouTube URL ingestion | ✅ | Real yt-dlp download, persisted to DB, verified across 6+ live runs this session |
| Local file upload | ✅ | Tested this session for the first time — uploaded a 213s MP4, real processing kicked off automatically, completed correctly (97 scenes, 41 transcript segments, accurate summary) |
| Streaming URL ingestion | ❌ | `POST /api/videos/stream` returns a fake "downloading" response with a video_id, but never persists a Video row. The background task immediately errors (`Video not found in database`) and the video silently vanishes — `download_streaming_video` is a `# TODO` stub that never calls ffmpeg |

## 2. Processing Pipeline (triggered via upload/YouTube `auto_process`)

All confirmed real and working, verified via direct DB inspection and by cross-checking outputs against actual video content:

| Stage | Status | Evidence |
|---|---|---|
| Sparse frame sampling | ✅ | Real ffmpeg extraction (0.2 fps), files on disk |
| Scene detection | ✅ | Content-based histogram detection; 4 scenes for the talking-head video, 97 for the fast-cut music video — correctly reflects actual content |
| Audio transcription | ✅ | Local Whisper; transcript text verified to match actual spoken content word-for-word |
| Speaker diarization | ✅ | Real pyannote.audio pipeline; correctly found 1 speaker for a single-presenter video, real per-segment `speaker_id` persisted |
| Object detection | ✅ | Real YOLO; correctly differentiated scenes (found a "cell phone" in only one scene) |
| Face detection | ✅ | Real OpenCV Haar cascade; found the presenter's face |
| OCR | ✅ | Real EasyOCR; extracted legible (if imperfect, handwriting-on-blackboard) text matching on-screen content |
| Action recognition | ✅ | Real motion-based detection; aggregated into a per-scene activity ratio |
| Audio energy | ✅ | Real librosa RMS energy per scene segment |
| Keyframe captioning | ✅ | Local BLIP; captions accurately describe scene content across both very different test videos |
| Embeddings / vector search index | ✅ | Real sentence-transformer embeddings pushed to ChromaDB per transcript segment and scene |
| Summary generation | ✅ | Real local LLM (Ollama llama3.2); summaries are coherent, accurate, on-topic for both test videos |
| Highlight detection | ✅ | Real, differentiated importance scores (0.13 flat → 0.50-0.59 differentiated after wiring visual/audio/speaker context this session) |

**⚠️ Important structural gap found this session:** there are **two separate, disconnected "process a video" code paths**:
1. The real one — auto-triggered from `/api/videos/upload` and `/api/videos/youtube` when `auto_process=true`. This is what's described above and is fully real.
2. `POST /api/videos/{id}/process` and `POST /api/videos/{id}/reprocess` (in `processing.py`) — these are **pure stubs**. They log a message and return "complete" in ~2ms without doing anything (`# TODO: Implement full pipeline`). If a user (or the frontend) calls these expecting to (re)trigger analysis, nothing happens and the response looks successful.

## 3. Video Management

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/videos` (list, with `status`/`source_type` filters) | ✅ | Filters work correctly, verified counts |
| `GET /api/videos/{id}` | ✅ | |
| `GET /api/videos/{id}/status` | ✅ | |
| `DELETE /api/videos/{id}` | ✅ | Verified: deletes DB row and the video file; subsequent GET correctly 404s |
| `GET /api/videos/{id}/scenes` | ✅ | |
| `GET /api/videos/{id}/transcript` | ✅ | Includes real `speaker_id` |
| `GET /api/videos/{id}/frames` / `/keyframes` | ✅ | Fixed a bug this session (`Query()` sentinel leaking through a direct function call) that crashed this endpoint the moment real frame data existed |

## 4. Analysis — Summary, Highlights, Chapters, Timeline

| Endpoint | Status | Notes |
|---|---|---|
| `GET /{id}/summary`, `POST /{id}/summarize` | ✅ | Real, wired this session |
| `GET /{id}/highlights`, `POST /{id}/highlights/generate` | ✅ | Real, wired this session; scores now differentiate meaningfully by content |
| `GET /{id}/chapters` | ❌ | Stub, always returns empty list (`# TODO: Query database for chapters`) — note: `ChapterGenerator` service exists and is fully implemented/tested in isolation, just never wired to this endpoint |
| `GET /{id}/timeline`, `POST /{id}/timeline/filter` | ❌ | Stub, always empty (`# TODO: Build timeline from multiple sources`) — `fusion/timeline_builder.py` exists but isn't wired |

## 5. Search

| Endpoint | Status | Notes |
|---|---|---|
| `POST /api/search/semantic` | ✅ | Wired this session; real transcript+scene embedding search, correctly ranks results by relevance |
| `POST /api/search/frames` | ❌ | Stub, always empty — needs CLIP image embeddings (explicitly deferred all session as a heavier dependency) |
| `POST /api/search/transcript` | ❌ | Stub, always empty — despite `/semantic` already having the real transcript-search logic built; this dedicated endpoint was never updated to use it |
| `POST /api/search/query` (RAG) | ❌ | Stub, returns literal `"This is a placeholder answer."` |
| `POST /api/search/videos/{id}/ask` | ❌ | Same placeholder stub |
| `GET /api/search/videos/{id}/similar` | ❌ | Stub, always empty |
| `POST /api/search/temporal` | ❌ | Stub, always empty (takes query params, not a JSON body — inconsistent with the other search endpoints, worth noting if this ever gets built) |

## 6. Clips

| Endpoint | Status | Notes |
|---|---|---|
| `POST /{id}/clip` (create) | ❌ | Returns a *plausible* success response with a real-looking `clip_id` and `status: "pending"`, but `create_clip_task` is a complete no-op (`# TODO: Implement clip creation`). No ffmpeg ever runs, nothing is saved to the DB. Confirmed: the returned `clip_id` immediately 404s on lookup. This is the most misleading stub in the app — it looks like it worked. |
| `GET /api/clips`, `GET /api/clips/{id}`, download, thumbnail, batch, reel creation | ❌ | All stubs |

## 7. Frontend UI

| Feature | Status | Notes |
|---|---|---|
| Home page (status, version, video count) | ✅ | Real data |
| Nav routing (Home/Upload/Search/Videos/API Docs) | ✅ | Retested this session — works correctly. (Flagged as broken in an earlier session, but not reproducible on retest; likely a stale-tab issue, not a real bug) |
| WebSocket live progress updates | ✅ | Confirmed throughout dozens of live processing runs this session |
| "View Summary" popup | ✅ | Fixed this session — was a truncating `alert()`, now a proper themed modal |
| "View Highlights" popup | ✅ | Fixed this session — was a blank `alert()` on zero results, now a proper modal with a clean empty state |
| Video list / detail modal | ✅ | Real data |

---

## Summary

**What genuinely works, end-to-end, with real AI models and no mocks:** the entire core pipeline — ingest (YouTube + local upload) → frame/scene/audio/visual/speaker analysis → summarization → highlight detection → transcript+scene semantic search → frontend display. This is the majority of the product's value and it is real.

**What's still a facade:** anything downstream of the core pipeline that was scaffolded but never connected — chapters, timeline, clip creation/export, video Q&A, similar-video search, frame/CLIP visual search, transcript-specific search, streaming ingestion, and the separate `/process` + `/reprocess` endpoints. These all return plausible, well-formed API responses (this is what made them easy to miss originally) while doing nothing.
