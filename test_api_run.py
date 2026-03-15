import asyncio
import os
import signal
import subprocess
import time
import requests

def test_run():
    print("Starting API Server...")
    server = subprocess.Popen(
        ["uvicorn", "price_monitor.api.app:app", "--host", "127.0.0.1", "--port", "8085"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(3) # Wait for startup

    print("Triggering Scan API...")
    try:
        # Mock auth via headers if implemented or bypass if open locally for testing
        res = requests.post("http://127.0.0.1:8085/api/scan/trigger")
        print(f"Trigger Status: {res.status_code}")
        print(f"Trigger Response: {res.json()}")
        job_id = res.json().get("job_id")
        
        print("Waiting for scrape to progress...")
        for _ in range(30):
            time.sleep(2)
            check = requests.get("http://127.0.0.1:8085/api/collection/jobs")
            if check.status_code == 200:
                jobs = check.json().get("items", [])
                if jobs:
                    j = jobs[0]
                    print(f"Status: {j['status']} | Progress: {j['progress']}% | Offers: {j['success_items']}")
                    if j['status'] in ('SUCCESS', 'FAILED', 'CANCELLED'):
                        break
    except Exception as e:
        print(f"API Error: {e}")
    
    print("Shutting down server...")
    os.kill(server.pid, signal.SIGTERM)
    server.wait()

if __name__ == "__main__":
    test_run()
