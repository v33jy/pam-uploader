import time

import requests


def upload_file(filepath, remote_path, base_url, api_key, max_retries=3, timeout=60):
    """PUTs one file to the ingest endpoint, retrying with backoff on
    connection errors. Returns True on success, False if every attempt
    failed (caller just tries again next cycle — there's no partial state to
    clean up since the transformed file is fully regenerated each run)."""
    url = f"{base_url}/{remote_path}"
    for attempt in range(1, max_retries + 1):
        try:
            with open(filepath, "rb") as f:
                resp = requests.put(url, data=f, headers={"X-Api-Key": api_key}, timeout=timeout)
            if resp.status_code in (200, 204):
                print(f"[Upload] OK -> {remote_path}")
                return True
            if resp.status_code == 401:
                print("[Upload] Rejected (401) — wrong API key, retrying won't help. Giving up.")
                return False
            raise requests.RequestException(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            wait = 15 * attempt
            print(f"[Upload] Attempt {attempt}/{max_retries} failed for {remote_path} ({e}); retrying in {wait}s")
            if attempt < max_retries:
                time.sleep(wait)
    print(f"[Upload] Giving up on {remote_path} after {max_retries} attempts")
    return False
