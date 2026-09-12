# SentinelVision — Unified Tactical AI CCTV Command Platform

**SentinelVision** is an enterprise-grade tactical AI intelligence platform engineered for real-time video analytics, vehicle tracking, Automated Number Plate Recognition (ANPR), and cross-camera vehicle intelligence across large-scale CCTV networks.

Designed as a high-throughput, security-first command platform, SentinelVision unifies heterogeneous RTSP stream ingestion, deep learning computer vision pipelines, real-time spatial GIS mapping, and automated alert correlation into a centralized operational dashboard.

---

## 1. Problem Statement

Modern state-level traffic management and defense infrastructure (such as the Gujarat government CCTV network) faces significant operational challenges:

- **Heterogeneous Camera Networks**: Thousands of cameras deployed across municipalities, highways, and public safety departments utilize disparate hardware, VMS platforms, resolutions, and video codecs.
- **Fragmented Departmental Silos**: Police, municipal corporations, traffic management authorities, and highway command centers operate isolated video feeds without cross-departmental intelligence sharing.
- **Geographically Distributed Streams**: Monitoring cameras spread across thousands of square kilometers makes manual human surveillance inefficient and prone to missed critical events.
- **Scale Requirements**: State-level infrastructure projects require scalable architecture capable of scaling toward **~80,000 concurrent CCTV cameras**.
- **Lack of Unified Tracking**: Traditional CCTV systems record localized video loops but cannot trace vehicle movement trajectories across multiple physical camera gates.

---

## 2. Solution Architecture

SentinelVision resolves these challenges through a **unified, hybrid AI intelligence platform**:

1. **Centralized Stream Normalization**: Converts raw RTSP streams and evaluation feeds into unified, authenticated low-latency MJPEG frame relays.
2. **Decoupled Edge/Server AI Pipeline**: Orchestrates real-time object detection (YOLO11m), multi-object tracking (ByteTrack), vehicle class stabilization, and license plate OCR (ANPR) on bounded worker pools.
3. **Cross-Camera Vehicle Identity Correlation**: Reconstructs global vehicle identity timelines (`GlobalVehicle`) and spatial routes across independent camera gates (`CrossCameraObservation`).
4. **Interactive GIS Command Map**: Displays real-time geospatial camera nodes, spatial telemetry, and vehicle movement paths on Leaflet-powered GIS maps.
5. **Real-time Event Hub & Security Engine**: Emits instant WebSocket notifications for watchlist matches (`AlertEngine`), security audit logs, and operational telemetry.

---

## 3. Key Capabilities

- **Multi-Camera CCTV Integration**: Live catalogue management supporting authenticated government RTSP feeds and local evaluation feeds.
- **Real-Time Live Monitoring**: Low-latency stream relay with dynamic AI worker state indicators (`STARTING`, `ACTIVE`, `INACTIVE`, `STOPPED`, `ERROR`).
- **YOLO11 Vehicle Detection**: High-accuracy multi-class detection for cars, motorcycles, buses, and trucks.
- **ByteTrack Vehicle Tracking**: Association of spatial bounding boxes across sequential video frames with unique track IDs.
- **Vehicle Class Stabilization**: Temporal voting window to resolve ambiguous or fluctuating vehicle class predictions.
- **Track Continuity Manager**: Persistence of canonical vehicle identities across stream interruptions or re-entries.
- **ANPR & OCR Engine**: Automated plate detection, character OCR, state-specific text normalization, and multi-frame confidence voting.
- **Watchlist & Alert Triangulation**: Automated background correlation of detected plates against security watchlists with priority alerts (`CRITICAL`, `HIGH`, `MEDIUM`).
- **Cross-Camera Vehicle Tracing**: Automated timeline reconstruction and geographic mapping of vehicle routes across multiple camera nodes.
- **Interactive GIS Map**: Real-time Leaflet map displaying real government camera nodes and vehicle travel paths.
- **System Telemetry & Health Monitoring**: Continuous monitoring of database connection, RTSP latency, frame rates, and worker CPU/GPU load.
- **Evidence Reporting**: One-click export of cross-camera vehicle intelligence as CSV data or formatted PDF investigation reports.
- **Enterprise Security & Audit**: Environment-isolated secrets, Role-Based Access Control (RBAC), JWT authentication, rate limiting, security headers, and SQLite audit logging.

