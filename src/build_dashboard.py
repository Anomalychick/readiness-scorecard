"""
build_dashboard.py: writes the one-page HTML dashboard.

Reads the metric views from data/scorecard.db (run calculate_metrics.py
first), packs them into one JSON block, and drops that into
src/dashboard_template.html. The result, output/dashboard.html, is a single
file that opens in any browser. Charts use Chart.js, loaded from a CDN.

Every number on the dashboard comes from the SQL views; this script does
no calculating of its own, only selecting and formatting.

Run from the project folder:   python src/build_dashboard.py
"""

import importlib.util
import json
import sqlite3
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Reuse the findings rules from write_summary.py so the dashboard and the
# written summary always say the same thing.
_spec = importlib.util.spec_from_file_location("write_summary", ROOT / "src" / "write_summary.py")
write_summary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(write_summary)
DB_PATH = ROOT / "data" / "scorecard.db"
TEMPLATE = ROOT / "src" / "dashboard_template.html"
OUTPUT = ROOT / "output" / "dashboard.html"


def rows(con, query):
    cur = con.execute(query)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def ordered(view):
    """All rows of a view, in department display order."""
    return f"SELECT v.* FROM {view} v JOIN departments d USING (department) ORDER BY d.sort_order"


def main():
    if not DB_PATH.exists():
        raise SystemExit("No database found. Run load_database.py and calculate_metrics.py first.")
    with open(ROOT / "rollout_config.toml", "rb") as f:
        cfg = tomllib.load(f)
    con = sqlite3.connect(DB_PATH)
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'scorecard'").fetchone():
        raise SystemExit("Metric views missing. Run calculate_metrics.py first.")

    settings = rows(con, "SELECT * FROM settings")[0]
    th = cfg["thresholds"]
    findings = write_summary.build_findings(con, cfg)

    data = {
        "meta": {
            "author": cfg.get("project", {}).get("author", ""),
            "github_username": cfg.get("project", {}).get("github_username", ""),
            "organization": settings["organization"],
            "change_name": settings["change_name"],
            "change_type": cfg["rollout"]["change_type"],
            "first_week_start": settings["first_week_start"],
            "go_live_date": settings["go_live_date"],
            "training_deadline_date": settings["training_deadline_date"],
            "data_end_date": settings["data_end_date"],
            "adoption_window_start": settings["adoption_window_start"],
            "baseline_weeks": settings["baseline_weeks"],
            "total_weeks": settings["total_weeks"],
            "employees": con.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
            "survey_scale": th["readiness"]["scale_points"],
        },
        "thresholds": {
            name: {k: v for k, v in t.items()
                   if k in ("headline", "definition", "green", "amber", "minimum_use_gate",
                            "low_response_rate", "heavy_use_active_days", "favorable_minimum")}
            for name, t in th.items()
        },
        "findings": findings,
        "overview": write_summary.overview(con, findings),
        "departments": rows(con, "SELECT * FROM departments ORDER BY sort_order"),
        "scorecard": rows(con, "SELECT * FROM scorecard ORDER BY sort_order"),
        "reach": rows(con, ordered("reach_by_department")),
        "readiness_waves": rows(con, ordered("readiness_by_department_wave")
                                .replace("ORDER BY d.sort_order", "ORDER BY d.sort_order, v.wave_number")),
        "adoption": rows(con, ordered("adoption_by_department")),
        "trend": rows(con, ordered("adoption_trend").replace("ORDER BY d.sort_order",
                                                             "ORDER BY d.sort_order, v.week")),
        "distribution": rows(con, ordered("adoption_active_days_distribution")),
        "usage_training": rows(con, ordered("usage_by_training_period_department")),
        "outcomes": rows(con, ordered("outcomes_by_department")),
        "outcomes_weekly": rows(con, ordered("outcomes_by_department_week").replace(
            "ORDER BY d.sort_order", "ORDER BY d.sort_order, v.week")),
        "outcomes_training": rows(con, ordered("outcomes_by_training_period")),
        "outcomes_rating": rows(con, ordered("outcomes_by_adoption_rating")),
        "employees": rows(con, """
            SELECT e.employee_id, e.department,
                   r.loa_in_training_window, r.training_status, r.completed_date,
                   a.loa_in_window, a.adoption_rating, a.active_days_30,
                   o.baseline_value, o.recent_value, o.improvement_pct
            FROM employees e
            JOIN reach_by_employee    r USING (employee_id)
            JOIN adoption_by_employee a USING (employee_id)
            LEFT JOIN outcomes_by_employee o USING (employee_id)
            ORDER BY e.employee_id"""),
    }
    con.close()

    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DASHBOARD_DATA__", payload)
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(html) / 1024:,.0f} KB)")


if __name__ == "__main__":
    main()
