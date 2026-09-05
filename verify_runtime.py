"""
Phase 9.3 - Full End-to-End Runtime Verification Script
"""
import subprocess
import time
import sys
import json
import urllib.request
import os

def curl(url):
    """Fetch a URL and return the response text."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode('utf-8')
    except Exception as e:
        return -1, str(e)

def main():
    print("=" * 70)
    print("SENTINELVISION PHASE 9.3 - END-TO-END RUNTIME VERIFICATION")
    print("=" * 70)

    # Check if backend is already running
    status, body = curl("http://127.0.0.1:8000/health")
    if status != 200:
        print("\n[1] Starting backend server...")
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.api.main:app",
             "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print(f"    Backend PID: {backend_proc.pid}")
        time.sleep(5)
    else:
        print("\n[1] Backend already running.")

    # Verify health
    print("\n[2] Verifying /health...")
    status, body = curl("http://127.0.0.1:8000/health")
    print(f"    HTTP {status}: {body}")

    # Verify cameras
    print("\n[3] Verifying /api/cameras...")
    status, body = curl("http://127.0.0.1:8000/api/cameras")
    print(f"    HTTP {status}: {body[:500]}")

    # Verify counts
    print("\n[4] Verifying /api/counts...")
    status, body = curl("http://127.0.0.1:8000/api/counts")
    print(f"    HTTP {status}: {body[:500]}")

    # Verify alerts
    print("\n[5] Verifying /api/alerts...")
    status, body = curl("http://127.0.0.1:8000/api/alerts")
    print(f"    HTTP {status}: {body[:500]}")

    # Verify plates search (empty state)
    print("\n[6] Verifying /api/plates/search (empty state)...")
    status, body = curl("http://127.0.0.1:8000/api/plates/search?plate=TEST")
    print(f"    HTTP {status}: {body[:500]}")

    # Verify watchlist (create, list, update, delete)
    print("\n[7] Testing watchlist CRUD...")
    # Create
    data = json.dumps({"plate": "ZTEST789", "reason": "temp test", "category": "OTHER", "priority": "LOW"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/api/watchlist", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"    POST create: HTTP {resp.status} - {resp.read().decode()[:200]}")
    except Exception as e:
        print(f"    POST create: FAILED - {e}")

    # List
    status, body = curl("http://127.0.0.1:8000/api/watchlist")
    print(f"    GET list: HTTP {status} - {body[:300]}")

    # Update
    data = json.dumps({"notes": "updated test notes"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/api/watchlist/ZTEST789",
                                  data=data, headers={"Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"    PATCH update: HTTP {resp.status} - {resp.read().decode()[:200]}")
    except Exception as e:
        print(f"    PATCH update: FAILED - {e}")

    # Delete (deactivate)
    req = urllib.request.Request("http://127.0.0.1:8000/api/watchlist/ZTEST789", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"    DELETE deactivate: HTTP {resp.status} - {resp.read().decode()[:200]}")
    except Exception as e:
        print(f"    DELETE deactivate: FAILED - {e}")

    # Verify database
    print("\n[8] Verifying database...")
    db_path = "data/sentinelvision.db"
    if os.path.exists(db_path):
        print(f"    DB exists at {db_path} ({os.path.getsize(db_path)} bytes)")
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for table in ['cameras', 'vehicle_events', 'zone_counts', 'plate_reads', 'alerts', 'watchlist_entries']:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"    {table}: {count} records")
        conn.close()
    else:
        print("    DB NOT FOUND!")

    # Check if frontend is running
    print("\n[9] Checking frontend...")
    status, body = curl("http://127.0.0.1:5173/")
    if status == 200:
        print(f"    Frontend running: HTTP {status}")
    else:
        print(f"    Frontend not running (HTTP {status})")
        print("    Starting frontend...")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
