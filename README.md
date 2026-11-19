# AI Gaming Shorts Generator — Production Release (v1.0.0)

A local-first, privacy-respecting, zero-cloud-cost AI workstation for turning long gaming streams and YouTube videos into viral, creator-quality 9:16 vertical YouTube Shorts and TikToks.

Built with an auditable multi-track Edit Decision List (EDL) engine, hardware-accelerated rendering, real-time Hinglish normalization, automated sound design, and live-stream rolling capture.

---

## 1. System Architecture Overview

```text
                                  INPUT SOURCE
                                       │
                      ┌────────────────┴────────────────┐
                      │                                 │
                 NORMAL VIDEO                      LIVE STREAM
             (VOD / Long Stream)              (Continuous Stream)
                      │                                 │
           yt-dlp + Chunk Processor             Rolling Capture Engine
           (15m Chunks, Resumable)              (60s Segments, 15s Overlap)
                      │                                 │
                      └────────────────┬────────────────┘
                                       │
                               TRANSCRIPTION
                       faster-whisper on CUDA/FP16
                        Word-Level Timestamps
                                       │
                         CANDIDATE INTELLIGENCE
                     Hook-Event-Payoff Windowing
                  6-Factor Auditable Event Scoring
                   Global Diversity & Deduplication
                                       │
                       CREATOR QUALITY ENGINE (7E)
                    Pacing, Visuals, Audio & Polish
                  Classification: STRONG / REVIEW / REJECT
                                       │
                     MULTI-TRACK TIMELINE / EDL (8)
                   Deterministic JSON Edit Decision List
                   Human Corrections & Boundary Trimming
                                       │
                   SELECTIVE RENDERING PIPELINE (3-6A)
                     Layouts: Smart Crop / Blur / Facecam
                      Karaoke ASS Subtitles + Emojis
                        Contextual Zooms, Shakes & Flashes
                      SFX Mixing + Dynamic Speech Ducking
                                       │
                          PUBLISHING PACKAGES (6B)
                     SEO Titles, Descriptions, Hashtags
                       High-Res Clickable Thumbnails
                                       │
                     REACT PRODUCTION DASHBOARD (7B)
                     Real-Time SSE Telemetry & Player
```

---

## 2. Hardware & System Prerequisites

- **Operating System**: Windows 10/11 (or Linux with FFmpeg installed).
- **Python**: Version `3.11.x` 64-bit.
- **Node.js**: Version `18.x` or higher (for the React Dashboard UI).
- **FFmpeg**: Version `5.0+` with `h264_nvenc` and `ffprobe` installed on system PATH or WinGet packages.
- **NVIDIA GPU**: Recommended 4GB+ VRAM (e.g. RTX 3050 or higher) for NVENC acceleration and CUDA Whisper transcription. Automatic fallback to CPU (`libx264`, CPU Whisper) is supported.
- **Disk Storage**: At least 5GB free disk space for temporary media processing.

---

## 3. Installation & Setup

### A. Clone and Setup Python Virtual Environment
```powershell
# Navigate to the project root
cd "D:\AI Clipper"

# Create and activate virtual environment (if not already created)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt
```

### B. Setup React Dashboard Frontend
```powershell
cd frontend
npm install
npm run build
cd ..
```

---

## 4. Running the Application

### Option 1: Full-Stack Production Mode
Start the FastAPI backend server (which also serves the compiled React production SPA):
```powershell
.\venv\Scripts\python -m uvicorn backend.app.server:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at: **`http://localhost:8000`**

### Option 2: Frontend Development Mode
Run the Vite development server with hot-module reloading:
```powershell
# Terminal 1: Backend API
.\venv\Scripts\python -m uvicorn backend.app.server:app --host 127.0.0.1 --port 8000

# Terminal 2: Vite React Frontend
cd frontend
npm run dev
```
Open your browser at: **`http://localhost:5173`**

---

## 5. Core Operational Workflows

### Workflow A: Normal Video & VOD Clipping
1. Open the Dashboard and click **New Project**.
2. Paste any YouTube URL or local file path (e.g., `https://www.youtube.com/watch?v=EdtUDpqjltA`).
3. Select **Normal Video** mode and configure your preferences:
   - Target Short duration (`auto`, `15-30s`, `30-60s`, `60-180s`).
   - Subtitle language (`auto`, `original`, `english`, `hindi`, `hinglish`).
   - Target layout (`smart_crop`, `blurred_background`, `facecam_gameplay`).
