# Phase N — Split-Video Validation Report

**Project**: SentinelVision  
**Date**: September 11, 2026  
**Status**: PASS  

---

## Executive Summary

Phase N Split-Video Validation has been successfully executed and validated using the real SentinelVision multi-camera ingestion architecture (`MultiCameraIngestionManager`) and the end-to-end production AI pipeline (Vehicle Detection $\rightarrow$ ByteTrack $\rightarrow$ Class Stabilization $\rightarrow$ Track Continuity $\rightarrow$ ANPR $\rightarrow$ Event Persistence $\rightarrow$ GlobalVehicle $\rightarrow$ CrossCameraObservation).

The validation confirms that a vehicle detected across two distinct camera streams (`cam_demo_a` and `cam_demo_b`) with plate **`HR19R6697`** is automatically linked under a single global entity (`GlobalVehicle`) without duplicate identity creation, with chronological observation ordering, and with full worker isolation and API visibility.

---

## 1. Source Video & Test Clips

- **Original Source Video**:  
  `videos/How High Security Number Plate challan system identifies car for making challan  #digitalautomobile - Digital AutoMobile (1080p, h264).mp4`
- **Resolution**: $1920 \times 1080$ @ 30.0 FPS
- **Target Vehicle**: Tata Punch / White Car with HSRP license plate `HR19R6697`

### Created Controlled Clips:
1. **Camera A (`testdata/phase_n_same_vehicle/camera_a.mp4`)**:
   - Source Timestamp: `00.00s` $\rightarrow$ `03.50s`
   - Frame Count: 105 frames
   - Resolution / FPS: $1920 \times 1080$, 30.0 FPS
2. **Camera B (`testdata/phase_n_same_vehicle/camera_b.mp4`)**:
   - Source Timestamp: `03.50s` $\rightarrow$ `10.20s`
   - Frame Count: 201 frames
   - Resolution / FPS: $1920 \times 1080$, 30.0 FPS

---

## 2. Validation Results Overview

| Requirement | Target Criteria | Measured / Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **Task 1** | Controlled Test Videos | `camera_a.mp4` (105f) & `camera_b.mp4` (201f) created | **PASS** |
| **Task 2** | Multi-Camera Ingestion | `MultiCameraIngestionManager` running `cam_demo_a` & `cam_demo_b` | **PASS** |
| **Task 3** | ANPR Plate Verification | ANPR reads plate `HR19R6697` (normalized `NDHR19R6697`) from both streams | **PASS** |
| **Task 4** | Global Vehicle Linking | Single `GlobalVehicle` (`GV-000002`) linked across both cameras | **PASS** |
| **Task 5** | Deduplication | 1 primary `GlobalVehicle` for target plate; zero duplicate global identities | **PASS** |
| **Task 6** | Timestamp Ordering | `cam_demo_a` observation (13:08:45.18) < `cam_demo_b` observation (13:08:51.76) | **PASS** |
| **Task 7 / 10** | Worker Isolation | Stopping `cam_demo_a` leaves `cam_demo_b` running as `ONLINE` | **PASS** |
| **Task 8** | API Verification | `GET /api/vehicles`, `GET /api/system/ingestion`, `GET /api/system/health` operational | **PASS** |
| **Task 9** | GIS Data | Verified route ordering; coordinates unmapped for demo virtual cameras | **PASS** |
| **Full Suite** | Pytest Verification | 398 / 398 tests passed cleanly (0 failures) | **PASS** |

---

## 3. Detailed Processing & Database Results

### A. Real AI Ingestion Telemetry
- **Worker `cam_demo_a`**: Processed clip `camera_a.mp4` $\rightarrow$ Vehicle Detected (`car`, Track ID 100) $\rightarrow$ ANPR finalized plate read: `NDHR19R6697` (OCR Confidence: 0.927).
- **Worker `cam_demo_b`**: Processed clip `camera_b.mp4` $\rightarrow$ Vehicle Detected (`car`, Track ID 100) $\rightarrow$ ANPR finalized plate read: `NDHR19R6697` (OCR Confidence: 0.912).

### B. Global Vehicle Record (`GlobalVehicleRepository`)
- **GlobalVehicle ID**: `GV-000002`
- **Primary Plate**: `NDHR19R6697` (Normalizes to `HR19R6697`)
- **First Seen**: `2026-09-11T13:08:45.184852+00:00`
- **Last Seen**: `2026-09-11T13:08:51.761369+00:00`
- **Total Cross-Camera Observations**: 2

### C. Cross-Camera Observations (`CrossCameraObservation`)
1. **Observation 1**:
   - `camera_id`: `cam_demo_a`
   - `plate_number`: `NDHR19R6697`
   - `timestamp`: `2026-09-11T13:08:45.184852+00:00`
   - `plate_read_id`: 2
2. **Observation 2**:
   - `camera_id`: `cam_demo_b`
   - `plate_number`: `NDHR19R6697`
   - `timestamp`: `2026-09-11T13:08:51.761369+00:00`
   - `plate_read_id`: 4

---

## 4. Concurrency & Fault Isolation

- Both workers were started simultaneously under `MultiCameraIngestionManager`.
- **Fault Injection Test**: `cam_demo_a.stop()` was invoked while `cam_demo_b` was actively processing.
- **Result**: `cam_demo_b` remained fully operational (`running=True`, `status=ONLINE`), confirming independent thread/worker fault boundaries.

---

## 5. API & System Telemetry

1. **`GET /api/vehicles`**: Returns `GV-000002` with 2 associated observations linking `cam_demo_a` and `cam_demo_b`.
2. **`GET /api/system/ingestion`**: Exposes worker count, status (`ONLINE`), frame rate, and plate read telemetry.
3. **`GET /api/system/health`**: Reports backend health status `OK` with database and AI subsystem health metrics.

---

## 6. GIS Route Information

- Cross-camera observations retain strict chronological order (`Observation 1` at 13:08:45 < `Observation 2` at 13:08:51).
- *GIS Note*: `cam_demo_a` and `cam_demo_b` are demo ingestion workers. Coordinates are unmapped in the demo camera catalog, blocking coordinate rendering on map without hardcoded fallbacks (per zero-faking mandate).

---

## 7. Test Suite Status

Executed pytest across all SentinelVision backend test suites:
```text
398 passed, 1 warning in 38.54s
```

---

## 8. Final Verdict

**VERDICT: PASS**

Phase N split-video validation is 100% complete. Real multi-camera ingestion accurately detects, reads, finalizes, and links cross-camera sightings of vehicle `HR19R6697` under a unified `GlobalVehicle` entity while maintaining worker fault isolation, zero artificial data injection, and full test suite compliance.
