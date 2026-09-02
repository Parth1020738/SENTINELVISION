"""
SentinelVision - Phase 1 RTSP Camera Validation Tool

Tests the detection and tracking pipeline against a live RTSP stream.

Usage:
    python backend/ai/test_rtsp_camera.py --camera cam01 --seconds 30
    python backend/ai/test_rtsp_camera.py --camera cam01 --max-frames 500 --imgsz 640
"""

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

# Ensure project root is in path for direct script execution
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Camera configuration
# ---------------------------------------------------------------------------
CAMERA_URLS = {
    "cam01": "rtsp://103.250.160.189:8554/stream/cam01",
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SentinelVision Phase 1 - RTSP Camera Validation"
    )
    parser.add_argument(
        "--camera",
        type=str,
        default="cam01",
        choices=list(CAMERA_URLS.keys()),
        help="Camera identifier (default: cam01)",
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=30,
        help="Maximum duration to run in seconds (default: 30)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Maximum frames to process. 0 = unlimited (default: 0)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=1280,
        help="YOLO inference image size (default: 1280)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without display window",
    )
    return parser.parse_args()


def draw_observations(frame, observations):
    """Draw bounding boxes and labels on the frame for display."""
    display = frame.copy()

    for obs in observations:
        x1, y1, x2, y2 = obs.bbox
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

        # Color by class
        color_map = {
            "car": (0, 255, 0),
            "motorcycle": (0, 255, 255),
            "bus": (255, 0, 0),
            "truck": (0, 0, 255),
        }
        color = color_map.get(obs.class_name, (255, 255, 255))

        # Draw box
        cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

        # Draw label
        label = f"ID:{obs.raw_track_id} {obs.class_name} {obs.confidence:.2f}"
        cv2.putText(
            display,
            label,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )

    return display


def main() -> None:
    """Main validation routine."""
    args = parse_args()

    # ------------------------------------------------------------------
    # Import here to fail fast with clear error if ultralytics missing
    # ------------------------------------------------------------------
    from backend.ai.vehicle_tracker import VehicleTracker

    # ------------------------------------------------------------------
    # Resolve camera URL
    # ------------------------------------------------------------------
    camera_id = args.camera
    camera_url = CAMERA_URLS[camera_id]
    print(f"[TEST] Camera: {camera_id}")
    print(f"[TEST] RTSP URL: {camera_url}")

    # ------------------------------------------------------------------
    # Open RTSP stream
    # ------------------------------------------------------------------
    print("[TEST] Opening RTSP stream...")
    cap = cv2.VideoCapture(camera_url)

    if not cap.isOpened():
        print("[TEST] FAIL: Could not open RTSP stream")
        sys.exit(1)

    ret, first_frame = cap.read()
    if not ret or first_frame is None:
        print("[TEST] FAIL: Could not read first frame")
        cap.release()
        sys.exit(1)

    height, width = first_frame.shape[:2]
    print(f"[TEST] RTSP Connection: PASS")
    print(f"[TEST] Frame Resolution: {width}x{height}")

    # ------------------------------------------------------------------
    # Initialize tracker
    # ------------------------------------------------------------------
    print("[TEST] Loading YOLO model...")
    try:
        tracker = VehicleTracker(imgsz=args.imgsz)
    except Exception as e:
        print(f"[TEST] FAIL: Could not load model: {e}")
        cap.release()
        sys.exit(1)

    device_info = tracker.get_device_info()
    print(f"[TEST] YOLO Model Loaded: PASS")
    print(f"[TEST] GPU Available: {'YES' if device_info['cuda_available'] else 'NO'}")

    # ------------------------------------------------------------------
    # Process frames
    # ------------------------------------------------------------------
    max_frames = args.max_frames
    max_seconds = args.seconds
    headless = args.headless

    frame_number = 0
    total_detections = 0
    class_counts = defaultdict(int)
    all_track_ids = set()
    motorcycle_track_ids = set()
    start_time = time.time()

    print(f"[TEST] Processing for up to {max_seconds} seconds...")
    print("-" * 60)

    try:
        while True:
            # Check time limit
            elapsed = time.time() - start_time
            if elapsed >= max_seconds:
                print(f"\n[TEST] Time limit reached ({max_seconds}s)")
                break

            # Check frame limit
            if max_frames > 0 and frame_number >= max_frames:
                print(f"\n[TEST] Frame limit reached ({max_frames})")
                break

            # Read frame
            ret, frame = cap.read()
            if not ret or frame is None:
                print(f"\n[TEST] Frame read failed at frame {frame_number}")
                break

            frame_number += 1

            # Run tracking
            observations = tracker.track(frame, frame_number=frame_number)

            # Accumulate statistics
            num_obs = len(observations)
            total_detections += num_obs

            for obs in observations:
                class_counts[obs.class_name] += 1
                all_track_ids.add(obs.raw_track_id)
                if obs.class_name == "motorcycle":
                    motorcycle_track_ids.add(obs.raw_track_id)

            # Periodic status report (every 30 frames)
            if frame_number % 30 == 0:
                print(
                    f"FRAME: {frame_number} | "
                    f"DETECTIONS: {num_obs} | "
                    f"TOTAL: {total_detections} | "
                    f"MOTORCYCLES: {class_counts.get('motorcycle', 0)} | "
                    f"UNIQUE IDS: {len(all_track_ids)}"
                )

            # Display (unless headless)
            if not headless:
                display_frame = draw_observations(frame, observations)
                cv2.imshow("SentinelVision Phase 1 Test", display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("\n[TEST] User interrupted")
                    break

    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user")
    finally:
        cap.release()
        if not headless:
            cv2.destroyAllWindows()

    # ------------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------------
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 60)
    print("PHASE 1 VALIDATION SUMMARY")
    print("=" * 60)
    print(f"RTSP Connection:        PASS")
    print(f"Frame Resolution:       {width}x{height}")
    print(f"GPU Available:          {'YES' if device_info['cuda_available'] else 'NO'}")
    print(f"GPU Name:               {device_info['gpu_name']}")
    print(f"YOLO Model Loaded:      PASS")
    print(f"Vehicle Detections:     {total_detections}")
    print(f"Car Detections:         {class_counts.get('car', 0)}")
    print(f"Motorcycle Detections:  {class_counts.get('motorcycle', 0)}")
    print(f"Bus Detections:         {class_counts.get('bus', 0)}")
    print(f"Truck Detections:       {class_counts.get('truck', 0)}")
    print(f"Unique ByteTrack IDs:   {len(all_track_ids)}")
    print(f"Motorcycle Track IDs:   {len(motorcycle_track_ids)}")
    print(f"Frames Processed:       {frame_number}")
    print(f"Elapsed Time:           {elapsed_total:.1f}s")
    print("=" * 60)

    # Motorcycle status
    print("\nMOTORCYCLE STATUS:")
    if class_counts.get("motorcycle", 0) > 0:
        print("  -> motorcycles detected and tracked")
    elif total_detections > 0:
        print("  -> no motorcycles appeared during this sample")
    else:
        print("  -> no vehicles detected at all")

    # ByteTrack status
    print("\nBYTE TRACK STATUS:")
    if len(all_track_ids) > 0:
        print(f"  -> {len(all_track_ids)} unique track IDs assigned")
    else:
        print("  -> no track IDs assigned")


if __name__ == "__main__":
    main()
