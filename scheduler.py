import csv
import glob
import json
import os
import sys
from datetime import date, datetime

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKING_LOG = os.path.join(_DIR, "uploaded_pam.json")
TRANSFORMED_DIR = os.path.join(_DIR, "transformed")

sys.path.insert(0, _DIR)
from transform import DEFAULT_COLUMNS, DEFAULT_TIMESTAMP_FORMAT, output_header, parse_raw_pam
from uploader import upload_file


def _load_config():
    for name in ("config.local.yaml", "config.yaml"):
        path = os.path.join(_DIR, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError("No config file found in windows_pam/")


try:
    cfg = _load_config()
    station_id = cfg["station"]["id"]
    if station_id == "CHANGE_ME":
        raise ValueError("station.id in config.yaml/config.local.yaml is still the placeholder — set it before running")
except Exception as e:
    print(f"[Config] Failed to load configuration: {e}")
    raise SystemExit(1)

SOURCE_DIR = cfg["pam"]["source_dir"] or os.path.join(os.path.expanduser("~"), "Desktop", "PAM data")
CHANNELS = set(cfg["pam"]["channels"])
VARIABLES = cfg["pam"]["variables"]
# Merged (not replaced) with defaults, so a config that only overrides one
# column (e.g. just "timestamp") doesn't drop the rest.
COLUMNS = {**DEFAULT_COLUMNS, **(cfg["pam"].get("columns") or {})}
TIMESTAMP_FORMAT = cfg["pam"].get("timestamp_format") or DEFAULT_TIMESTAMP_FORMAT
YEAR_OVERRIDE = cfg["pam"].get("year_override")
OUTPUT_HEADER = output_header(VARIABLES)


def _load_tracking():
    if os.path.exists(TRACKING_LOG):
        try:
            with open(TRACKING_LOG) as f:
                return json.load(f)
        except Exception as e:
            print(f"[Tracking] {TRACKING_LOG} unreadable, treating as empty this run | {e}")
            return {}
    return {}


def _save_tracking(tracking):
    tmp_path = f"{TRACKING_LOG}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(tracking, f, indent=2)
    os.replace(tmp_path, TRACKING_LOG)


def _write_transformed_csv(rows, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def upload_job():
    if not os.path.exists(SOURCE_DIR):
        print(f"[PAM] Source dir not found: {SOURCE_DIR}")
        return

    tracking = _load_tracking()
    today = date.today()

    raw_files = sorted(glob.glob(os.path.join(SOURCE_DIR, "*.csv")))
    if not raw_files:
        print(f"[PAM] No CSV files in {SOURCE_DIR}")
        return

    uploaded_count = 0
    for filepath in raw_files:
        filename = os.path.basename(filepath)
        mtime_date = date.fromtimestamp(os.path.getmtime(filepath))
        is_today = mtime_date == today

        # A file not modified today is done growing — once it's been
        # uploaded successfully, skip it on future cycles instead of
        # re-sending an unchanged file forever.
        if not is_today and tracking.get(filename):
            continue

        year = YEAR_OVERRIDE or mtime_date.year
        rows = parse_raw_pam(filepath, CHANNELS, year, VARIABLES, COLUMNS, TIMESTAMP_FORMAT)
        if not rows:
            print(f"[PAM] {filename}: no matching rows (channels {sorted(CHANNELS)}), skipping")
            continue

        transformed_path = os.path.join(TRANSFORMED_DIR, filename)
        _write_transformed_csv(rows, transformed_path)

        remote_path = f"{station_id}/sensor/PAM/{filename}"
        ok = upload_file(transformed_path, remote_path, cfg["http"]["base_url"].rstrip("/"), cfg["http"]["shared_key"])
        if ok:
            uploaded_count += 1
            if not is_today:
                tracking[filename] = True
                _save_tracking(tracking)

    print(f"[PAM] {uploaded_count}/{len(raw_files)} file(s) uploaded this cycle")


if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(
        upload_job, "interval", seconds=cfg["pam"]["interval_seconds"],
        next_run_time=datetime.now(),
    )
    print(f"[Scheduler] {station_id} | HTTP {cfg['http']['base_url']}")
    print(f"  Source dir: {SOURCE_DIR}")
    print(f"  Upload interval: {cfg['pam']['interval_seconds']}s")
    scheduler.start()
