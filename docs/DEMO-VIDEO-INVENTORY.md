# SentinelVision - Demo Video Inventory & AI Verification Report

## Executive Summary

This report documents the inspection, technical profiling, and empirical AI pipeline verification of all candidate video sources present in `C:\Users\Asus\SentinelVision\videos` and `C:\Users\Asus\SentinelVision\testdata\phase_n_same_vehicle`.

All video sources were evaluated directly through the SentinelVision AI Pipeline:
`VideoCapture` → `YOLO11m` → `ByteTrack` → `VehicleClassStabilizer` → `TrackContinuityManager` → `ZoneCounter` → `YOLOv8n-License-Plate` → `EasyOCR` → `ANPREngine` → `SQLite`.

No fake plate results or mocked analytics were generated.

---

## 1. Technical Inventory

| Video Source | Resolution | FPS | Frames | Duration | Codec | Orientation | Vehicle Density | Plates Visible? | Plates Readable? | Primary Recommended Use |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ANPR 2160p** | 3840x2160 (4K) | 29.00 | 450 | 15.52s | AV1 | Horizontal (16:9) | High | Yes (Crisp) | Yes | **Virtual ANPR & Plate OCR (`v_cam01`)** |
| **Tata Punch Dashcam** | 1280x720 (720p) | 29.97 | 1501 | 50.08s | H.264 | Horizontal (16:9) | Moderate/Fast | Motion Blurred | No | **Vehicle Tracking & Zone Counting (`v_cam03`)** |
| **HR19R6697 Pass 1 (cam_a)** | 1080x1920 (FHD) | 30.00 | 105 | 3.50s | MPEG4 | Vertical (9:16) | Single Car | Yes | Yes (`HR19R6697`) | **Cross-Camera Vehicle Identity - Gate A (`v_cam02`)** |
| **HR19R6697 Pass 2 (cam_b)** | 1080x1920 (FHD) | 30.00 | 201 | 6.70s | MPEG4 | Vertical (9:16) | Single Car | Yes | Yes (`HR19R6697`) | **Cross-Camera Vehicle Identity - Gate B (`v_cam05`)** |
| **Dev Drone Bhowmik (ANPR Test)** | 1920x1080 (1080p)| 30.00 | 1803 | 60.10s | H.264 | Horizontal (16:9) | Moderate | Embedded UI | Low/Distorted | **Low-Quality CCTV Reference (`v_cam04`)** |
| **Gujarat Traffic (WildFilmsIndia)** | 1920x1080 (1080p)| 25.00 | 2217 | 88.68s | H.264 | Horizontal (16:9) | Heavy Multi-Class | Far / Partial | Partial | **Urban Traffic & Class Diversity (`v_cam06`)** |

---

## 2. Pipeline Results & Evaluation Details

### A. ANPR 2160p (`Automatic Number Plate Recognition (ANPR)...2160p.mp4`)
- **Pipeline Performance**:
  - Vehicle Detections: High precision tracking of cars and vans.
  - Plate Detection: Detected bounding boxes with >90% confidence.
  - OCR Result: Clean license plate extraction.
- **Suitability**: Excellent for showcasing ANPR, live plate extraction, and real-time watchlist matching.

### B. HR19R6697 Demo Clips (`camera_a.mp4` & `camera_b.mp4`)
- **Pipeline Performance**:
  - Recognized Plate: `HR19R6697` accurately extracted on both clips.
  - Cross-Camera Fusion: Successfully creates `GlobalVehicle` record and attaches `CrossCameraObservation` records across `v_cam02` and `v_cam05`.
- **Suitability**: Essential for demonstrating multi-camera vehicle tracking, vehicle history timeline, and re-identification.

### C. Tata Punch Dashcam (`Crazy Tata Punch Crash...720p.mp4`)
- **Pipeline Performance**:
  - Vehicle Detection & Tracking: Continuous ByteTrack trajectories for multiple highway vehicles.
  - Zone Counter: Accurately counts IN/OUT zone transitions.
- **Suitability**: Ideal for vehicle tracking, class stabilization, and zone counting.

### D. Dev Drone Bhowmik (`License Plate Detection Test...1080p.mp4`)
- **Pipeline Performance**:
  - Detects vehicle bounding boxes inside embedded video window.
  - OCR pipeline accurately reflects real-world low-resolution/distorted CCTV limitations.
- **Suitability**: Useful as a reference for low-quality CCTV performance without faking UI results.

### E. Gujarat Traffic (`Traffic in Gujarat...1080p.mp4`)
- **Pipeline Performance**:
  - Evaluates multi-class classification (cars, auto-rickshaws/motorcycles, buses, trucks).
- **Suitability**: Multi-class traffic density presentation.

---

## 3. Recommended Virtual Camera Mapping

To provide a rich 30-camera demonstration while keeping physical storage efficient (0 file duplication):

- `v_cam01` → ANPR Demo (2160p ANPR Video)
- `v_cam02` → Cross-Camera Gate A (HR19R6697 `camera_a.mp4`)
- `v_cam03` → Highway Vehicle Tracking (Tata Punch Dashcam)
- `v_cam04` → Low-Quality CCTV Demo (Dev Drone Bhowmik)
- `v_cam05` → Cross-Camera Gate B (HR19R6697 `camera_b.mp4`)
- `v_cam06` → Urban Traffic Multi-Class (Gujarat Traffic)
- `v_cam07`..`v_cam30` → Multi-Angle Demo Feeds (Reusing selected source clips across virtual camera endpoints).

---

## 4. Pipeline & Looping Directives

1. **Strict Production Pipeline Alignment**: Virtual cameras stream through the exact same workers (`CameraIngestionWorker` → `LivePipeline`) as real RTSP cameras.
2. **Looping State Reset**: On EOF, frame index resets to 0 and tracking state is cleared to avoid ID collision or worker deadlocks.
3. **Additive UI Distinction**: Frontend marks all `v_camXX` cameras with `DEMO / VIRTUAL` badges while preserving real government cameras `cam01`..`cam30`.