4. Click **Start Analysis**. The system will download audio, transcribe speech with word-level timestamps, detect gaming climax events, and rank candidate moments.
5. Review the detected candidates and their **Creator Quality Scores** (`STRONG`, `REVIEW`, `REJECT`).
6. Select desired candidates and click **Render Selected** to generate finished 9:16 vertical Shorts.

### Workflow B: Long-Stream Processing (4–6+ Hours)
- Streams exceeding 30 minutes are automatically chunked into manageable 15-minute segments.
- Transcripts and audio analysis are persisted per chunk, allowing **instant resumption** if interrupted.
- Candidates are evaluated across chunk boundaries, deduplicated globally, and ranked with strict temporal and narrative diversity.

### Workflow C: Live Stream Rolling Capture
1. Select **Live Stream** mode in the New Project modal.
2. Enter the live stream URL (or a local simulation test video).
3. The system initiates a rolling 60-second capture engine with 15-second sliding overlaps.
4. Candidates are detected in near real-time as the stream progresses.
5. Pause, resume, or stop capture anytime without losing analyzed candidates.

### Workflow D: Interactive Multi-Track Timeline Editor (EDL)
1. In the candidate list or player view, click **Edit Timeline**.
2. Interactively modify:
   - Subtitle wording, line breaks, and styling.
   - Word-level karaoke timing.
   - Hinglish spelling and normalization.
   - Contextual emoji placement and pop animations.
   - Visual effects (Punch Zoom, Subtle Zoom, Shake, Flash).
   - Audio SFX (Whoosh, Impact, Pop) and speech ducking attenuation.
   - Candidate boundary in/out points.
3. Click **Save Timeline** — changes are recorded in `timeline.json` without modifying the original video.
4. Click **Re-Render Short** — the selective renderer re-runs *only* the affected filter stages (e.g., subtitles or audio), preserving unmodified video render caches.

---

## 6. Key Production Hardening & Reliability Features

| Reliability Area | Implementation Safeguard |
| :--- | :--- |
| **Crash & Interruption Recovery** | On startup, `ProjectManager._reconcile_interrupted_projects()` checks for projects stuck in transient states (`analyzing`, `rendering`, `capturing`) and safely marks them as `recoverable` or `failed` with diagnostic code `SERVER_RESTARTED`. |
| **Atomic File Operations** | All databases, timelines, manifests, and sessions (`projects.json`, `timeline.json`, `live_session.json`) are written via atomic temporary files (`.tmp` $\to$ `.replace`), preventing corrupt files during sudden power loss. |
| **Subprocess Leaks & Cancellation** | `ProcessTracker` registers all child FFmpeg and worker processes. When a user cancels a job, `psutil` cleanly terminates the entire process tree. |
| **Subprocess Timeouts** | Every FFmpeg invocation is protected with strict timeouts (`30s` to `300s`), preventing infinite hangs on corrupt media streams. |
| **VRAM & Memory Safety** | Whisper model is explicitly unloaded (`unload_model()`) and garbage-collected immediately after transcription, ensuring zero VRAM contention for heavy NVENC 1080x1920 filtergraphs. |
| **Pre-Flight Disk Safety** | Before job creation and live capture, the system verifies disk writability and ensures at least 5GB free space. |
| **Path Traversal Protection** | All project IDs and endpoints are strictly validated against `^[a-zA-Z0-9_\-]+$`, preventing directory traversal attacks. |
| **Diagnostic Health API** | `/api/health` and `/health` report real-time Python version, FFmpeg binary path/version, CUDA acceleration status, available RAM, and disk storage metrics. |

---

## 7. Testing & Verification

The repository contains an exhaustive automated test suite covering all 10 project phases.

### Run All Unit Tests
```powershell
.\venv\Scripts\python -m unittest discover tests
```
*Expected: 206 passing tests, 0 failures, 0 errors.*

### Run Phase 9/10 End-to-End Validation
```powershell
.\venv\Scripts\python scripts/validate_phase9_live.py
.\venv\Scripts\python scripts/validate_phase10_release.py
```

### Build Frontend Production Assets
```powershell
npm --prefix frontend run build
```

---

## 8. License & Local Privacy

This software operates **100% locally**. All AI models (Whisper, rule-based NLP, OpenCV, FFmpeg) run directly on your hardware. No media, audio, transcripts, or credentials are ever transmitted to any external cloud service.
