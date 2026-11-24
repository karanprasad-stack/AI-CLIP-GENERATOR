# AI Clipper: Mobile (Android APK) & Production Docker Guide

This guide details how to build and deploy **AI Clipper** across two production environments:
1. **Containerized Server Deployment**: Run the full backend and frontend via **Docker** & **Docker Compose** on any local Windows/Linux PC or remote cloud VPS.
2. **Native Mobile App**: Build and run an installable **Android APK** powered by **Capacitor**, enabling creators to monitor rendering, edit timelines, and publish shorts on mobile phones or tablets connected to their PC/cloud backend.

---

## 1. Production Docker Setup

The repository includes a production multi-stage `Dockerfile` and a ready-to-run `docker-compose.yml`.

### Architecture
- **Stage 1 (Frontend Builder)**: Node.js 20 Alpine compiles the React Vite application into optimized static assets in `/frontend/dist`.
- **Stage 2 (Runtime)**: Python 3.11 Slim bundles `ffmpeg`, `libass`, TrueType fonts (DejaVu/FreeFont), sound libraries (`libsndfile`), OpenCV dependencies, and production Python packages (`fastapi`, `uvicorn`, `ctranslate2`, `faster-whisper`, `yt-dlp`).
- **Persistence**: Volumes are mounted for `output/`, `config/`, and `assets/` so rendered shorts, configurations, and downloaded models are not lost across container restarts.

### Quick Start with Docker Compose

1. **Build and start the container in the background**:
   ```bash
   docker compose up --build -d
   ```

2. **Check container status & health**:
   ```bash
   docker compose ps
   ```
   The container has an automatic `HEALTHCHECK` hitting `http://localhost:8000/api/health` every 30 seconds.

3. **View live logs**:
   ```bash
   docker compose logs -f ai-clipper
   ```

4. **Access the workstation**:
   Open [http://localhost:8000](http://localhost:8000) in your web browser.

5. **Stop the container**:
   ```bash
   docker compose down
   ```

### Optional: NVIDIA GPU Acceleration in Docker
If you have an NVIDIA GPU and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed on your host system:
Uncomment the `deploy` reservation block in `docker-compose.yml`:
```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

---

## 2. Capacitor Android APK Project

The mobile client is packaged using **Capacitor** (`@capacitor/android`, `@capacitor/core`, `@capacitor/cli`). It wraps the responsive React UI into an Android project located in `frontend/android`.

### Prerequisites
- Node.js 20+
- [Android Studio](https://developer.android.com/studio) with Android SDK and Build Tools installed
- Android device or Android Emulator (API level 24+)

### Development & Build Workflow

1. **Build Frontend & Sync Assets to Android**:
   ```bash
   npm --prefix frontend run build
   npm --prefix frontend run cap:sync
   ```
   *(Or run `cd frontend && npm run build && npx cap sync android`)*

2. **Open the Project in Android Studio**:
   ```bash
   npm --prefix frontend run cap:open
   ```
   *(Or launch Android Studio and open the folder `frontend/android`)*

3. **Build the Installable APK**:
   In Android Studio:
   - Select **Build** > **Build Bundle(s) / APK(s)** > **Build APK(s)**.
   - Once Gradle finishes building, click **locate** to retrieve `app-debug.apk` (typically under `frontend/android/app/build/outputs/apk/debug/app-debug.apk`).
   - Transfer and install `app-debug.apk` on your Android phone or tablet.

### Android Cleartext & Permissions
- `AndroidManifest.xml` includes:
  - `<uses-permission android:name="android.permission.INTERNET" />`
  - `android:usesCleartextTraffic="true"` (allows the app to connect over standard HTTP to your PC's local LAN IP like `http://192.168.1.x:8000`).
- `capacitor.config.ts` sets `server.cleartext: true` and `androidScheme: 'http'` for compatibility with local video streaming and SSE progress events.

---

## 3. Connecting Mobile APK to Your PC Backend

Because the Android APK runs on your phone's processor, video rendering and Whisper transcription remain executed by your high-power PC or GPU server.

### Connecting via Local Wi-Fi
1. Ensure your PC and mobile device are connected to the **same Wi-Fi network**.
2. Find your PC's local IP address:
   - On Windows: Run `ipconfig` in PowerShell and find your **IPv4 Address** (e.g. `192.168.1.100`).
3. Start the AI Clipper server on your PC:
   ```bash
   .\venv\Scripts\python.exe -m uvicorn backend.app.server:app --host 0.0.0.0 --port 8000
   ```
   *(Or run via `docker compose up -d`)*
4. Open the **AI Clipper** app on your phone.
5. Tap **Settings** (gear icon) > **Server & Mobile** tab.
6. Enter `http://192.168.1.100:8000` (replacing with your actual PC IP).
7. Tap **Test Connection** — you will see a green badge with the measured round-trip latency.
8. Tap **Save Server URL**. The mobile app is now connected!

### Connecting via Tailscale / WireGuard (Anywhere Access)
If you want to clip videos from your phone while away from home (on cellular data):
1. Install [Tailscale](https://tailscale.com/) on both your PC and your phone.
2. Enter your PC's 100.x.y.z Tailscale IP in **Settings** > **Server & Mobile** (e.g. `http://100.85.12.34:8000`).

---

## 4. Configuration Reference

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `CORS_ALLOWED_ORIGINS` | `""` | Comma-delimited extra CORS origins allowed by the backend (e.g. `http://192.168.1.50:5173`). |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint for local LLM semantic reranking and metadata generation. In Docker Compose, set to `http://host.docker.internal:11434`. |
| `DEFAULT_OUTPUT_DIR` | `./output` | Base directory for storing project metadata, audio, and rendered MP4 files. |

---

## 5. Troubleshooting Checklist

- **CORS Error**: The backend server dynamically allows `capacitor://localhost`, `http://localhost`, `127.0.0.1`, and private LAN subnets (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`). If you use an unconventional subnet, specify it in `CORS_ALLOWED_ORIGINS`.
- **Connection Timed Out on Mobile**:
  1. Check Windows Defender Firewall: Ensure incoming traffic on port `8000` is allowed for private networks.
  2. Test PC reachability from mobile browser: Open Chrome on your phone and navigate to `http://<PC-IP>:8000/api/health`. You should receive a JSON response with `"status": "ok"`.
- **404 on API Routes**: The backend SPA router explicitly blocks paths starting with `api/` from falling back to `index.html`, ensuring missing API endpoints correctly return HTTP 404 JSON.
