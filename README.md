# SentinelVision: AI-Powered Tactical Traffic & Security Intelligence Platform

![SentinelVision Architecture](frontend/stitch_sentinelvision_traffic_intelligence_platform/sentinelvision_tactical_ai_command_system/code.html)

**SentinelVision** is an end-to-end, enterprise-grade AI traffic monitoring, ANPR (Automatic Number Plate Recognition), vehicle tracking, and security surveillance platform. Engineered for real-time edge and cloud deployments, it processes high-throughput RTSP video streams with GPU acceleration to deliver dynamic zone counting, vehicle classification, license plate recognition, automated watchlist alerting, and detailed investigative history.

---

## Key Features

### 🤖 Advanced AI Computer Vision Pipeline
- **Real-Time Vehicle Detection:** Powered by YOLO (YOLO11) with PyTorch CUDA GPU acceleration.
- **Multi-Object Tracking:** ByteTrack integration with track continuity management and class stabilization across multi-frame sequences.
- **Zone & Directional Traffic Counting:** Region-of-Interest (ROI) IN/OUT spatial counters for lane and perimeter analytics.
- **ANPR & OCR Engine:** Automatic license plate detection and high-accuracy text extraction with multi-frame confidence aggregation.
- **Automated Security Alert Engine:** Real-time matching against watchlists (Stolen, BOLO, Suspicious) with instant alert generation.

### 📹 Enterprise Camera Ingestion
- **RTSP Connection Handling:** Reconnect and exponential backoff retry algorithms with TCP transport support.
- **Credential Isolation:** Strict environment-based credentials (`.env`) with automated URL redaction in logs to prevent credential leakage.
- **PTS-Based Synchronization:** Frame timing management to maintain accurate temporal sync.

### ⚡ High-Performance FastAPI Backend
- **RESTful API Ecosystem:** Endpoints for live camera metadata, vehicle events, zone counters, ANPR reads, watchlist management, system health metrics, and history search.
- **Database Abstraction:** Optimized SQLite persistence layer with repository patterns.
- **Robust Verification:** Comprehensive test suite covering DB operations, API endpoints, camera streams, and AI engines.

### 🎨 Modern Command & Control Frontend
- **Built with React + TypeScript + Vite + Tailwind CSS.**
- **Tactical Dark Theme:** Glassmorphism UI tailored for defense and surveillance command centers.
- **Real-Time Live Monitoring:** Live camera grid, zone counter tallies, and stream health status.
- **Interactive Dashboards:**
  - **Overview Dashboard:** High-level metrics, real-time activity, and zone counts.
  - **Live CCTV Monitoring:** Multi-stream layout and camera feed controls.
  - **Vehicle Intelligence:** Categorized vehicle logs, class distribution, and track timelines.
  - **ANPR & License Plate Search:** Exact and partial plate queries with confidence scoring.
  - **Watchlist Management:** Add, edit, or flag vehicles on watchlist tiers.
  - **Security Alerts Panel:** Real-time threat feed with severity ratings and action items.
  - **Vehicle History & Investigation:** Advanced multi-filter historical queries.
  - **System Health:** GPU memory utilization, RTSP pipeline latency, database statistics, and service health status.

---

## Architecture Overview

```
                          ┌────────────────────────┐
                          │  RTSP Camera Grid /    │
                          │   Video Feed Input     │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │    Camera Ingestion    │
                          │ (RTSP / TCP / Backoff) │
                          └───────────┬────────────┘
                                      │
                                      ▼
        ┌───────────────────────────────────────────────────────────┐
        │                     AI Vision Engine                      │
        │  ┌───────────────────────┐    ┌────────────────────────┐  │
        │  │ YOLO Vehicle Detector │ ──▶│   ByteTrack Tracker    │  │
        │  └───────────────────────┘    └───────────┬────────────┘  │
        │                                           │               │
        │  ┌───────────────────────┐    ┌───────────▼────────────┐  │
        │  │  ANPR / OCR Pipeline  │ ◀──│ Zone Counter / IN-OUT  │  │
        │  └───────────────────────┘    └────────────────────────┘  │
        └─────────────────────────────┬─────────────────────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │ FastAPI Backend & DB   │
                          │  (SQLite Persistence & │
                          │   Watchlist Engine)    │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │ React + TS Command UI  │
                          │ (Vite / Tailwind CSS)  │
                          └────────────────────────┘
```

