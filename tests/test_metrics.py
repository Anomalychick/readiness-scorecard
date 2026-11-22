"""
METRIC TESTS: do the SQL calculations make sense?

  1. Sanity checks: rates between 0 and 100, counts that add up,
     LOA employees never counted as eligible.
  2. Color rules: every color follows the thresholds in settings,
     including the minimum-use gate.
  3. Independent recalculation: a few headline numbers are recomputed
     in plain Python straight from the CSVs and must match the SQL.
  4. Planted patterns: each department gets the colors its synthetic
     pattern was built to produce. (This one is specific to the made-up data.)
"""

import csv
from datetime import date

import pytest

from conftest import DATA_DIR, count

# --- 1. Sanity checks --------------------------------------------------------
RATE_COLUMNS = [
    ("reach_by_department", "on_time_rate"),
    ("reach_by_department", "completed_by_data_end_rate"),
    ("reach_by_department", "pct_registered_after_reminder"),
    ("email_opens_by_department", "open_rate"),
    ("readiness_by_department_wave", "response_rate"),
    ("readiness_by_department_wave", "pct_favorable_exact"),
    ("readiness_by_question", "pct_favorable"),
    ("adoption_by_department", "heavy_user_rate"),
    ("adoption_by_department", "minimum_use_rate"),
    ("adoption_trend", "heavy_user_rate"),
    ("adoption_trend", "minimum_use_rate"),
    ("usage_by_training_period", "pct_workdays_active"),
]


@pytest.mark.parametrize("view, column", RATE_COLUMNS, ids=[f"{v}.{c}" for v, c in RATE_COLUMNS])
def test_rates_between_0_and_100(db, view, column):
    bad = count(db, f"SELECT COUNT(*) FROM {view} WHERE {column} < 0 OR {column} > 100")
    assert bad == 0


COUNT_CHECKS = [
    ("SELECT COUNT(*) FROM reach_by_department WHERE eligible + loa_excluded <> employees",
     "reach: eligible + LOA excluded = all employees"),
    ("SELECT COUNT(*) FROM reach_by_department WHERE on_time + late + not_completed <> eligible",
     "reach: on time + late + not completed = eligible"),
    ("SELECT COUNT(*) FROM adoption_by_department WHERE eligible + loa_excluded <> employees",
     "adoption: eligible + LOA excluded = all employees"),
    ("SELECT COUNT(*) FROM adoption_by_department WHERE not_using + meets + exceeds <> eligible",
     "adoption: not using + meets + exceeds = eligible"),
    ("SELECT COUNT(*) FROM readiness_by_department_wave WHERE respondents > eligible",
     "readiness: respondents never exceed eligible"),
    ("SELECT COUNT(*) FROM readiness_by_department_wave WHERE favorable_answers > answers",
     "readiness: favorable answers never exceed answers"),
    ("SELECT COUNT(*) FROM email_opens_by_department WHERE opened > sent",
     "emails: opened never exceeds sent"),
]


@pytest.mark.parametrize("query, meaning", COUNT_CHECKS, ids=[m for _, m in COUNT_CHECKS])
def test_counts_add_up(db, query, meaning):
    assert count(db, query) == 0, meaning


def test_loa_employees_never_eligible_for_training(db):
    # Anyone whose leave overlaps the training window must be flagged as excluded.
    missed = count(db, """
        SELECT COUNT(*) FROM reach_by_employee r JOIN employees e USING (employee_id)
        CROSS JOIN settings s
        WHERE e.loa_start_date <= s.training_deadline_date
          AND e.loa_end_date   >= s.training_start_date
          AND r.loa_in_training_window = 0""")
    assert missed == 0


def test_scorecard_has_every_department_once(db, config):
    names = [r[0] for r in db.execute("SELECT department FROM scorecard")]
    assert sorted(names) == sorted(d["name"] for d in config["departments"])


# --- 2. Color rules ----------------------------------------------------------
def expected_color(value, green, amber):
    return "Green" if value >= green else "Amber" if value >= amber else "Red"


def test_colors_follow_thresholds(db, config):
    th = config["thresholds"]
    rows = db.execute("""
        SELECT r.department,
               100.0 * r.on_time / r.eligible, r.reach_color,
               w.pct_favorable_exact, rd.readiness_color,
               100.0 * a.exceeds / a.eligible, 100.0 * (a.meets + a.exceeds) / a.eligible, a.adoption_color,
               o.improvement_pct, o.outcomes_color
        FROM reach_by_department r
        JOIN readiness_by_department rd USING (department)
        JOIN readiness_by_department_wave w
             ON w.department = r.department AND w.survey_week = rd.latest_survey_week
        JOIN adoption_by_department a USING (department)
        JOIN outcomes_by_department o USING (department)""").fetchall()
    for dept, reach, reach_c, fav, ready_c, heavy, min_use, adopt_c, outc, outc_c in rows:
        assert reach_c == expected_color(reach, th["reach"]["green"], th["reach"]["amber"]), dept
        assert ready_c == expected_color(fav, th["readiness"]["green"], th["readiness"]["amber"]), dept
        if min_use < th["adoption"]["minimum_use_gate"]:
            assert adopt_c == "Red", f"{dept}: minimum-use gate should force Red"
        else:
            assert adopt_c == expected_color(heavy, th["adoption"]["green"], th["adoption"]["amber"]), dept
        # improvement_pct is rounded to 1 decimal in the view; skip exact-boundary cases
        if round(outc, 1) not in (th["outcomes"]["green"], th["outcomes"]["amber"]):
            assert outc_c == expected_color(outc, th["outcomes"]["green"], th["outcomes"]["amber"]), dept


