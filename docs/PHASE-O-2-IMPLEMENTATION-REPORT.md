# Phase O.2 Implementation Report

## Problem
In Phase O.1, GIS map markers and camera location representation required strict alignment with the authoritative camera catalogue used by Live Monitoring. The objective for Phase O.2 was to ensure that all 30 SentinelVision cameras (`cam01` through `cam30`) are faithfully represented using the backend as the single source of truth, with zero fabricated or random geographic coordinates.

## Root Cause
Previously, frontend map components lacked visible permanent camera markers/tooltips, explicit display of coordinate provenance status (`coordinate_source`, `coordinate_approximate`), and a dedicated list for cameras whose exact coordinates could not be safely verified.

## Coordinate Source & Nominatim Protocol
- **Source Priority**:
  1. Existing trusted database/catalogue coordinates.
  2. Official camera catalogue (`cameras.json`).
  3. Carefully verified place-level coordinates using OpenStreetMap Nominatim.
- **Separate Re-runnable Importer**: Created `backend/scripts/import_verified_coords.py` which executes Nominatim geocoding independently with rate-limiting (1 request/sec), respectful User-Agent headers, and strict context validation.
- **Zero Fabrication Policy**: Unresolved locations (e.g. `cam27`, `cam28`, `cam29`, `cam30`) remain strictly `latitude = NULL`, `longitude = NULL`, `coordinate_source = NULL`, `coordinate_approximate = NULL`.

## Metrics
- **Total Camera Records**: 30 / 30
- **Mapped Cameras**: 5 / 30
- **Unresolved (Location Unavailable)**: 25 / 30
- **Verified Explicit Coordinates**: 4
- **Approximate Coordinates**: 1

## GIS Map & UI Changes
1. **Visible Marker Labels**: Uses Leaflet Tooltip with `permanent: true` showing `CAM_ID - Camera Name/Location` for all mapped markers.
2. **Interactive Popup**: Shows Camera ID, Camera Name, Location text, Coordinate status (`coordinate_source`), Live status (`ONLINE`/`OFFLINE`), AI Status (`ACTIVE`/`INACTIVE`), and interactive actions:
   - **View Live**: Triggers navigation to the live monitoring feed without exposing RTSP credentials.
   - **Camera Details**: Selects camera inspector view.
3. **Dynamic Top Metrics**: Displays dynamic counts (`Cameras: 30`, `Mapped: 5`, `Location unavailable: 25`).
4. **Location Unavailable List**: Below the map, renders all 25 unmapped cameras with their preserved Camera ID, Name, and Location text.

## Security Verification
- Zero RTSP credentials exposed in API endpoints (`/api/cameras`, `/api/cameras/{id}`).
- Browser streams consume authenticated server-side HLS relay endpoints.

## Test Verification
- **Backend Test Suite**: 406 / 406 passed (`python -m pytest`).
- **Frontend Build**: `npm run build` completed cleanly without errors.

## Manual Verification
Verified cameras `cam01`, `cam27`, `cam28`, `cam29`, and `cam30`:
- Name and location text preserved verbatim from catalogue.
- `cam27`, `cam28`, `cam29` remain 3 distinct records.
- Markers render strictly for mapped cameras.
- "View Live" correctly switches active live stream.

## Remaining Limitations
- 25 cameras remain unmapped pending physical GPS surveying or official catalogue coordinate updates.