---

## 4. End-to-End AI Pipeline Flow

The production AI processing pipeline operates frame-by-frame with zero external data leakage:

```
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────────────────────┐
│  Camera Stream  │ ---> │     Frame Ingestion      │ ---> │ YOLO11m Vehicle Detector    │
│  (RTSP / MP4)   │      │ (CameraStream / Worker)  │      │ (Cars, Bikes, Buses, Trucks)│
└─────────────────┘      └──────────────────────────┘      └─────────────────────────────┘
                                                                          │
                                                                          ▼
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────────────────────┐
│ Zone Analytics  │ <--- │ Canonical Continuity ID  │ <--- │      ByteTrack Engine       │
│ (IN / OUT Count)│      │(TrackContinuityManager)  │      │ (Multi-Object Tracking)     │
└─────────────────┘      └──────────────────────────┘      └─────────────────────────────┘
        │
        ▼
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────────────────────┐
│   ANPR Engine   │ ---> │    Plate OCR & Vote      │ ---> │ Watchlist & Alert Engine    │
│(Plate Detector) │      │ (EasyOCR + Normalizer)   │      │ (Priority Match & Hub)      │
└─────────────────┘      └──────────────────────────┘      └─────────────────────────────┘
                                                                          │
                                                                          ▼
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────────────────────┐
│  SQLite DB      │ ---> │ WebSocket Event Hub      │ ---> │ Command Center Dashboard    │
│ Persistence     │      │ (Real-Time Broadcast)    │      │ (React + TS + GIS Map)      │
└─────────────────┘      └──────────────────────────┘      └─────────────────────────────┘
```

---

## 5. System Architecture

SentinelVision is structured as a modular, decoupled web application:

- **Backend**: FastAPI (Python 3.12) providing async REST endpoints, WebSocket streaming, and background thread execution.
- **Database & Persistence**: SQLite relational database using repository pattern (`CameraRepository`, `VehicleRepository`, `PlateRepository`, `ZoneRepository`, `WatchlistRepository`, `AlertRepository`, `GlobalVehicleRepository`, `CameraHealthRepository`, `AuditRepository`).
- **AI Core**: PyTorch, Ultralytics YOLO11m, ByteTrack, EasyOCR, and custom tracking continuity algorithms.
- **Frontend**: React 18, TypeScript, Vite, TailwindCSS, React-Leaflet, and Lucide/Material Symbols.
- **Services**: `EventHub` for WebSocket broadcasting, `AttentionEngine` for operational camera state computation, and `AlertEngine` for watchlist matching.

---

## 6. Camera Feed Integration

SentinelVision supports two distinct camera stream modes:

1. **Real Government CCTV Cameras (`cam01` .. `cam30`)**:
   - The authoritative catalogue of 30 physical government CCTV feeds.
   - Configured with official RTSP URLs, authenticating server-side without exposing credentials to frontend clients.
   - Assigned verified geographic coordinates on the GIS map.

2. **Local Evaluation Demo Feeds (`v_cam01` .. `v_cam06`)**:
   - Evaluation feeds initialized dynamically from actual local MP4 video assets.
   - Run through the **exact same production AI pipeline** (YOLO11m + ByteTrack + ANPR) as live RTSP feeds.
   - Clearly badged as **DEMO / VIRTUAL** in the user interface to ensure operational transparency.
   - Demo feeds are non-geographical and excluded from the GIS physical camera map.

---

## 7. ANPR & License Plate Recognition

The Automated Number Plate Recognition (ANPR) subsystem operates in five stages:

