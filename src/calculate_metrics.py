"""
calculate_metrics.py: runs the SQL metric files and prints the scorecard.

1. Runs every file in sql/ in order (01_reach.sql ... 05_scorecard.sql).
   Each file creates VIEWS (saved queries) in data/scorecard.db.
2. Prints the scorecard and the key supporting tables.
3. Exports every view to output/metrics/<view>.csv so the numbers can be
   checked by hand in Excel.

Run from the project folder (after load_database.py):
    python src/calculate_metrics.py
"""

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "scorecard.db"
SQL_DIR = ROOT / "sql"
METRICS_DIR = ROOT / "output" / "metrics"

COLOR_MARK = {"Green": "G", "Amber": "A", "Red": "R"}


def print_table(con, title, query, columns=None):
    cur = con.execute(query)
    headers = columns or [d[0] for d in cur.description]
    rows = [["" if v is None else str(v) for v in row] for row in cur.fetchall()]
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    print(f"\n{title}")
    print("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(v.ljust(w) for v, w in zip(r, widths)))


def main():
    if not DB_PATH.exists():
        raise SystemExit("No database found. Run src/load_database.py first.")
    con = sqlite3.connect(DB_PATH)

    # 1. Run the SQL files in order
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        con.executescript(sql_file.read_text(encoding="utf-8"))
        print(f"Ran {sql_file.relative_to(ROOT)}")

    org, tool = con.execute("SELECT organization, change_name FROM settings").fetchone()
    print(f"\n=== {org}: {tool} readiness scorecard (SYNTHETIC DATA) ===")

    # 2. Print the scorecard and supporting tables
    print_table(con, "SCORECARD (Reach / Readiness / Adoption / Outcomes)", """
        SELECT department,
               on_time_rate || '% ' || reach_color                    AS reach,
               pct_favorable || '% ' || readiness_color
                 || CASE WHEN readiness_caution IS NOT NULL THEN ' (low response)' ELSE '' END AS readiness,
               heavy_user_rate || '% ' || adoption_color
                 || CASE WHEN gate_triggered THEN ' (gate: ' || minimum_use_rate || '% min use)' ELSE '' END AS adoption,
               improvement_pct || '% ' || outcomes_color               AS outcomes
        FROM scorecard ORDER BY sort_order""")

    print_table(con, "REACH: training detail", """
        SELECT department, eligible, loa_excluded, on_time, late, not_completed,
               on_time_rate, pct_registered_after_reminder
        FROM reach_by_department JOIN departments USING (department) ORDER BY sort_order""")

    print_table(con, "READINESS: percent favorable by survey wave (response rate)", """
        SELECT department,
               MAX(CASE WHEN wave_number = 1 THEN ROUND(pct_favorable_exact, 1) || '% (' || response_rate || '%)' END) AS wave_1,
               MAX(CASE WHEN wave_number = 2 THEN ROUND(pct_favorable_exact, 1) || '% (' || response_rate || '%)' END) AS wave_2,
               MAX(CASE WHEN wave_number = 3 THEN ROUND(pct_favorable_exact, 1) || '% (' || response_rate || '%)' END) AS wave_3
        FROM readiness_by_department_wave JOIN departments USING (department)
        GROUP BY department ORDER BY MIN(sort_order)""")

    print_table(con, "ADOPTION: ratings in the final 30 days", """
        SELECT department, eligible, not_using, meets, exceeds, heavy_user_rate, minimum_use_rate
        FROM adoption_by_department JOIN departments USING (department) ORDER BY sort_order""")

    print_table(con, "ADOPTION: share of workdays with use, before vs. after own training", """
        SELECT department,
               MAX(CASE WHEN period = 'Before training' THEN pct_workdays_active END) AS before_training,
               MAX(CASE WHEN period = 'After training'  THEN pct_workdays_active END) AS after_training
        FROM usage_by_training_period_department JOIN departments USING (department)
        GROUP BY department ORDER BY MIN(sort_order)""")

    print_table(con, "OUTCOMES: improvement vs. baseline, by period (volume-weighted)", """
        SELECT department,
               MAX(CASE WHEN period = 'Tool, before training' THEN improvement_vs_baseline_pct END) AS tool_before_training,
               MAX(CASE WHEN period = 'Tool, after training'  THEN improvement_vs_baseline_pct END) AS tool_after_training
        FROM outcomes_by_training_period JOIN departments USING (department)
        GROUP BY department ORDER BY MIN(sort_order)""")

    print_table(con, "OUTCOMES: improvement by final adoption rating (lines up with, not proof of, cause)", """
        SELECT department,
               MAX(CASE WHEN adoption_rating = 'Not using' THEN improvement_pct || '% (n=' || employees || ')' END) AS not_using,
               MAX(CASE WHEN adoption_rating = 'Meets'     THEN improvement_pct || '% (n=' || employees || ')' END) AS meets,
               MAX(CASE WHEN adoption_rating = 'Exceeds'   THEN improvement_pct || '% (n=' || employees || ')' END) AS exceeds
        FROM outcomes_by_adoption_rating JOIN departments USING (department)
        GROUP BY department ORDER BY MIN(sort_order)""")

    # 3. Export every view for hand-checking
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    views = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name")]
    for view in views:
        cur = con.execute(f"SELECT * FROM {view}")
        with open(METRICS_DIR / f"{view}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([d[0] for d in cur.description])
            writer.writerows(cur.fetchall())
    print(f"\nExported {len(views)} views to {METRICS_DIR.relative_to(ROOT)}/")
    con.close()


if __name__ == "__main__":
    main()
