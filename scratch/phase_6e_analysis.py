"""Extract comprehensive Phase 6E analytics from the logs, database, and source diagnostics."""

import json
import sqlite3
from pathlib import Path
from app.config.settings import get_settings
from app.sources.lever import LeverJobSource
from app.sources.greenhouse import GreenhouseJobSource

def main():
    settings = get_settings()
    profile = settings.load_profile()

    # Read database jobs
    conn = sqlite3.connect(settings.DATABASE_PATH)
    rows = conn.execute("SELECT id, source, title, company, location, url, date_posted, date_found, extra_metadata FROM jobs").fetchall()
    conn.close()

    print(f"Total jobs in DB: {len(rows)}")

    # We also have the full task log from the first run task-368
    task_log_path = Path(r"C:\Users\gauta\.gemini\antigravity-ide\brain\2e37b0ac-40fb-4f15-80de-887d361a3cb3\.system_generated\tasks\task-368.log")
    if task_log_path.exists():
        with open(task_log_path, "r", encoding="utf-8", errors="replace") as f:
            log_content = f.read()
    else:
        log_content = ""

    print("Log size bytes:", len(log_content))

if __name__ == "__main__":
    main()