1. **License Plate Crop Extraction**: Small localized plate regions are extracted from detected vehicle bounding boxes.
2. **Character OCR Engine**: EasyOCR reads raw textual characters from plate crops.
3. **Text Normalization**: Converts raw text to uppercase, strips non-alphanumeric noise, and standardizes state registration syntax (e.g., `HR 99 ABV 2812` -> `HR99ABV2812`).
4. **Format Sanity Validation**: Verifies plate strings against tolerant Indian vehicle registration rules.
5. **Multi-Frame Confidence Voting**: Aggregates OCR reads across consecutive track frames to select the highest-confidence normalized plate text.

---

## 8. Multi-Camera Vehicle Intelligence

Cross-camera vehicle intelligence resolves isolated camera detections into unified vehicle journeys:

- **Global Vehicle Identity (`GlobalVehicle`)**: Unique ID (e.g., `GV-000001`) assigned to a vehicle based on its normalized license plate.
- **Cross-Camera Observations (`CrossCameraObservation`)**: Chronological sequence of detections across multiple camera gates.
- **Movement Route Reconstruction**: Maps camera coordinates and observation timestamps to plot geographical travel routes on Leaflet GIS maps.
- **Intelligence Export**: One-click CSV and PDF report generation for law enforcement investigations.

---

## 9. GIS Command Map

The embedded GIS Command Map provides real-time spatial awareness:

- Displays the **30 real government CCTV camera nodes** across Gujarat.
- Live marker color coding:
  - **Green**: Online & Normal
  - **Cyan**: Active AI Processing
  - **Blue Pulsing**: Currently Selected Camera
  - **Red / Amber**: Offline or Attention Required
- Interactive popups providing operational metadata, camera location, and streaming controls.
- Vehicle Route Overlay: Renders directional polyline routes connecting consecutive camera waypoints for tracked vehicles.

---

## 10. Security & Compliance

SentinelVision implements strict government-grade security controls:

- **Isolated Credentials**: RTSP passwords and database secrets reside exclusively in environment variables and are never exposed in source code or API responses.
- **Role-Based Access Control (RBAC)**: Enforces role permissions (`ADMIN`, `OPERATOR`, `VIEWER`).
- **Session Security**: JWT bearer tokens and access code verification (`SENTINEL_ACCESS_CODE`).
- **Rate Limiting**: IP-based rate limiting on authentication and access gate endpoints.
- **Audit Logging**: Comprehensive security audit log table recording all login attempts, watchlist modifications, and evidence exports.
- **Security Headers & CORS**: Strict HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`) and origin-restricted CORS middleware.

---

## 11. Scalability Roadmap (~80,000 Cameras)

While the current proof-of-concept (PoC) operates on a bounded multi-worker architecture tailored for evaluation hardware, the system is designed to scale toward **~80,000 state-wide cameras**:

```
                              ┌─────────────────────────────────────────┐
                              │     Distributed Edge Ingestion Nodes    │
                              │ (RTSP Stream Decoding & Motion Filtering)│
                              └─────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────┐      ┌─────────────────────────────────────────┐