def test_low_response_caution_matches_rule(db, config):
    limit = config["thresholds"]["readiness"]["low_response_rate"]
    for dept, rate, caution in db.execute(
            "SELECT department, response_rate, caution FROM readiness_by_department"):
        assert (caution is not None) == (rate < limit), dept


# --- 3. Independent recalculation in plain Python --------------------------------
def read_csv(name):
    with open(DATA_DIR / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def overlaps(emp, first, last):
    return bool(emp["loa_start_date"]) and emp["loa_start_date"] <= last and emp["loa_end_date"] >= first


def test_on_time_rate_recalculated_in_python(db):
    s = dict(zip(*[[d[0] for d in db.execute("SELECT * FROM settings").description],
                   db.execute("SELECT * FROM settings").fetchone()]))
    employees = {e["employee_id"]: e for e in read_csv("employees.csv")}
    tally = {}
    for t in read_csv("training.csv"):
        emp = employees[t["employee_id"]]
        if overlaps(emp, s["training_start_date"], s["training_deadline_date"]):
            continue
        on_time, eligible = tally.get(emp["department"], (0, 0))
        on_time += bool(t["completed_date"]) and t["completed_date"] <= s["training_deadline_date"]
        tally[emp["department"]] = (on_time, eligible + 1)
    for dept, sql_rate in db.execute("SELECT department, on_time_rate FROM reach_by_department"):
        on_time, eligible = tally[dept]
        assert round(100 * on_time / eligible, 1) == sql_rate, dept


def test_heavy_user_rate_recalculated_in_python(db, config):
    window_start, window_end = db.execute(
        "SELECT adoption_window_start, data_end_date FROM settings").fetchone()
    heavy_days = config["thresholds"]["adoption"]["heavy_use_active_days"]
    employees = {e["employee_id"]: e for e in read_csv("employees.csv")}
    active = {}
    for u in read_csv("usage.csv"):
        if window_start <= u["usage_date"] <= window_end:
            active[u["employee_id"]] = active.get(u["employee_id"], 0) + 1
    tally = {}
    for eid, emp in employees.items():
        if overlaps(emp, window_start, window_end):
            continue
        heavy, eligible = tally.get(emp["department"], (0, 0))
        tally[emp["department"]] = (heavy + (active.get(eid, 0) >= heavy_days), eligible + 1)
    for dept, sql_rate in db.execute("SELECT department, heavy_user_rate FROM adoption_by_department"):
        heavy, eligible = tally[dept]
        assert round(100 * heavy / eligible, 1) == sql_rate, dept


def test_outcome_improvement_recalculated_in_python(db, config):
    baseline_weeks = config["rollout"]["baseline_weeks"]
    total_weeks = baseline_weeks + config["rollout"]["rollout_weeks"]
    recent_from = total_weeks - config["thresholds"]["outcomes"]["comparison_weeks"] + 1
    dept_of = {e["employee_id"]: e["department"] for e in read_csv("employees.csv")}
    better = {d["name"]: d["better_when"] for d in config["departments"]}
    sums = {}
    for o in read_csv("outcomes.csv"):
        week, value, volume = int(o["week"]), float(o["outcome_value"]), int(o["volume"])
        period = "base" if week <= baseline_weeks else "recent" if week >= recent_from else None
        if period:
            key = (dept_of[o["employee_id"]], period)
            vsum, wsum = sums.get(key, (0.0, 0))
            sums[key] = (vsum + value * volume, wsum + volume)
    for dept, sql_pct in db.execute("SELECT department, improvement_pct FROM outcomes_by_department"):
        base = sums[(dept, "base")][0] / sums[(dept, "base")][1]
        recent = sums[(dept, "recent")][0] / sums[(dept, "recent")][1]
        change = (base - recent) if better[dept] == "lower" else (recent - base)
        assert round(100 * change / base, 1) == sql_pct, dept


# --- 4. Planted patterns (synthetic data only) ----------------------------------
# Expected colors (Reach, Readiness, Adoption, Outcomes) for each planted pattern.
PLANTED = {
    "strong_adopter":         ("Green", "Green", "Green", "Green"),
    "late_completers":        ("Red",   "Amber", "Red",   "Amber"),
    "trained_but_skeptical":  ("Green", "Red",   "Red",   "Red"),
    "usage_without_outcomes": ("Green", "Green", "Green", "Red"),
    "slow_start_recovering":  ("Amber", "Amber", "Green", "Green"),
    "middle_of_the_road":     ("Amber", "Amber", "Amber", "Green"),
}


def test_scorecard_detects_planted_patterns(db, config):
    actual = {row[0]: row[1:] for row in db.execute(
        "SELECT department, reach_color, readiness_color, adoption_color, outcomes_color FROM scorecard")}
    for dept in config["departments"]:
        assert actual[dept["name"]] == PLANTED[dept["test_pattern"]], dept["name"]


def test_branch_gate_and_caution_traps(db):
    # Branch Operations' heavy-user rate alone is Amber; the 97% gate must turn it Red,
    # and its low survey response must trigger the caution flag.
    heavy, gate, color = db.execute("""
        SELECT a.heavy_user_rate, a.gate_triggered, a.adoption_color
        FROM adoption_by_department a WHERE department = 'Branch Operations'""").fetchone()
    assert 40 <= heavy < 60 and gate == 1 and color == "Red"
    caution = db.execute(
        "SELECT caution FROM readiness_by_department WHERE department = 'Branch Operations'").fetchone()[0]
    assert caution is not None