---

## Directory Structure

```
SentinelVision/
├── backend/
│   ├── ai/                  # YOLO, ByteTrack, ANPR, OCR, Zone Counter, Class Stabilizer
│   ├── api/                 # FastAPI routes, schemas, dependency injection
│   ├── camera/              # RTSP stream abstraction & credential management
│   ├── db/                  # SQLite models, database initialization, repositories
│   └── services/            # Security Alert engine & business logic
├── frontend/
│   └── sentinelvision/      # React + TypeScript + Vite Frontend Application
│       ├── src/
│       │   ├── api/         # Axios API client
│       │   ├── components/  # Reusable UI components (StatCard, Layout, Loading, etc.)
│       │   ├── pages/       # Dashboard pages (Overview, Live, ANPR, Watchlist, Alerts, etc.)
│       │   └── types/       # TypeScript interfaces & API models
│       ├── index.html
│       ├── package.json
│       └── vite.config.ts
├── .env.example             # Template for local environment configuration
├── .gitignore               # Excludes secrets, models, database, node_modules, and virtualenvs
├── package.json
├── start_frontend.bat       # Helper script to launch frontend dev server
└── verify_runtime.py        # System verification script
```

---

## Getting Started

### Prerequisites

- **Python:** 3.10 or higher
- **Node.js:** v18.x or higher & `npm`
- **GPU Acceleration (Optional but Recommended):** NVIDIA GPU with CUDA support & PyTorch with CUDA support

---

### Setup Instructions

#### 1. Clone the Repository
```bash
git clone https://github.com/Parth1020738/SENTINELVISION.git
cd SENTINELVISION
```

#### 2. Environment Configuration
Copy `.env.example` to `.env` in the project root:
```bash
cp .env.example .env
```
Fill in your configuration details (e.g., RTSP credentials, database path):
```ini
SENTINEL_RTSP_EMAIL=your_email@example.com
SENTINEL_RTSP_PASSWORD=your_secure_password
SENTINELVISION_DB_PATH=data/sentinelvision.db
```

> **Security Note:** Never commit your `.env` file or SQLite database file to Git.

#### 3. Backend Setup & Run

Create and activate a virtual environment:
```bash
python -m venv myenv
# On Windows:
myenv\Scripts\activate
# On Linux/macOS:
source myenv/bin/activate
```

Install backend dependencies:
```bash
pip install -r requirements.txt
```

Launch the FastAPI Backend server:
```bash
uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```
*API documentation will be accessible at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)*

#### 4. Frontend Setup & Run

Navigate to the frontend folder and install Node dependencies:
```bash
cd frontend/sentinelvision
npm install
```

Start the Vite development server:
```bash
npm run dev
```
*The command center dashboard will open at [http://127.0.0.1:5173](http://127.0.0.1:5173)*

---

## Running Verification & Tests

### Backend Tests
Compile python source files and execute the pytest suite:
```bash
# Verify compilation
python -m compileall backend

# Run backend unit & integration tests
python -m pytest -q
```

### Frontend Build Verification
Validate TypeScript types and generate production bundle:
```bash
cd frontend/sentinelvision
npm run build
```

---

## Security & Best Practices

- **Zero Secret Exposure:** Credentials are pulled dynamically from OS environment variables or local `.env`.
- **RTSP Redaction:** All URL formatting utilities automatically mask username/password details before logging or storing metadata.
- **Ignored Artifacts:** Binary model files (`*.pt`), SQLite databases (`*.db`), video captures (`videos/`), and Python cache (`__pycache__`) are protected by `.gitignore`.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
