"""
load_database.py: loads the generated CSV files into a SQLite database.

Creates data/scorecard.db with:
    The seven raw-data tables (employees, communications, training, surveys,
    survey_comments, usage, outcomes), loaded as-is from data/*.csv.
    Four reference tables built from rollout_config.toml:
        departments      one row per department (metric, direction, baseline)
        settings         ONE row holding every date and threshold the SQL uses
        calendar         one row per day, with week number and workday flag
        survey_schedule  one row per survey wave, with its start and end date

The SQL metric files read thresholds and dates from `settings`, so changing
the settings file changes the metrics without touching any SQL.

The departments table deliberately leaves out `test_pattern`: the metrics
must find each department's pattern from the data alone.

Run from the project folder:   python src/load_database.py
"""

import csv
import sqlite3
import tomllib
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "rollout_config.toml"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "scorecard.db"

SCHEMA = """
CREATE TABLE employees (
    employee_id     TEXT PRIMARY KEY,
    department      TEXT NOT NULL,
    loa_start_date  TEXT,              -- NULL = no leave of absence
    loa_end_date    TEXT
);
CREATE TABLE communications (
    employee_id     TEXT NOT NULL REFERENCES employees,
    email_type      TEXT NOT NULL,
    sent_date       TEXT NOT NULL,
    opened_date     TEXT               -- NULL = never opened
);
CREATE TABLE training (
    employee_id     TEXT PRIMARY KEY REFERENCES employees,
    assigned_date   TEXT NOT NULL,
    registered_date TEXT,              -- NULL = never registered
    completed_date  TEXT               -- NULL = never completed
);
CREATE TABLE surveys (
    employee_id     TEXT NOT NULL REFERENCES employees,
    survey_week     INTEGER NOT NULL,
    response_date   TEXT NOT NULL,
    question_id     TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    score           INTEGER NOT NULL
);
CREATE TABLE survey_comments (
    employee_id     TEXT NOT NULL REFERENCES employees,
    survey_week     INTEGER NOT NULL,
    response_date   TEXT NOT NULL,
    comment         TEXT NOT NULL
);
CREATE TABLE usage (
    employee_id     TEXT NOT NULL REFERENCES employees,
    usage_date      TEXT NOT NULL,     -- one row per day with 1+ prompt
    prompts         INTEGER NOT NULL
);
CREATE TABLE outcomes (
    employee_id     TEXT NOT NULL REFERENCES employees,
    week            INTEGER NOT NULL,
    week_start      TEXT NOT NULL,
    outcome_value   REAL NOT NULL,
    volume          INTEGER NOT NULL
);
CREATE TABLE departments (
    department       TEXT PRIMARY KEY,
    sort_order       INTEGER NOT NULL,
    headcount        INTEGER NOT NULL,
    outcome_metric   TEXT NOT NULL,
    outcome_unit     TEXT NOT NULL,
    better_when      TEXT NOT NULL CHECK (better_when IN ('lower', 'higher')),
    outcome_baseline REAL NOT NULL,
    volume_unit      TEXT NOT NULL
);
CREATE TABLE calendar (
    cal_date    TEXT PRIMARY KEY,
    week        INTEGER NOT NULL,
    is_workday  INTEGER NOT NULL       -- 1 = Monday-Friday
);
CREATE TABLE survey_schedule (
    survey_week INTEGER PRIMARY KEY,
    wave_number INTEGER NOT NULL,
    wave_start  TEXT NOT NULL,
    wave_end    TEXT NOT NULL
);
CREATE INDEX idx_usage_emp_date    ON usage (employee_id, usage_date);
CREATE INDEX idx_outcomes_emp_week ON outcomes (employee_id, week);
CREATE INDEX idx_surveys_emp_week  ON surveys (employee_id, survey_week);
CREATE INDEX idx_comms_emp         ON communications (employee_id, email_type);
"""