│     Central Metadata Indexer         │ <--- │ Distributed GPU Inference Cluster       │
│(Global Vehicle & Spatial Tracking DB)│      │(Bounded YOLO + ByteTrack Worker Nodes)  │
└──────────────────────────────────────┘      └─────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  State-Wide Command Center Dashboard │
│  (Distributed Regional Map Buffers)  │
└──────────────────────────────────────┘
```

- **Bounded Worker Manager**: Limits concurrent active GPU workers (e.g., `max_workers=3` on local hardware) with dynamic eviction on camera selection.
- **Distributed Edge Ingestion**: Edge video processing units perform initial frame extraction, offloading heavy inference from central servers.
- **Event-Driven Broker Architecture**: Transition from in-memory `EventHub` to distributed message brokers (Kafka/RabbitMQ) for multi-region event distribution.
- **Time-Series Indexing**: Sharded PostgreSQL/TimescaleDB partitioning for rapid querying across billions of vehicle records.

---

## 12. Technology Stack

- **Core Backend**: Python 3.12, FastAPI, Uvicorn, SQLite3.
- **Computer Vision & AI**: PyTorch, Ultralytics YOLO11m, ByteTrack, EasyOCR, OpenCV.
- **Frontend Core**: React 18, TypeScript, Vite, TailwindCSS.
- **GIS & Visualization**: Leaflet, React-Leaflet, Lucide Icons, Material Symbols.
- **Reporting & Export**: ReportLab, FPDF2.
- **Testing & Tooling**: Pytest, Pytest-Asyncio, HTTPX, Vite Build.

---

## 13. Local Setup Instructions (Windows)

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** & **npm**
- Git

### 1. Clone Repository & Setup Virtual Environment
```powershell
git clone https://github.com/Parth1020738/SentinelVision.git
cd SentinelVision

# Create Python virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```
*(Optionally adjust configuration parameters in `.env`. Credentials and tokens default to safe development values.)*

### 3. Install Frontend Dependencies
```powershell
cd frontend\sentinelvision
npm install
cd ..\..
```

### 4. Run Backend Server
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

### 5. Run Frontend Development Server
In a separate terminal:
```powershell
cd frontend\sentinelvision
npm run dev
```
Open your browser at `http://localhost:5173`. Access Code default: `SENTINEL2026`.

---

## 14. Demo Instructions

1. **Live Camera Grid**: Navigate to **Live Monitoring** to inspect the 30 real government CCTV camera catalogue.
2. **Camera Switching**: Select any camera (e.g., `cam01`, `cam02`, `cam05`). Observe the smooth stream switching overlay (`CONNECTING TO CAMERA... Waiting for first frame...`).
3. **Demo Video Processing**: Select any registered demo feed (`v_cam01` .. `v_cam06`). The production AI pipeline will run live detection, tracking, and ANPR on video frames.
4. **GIS Command Map**: Open **GIS Command Map** to view the physical distribution of real government cameras across Gujarat.
5. **Vehicle Investigation**: Search plates in **Plate Search** or export evidence reports in **Vehicle Investigation**.

*Note: Demo video assets are excluded from Git repository commits due to size considerations.*

---

## 15. Testing & Verification

The test suite contains **416 automated tests** covering API endpoints, AI tracking, ANPR normalization, multi-camera ingestion, database persistence, and RBAC security.

To execute the test suite:
```powershell
pytest -q
```

**Verified Test Result**: `416 passed in 57.77s`.

To verify the frontend production build:
```powershell
cd frontend\sentinelvision
npm run build
```

**Verified Build Result**: `built in 4.54s` (Zero TypeScript or Vite compilation errors).

---

## 16. Project Status & PoC Scope

| Feature / Module | Status | Notes |
| :--- | :--- | :--- |
| **30 Government Camera Grid** | **Implemented** | Authoritative metadata & RTSP stream integration |
| **Demo Video AI Pipeline** | **Implemented** | Identical pipeline execution on local video feeds |
| **YOLO11m + ByteTrack** | **Implemented** | Multi-class detection & spatial tracking |
| **ANPR / EasyOCR Engine** | **Implemented** | Text normalization & multi-frame voting |
| **Watchlist & Alert Engine** | **Implemented** | Background correlation & WebSocket alerts |
| **Global Vehicle Identity** | **Implemented** | Cross-camera movement tracing & PDF reports |
| **GIS Command Map** | **Implemented** | Real camera mapping & route polylines |
| **System Telemetry & Health** | **Implemented** | Dynamic worker monitoring |
| **Security / RBAC / Audit** | **Implemented** | JWT auth, access gate & audit log table |
| **Large-Scale Multi-Node Cluster**| *Future Scope* | Production scale (~80k cameras) architecture |

---

## License

Confidential — Prepared for Government CCTV & Tactical AI Demonstration.