def build_settings(cfg):
    """Every date and threshold the SQL needs, worked out from the settings file."""
    roll, sched, th = cfg["rollout"], cfg["schedule"], cfg["thresholds"]
    start = roll["first_week_start"]
    total_weeks = roll["baseline_weeks"] + roll["rollout_weeks"]

    def week_start(n):
        return start + timedelta(weeks=n - 1)

    data_end = start + timedelta(weeks=total_weeks, days=-1)
    email_week = dict(zip(sched["communication_types"], sched["communication_weeks"]))
    links = sched["registration_link_in"]
    reminder = week_start(email_week[links[1]]) if len(links) > 1 else None

    return {
        "organization":            roll["organization"],
        "change_name":             roll["change_name"],
        "first_week_start":        start,
        "baseline_weeks":          roll["baseline_weeks"],
        "total_weeks":             total_weeks,
        "go_live_date":            week_start(roll["baseline_weeks"] + 1),
        "data_end_date":           data_end,
        "training_start_date":     week_start(min(sched["training_weeks"])),
        "training_deadline_date":  week_start(sched["training_deadline_week"]) + timedelta(days=6),
        "reminder_sent_date":      reminder,
        "reach_green":             th["reach"]["green"],
        "reach_amber":             th["reach"]["amber"],
        "favorable_minimum":       th["readiness"]["favorable_minimum"],
        "low_response_rate":       th["readiness"]["low_response_rate"],
        "readiness_green":         th["readiness"]["green"],
        "readiness_amber":         th["readiness"]["amber"],
        "adoption_window_days":    th["adoption"]["window_days"],
        "adoption_window_start":   data_end - timedelta(days=th["adoption"]["window_days"] - 1),
        "minimum_prompts":         th["adoption"]["minimum_prompts"],
        "heavy_use_active_days":   th["adoption"]["heavy_use_active_days"],
        "minimum_use_gate":        th["adoption"]["minimum_use_gate"],
        "adoption_green":          th["adoption"]["green"],
        "adoption_amber":          th["adoption"]["amber"],
        "outcome_comparison_weeks": th["outcomes"]["comparison_weeks"],
        "outcomes_green":          th["outcomes"]["green"],
        "outcomes_amber":          th["outcomes"]["amber"],
    }


def load_csv(con, table):
    """Insert data/<table>.csv into <table>. Empty cells become NULL."""
    with open(DATA_DIR / f"{table}.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [[v if v != "" else None for v in row.values()] for row in reader]
        cols = reader.fieldnames
    con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
    return len(rows)


def main():
    with open(CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)

    DB_PATH.unlink(missing_ok=True)                  # rebuild from scratch every time
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    # --- Reference tables from the settings file -----------------------------
    settings = build_settings(cfg)
    con.execute(f"CREATE TABLE settings ({', '.join(settings)})")
    con.execute(f"INSERT INTO settings VALUES ({', '.join('?' * len(settings))})",
                [v.isoformat() if hasattr(v, "isoformat") else v for v in settings.values()])

    con.executemany("INSERT INTO departments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [(d["name"], i + 1, d["headcount"], d["outcome_metric"], d["outcome_unit"],
                      d["better_when"], d["outcome_baseline"], d["volume_unit"])
                     for i, d in enumerate(cfg["departments"])])

    start = cfg["rollout"]["first_week_start"]
    con.executemany("INSERT INTO calendar VALUES (?, ?, ?)",
                    [((start + timedelta(days=d)).isoformat(), d // 7 + 1, int(d % 7 < 5))
                     for d in range(7 * settings["total_weeks"])])

    con.executemany("INSERT INTO survey_schedule VALUES (?, ?, ?, ?)",
                    [(w, i + 1, (start + timedelta(weeks=w - 1)).isoformat(),
                      (start + timedelta(weeks=w - 1, days=6)).isoformat())
                     for i, w in enumerate(cfg["schedule"]["survey_weeks"])])

    # --- Raw data ---------------------------------------------------------------
    print(f"Loading into {DB_PATH.relative_to(ROOT)}")
    for table in ["employees", "communications", "training", "surveys",
                  "survey_comments", "usage", "outcomes"]:
        print(f"  {table:<16} {load_csv(con, table):>7,} rows")

    con.commit()
    con.close()


if __name__ == "__main__":
    main()
