"""
BUSINESS-RULE TESTS on the raw data.

Each rule is a SQL query that COUNTS VIOLATIONS. The test passes only if the
count is zero. These are the rules a real bank's data would have to follow.
"""

import pytest

from conftest import count

# (rule description, SQL that counts rows breaking the rule)
RULES = [
    # --- Employees ---------------------------------------------------------
    ("every employee is in exactly one known department",
     """SELECT COUNT(*) FROM employees
        WHERE department NOT IN (SELECT department FROM departments)"""),
    ("leave end date is never before leave start date",
     "SELECT COUNT(*) FROM employees WHERE loa_end_date < loa_start_date"),
    ("leave dates are both filled in or both blank",
     "SELECT COUNT(*) FROM employees WHERE (loa_start_date IS NULL) <> (loa_end_date IS NULL)"),

    # --- Emails ------------------------------------------------------------
    ("every employee gets every email exactly once",
     """SELECT COUNT(*) FROM (
            SELECT employee_id, email_type FROM communications
            GROUP BY employee_id, email_type HAVING COUNT(*) <> 1)"""),
    ("no email is opened before it was sent",
     "SELECT COUNT(*) FROM communications WHERE opened_date < sent_date"),
    ("no email is opened while on leave",
     """SELECT COUNT(*) FROM communications c JOIN employees e USING (employee_id)
        WHERE c.opened_date BETWEEN e.loa_start_date AND e.loa_end_date"""),

    # --- Training ------------------------------------------------------------
    ("nobody completes training without registering",
     "SELECT COUNT(*) FROM training WHERE completed_date IS NOT NULL AND registered_date IS NULL"),
    ("nobody completes training before registering",
     "SELECT COUNT(*) FROM training WHERE completed_date < registered_date"),
    ("nobody registers before opening the invitation or reminder (the only emails with the link)",
     """SELECT COUNT(*) FROM training t
        WHERE t.registered_date IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM communications c
              WHERE c.employee_id = t.employee_id
                AND c.email_type IN ('training_invitation', 'training_reminder')
                AND c.opened_date <= t.registered_date)"""),
    ("no training registration or completion while on leave",
     """SELECT COUNT(*) FROM training t JOIN employees e USING (employee_id)
        WHERE t.registered_date BETWEEN e.loa_start_date AND e.loa_end_date
           OR t.completed_date  BETWEEN e.loa_start_date AND e.loa_end_date"""),
    ("nobody registers before training is assigned",
     "SELECT COUNT(*) FROM training WHERE registered_date < assigned_date"),

    # --- Usage -----------------------------------------------------------------
    ("no usage before go-live",
     "SELECT COUNT(*) FROM usage CROSS JOIN settings s WHERE usage_date < s.go_live_date"),
    ("no usage on weekends",
     "SELECT COUNT(*) FROM usage u JOIN calendar c ON c.cal_date = u.usage_date WHERE c.is_workday = 0"),
    ("no usage while on leave",
     """SELECT COUNT(*) FROM usage u JOIN employees e USING (employee_id)
        WHERE u.usage_date BETWEEN e.loa_start_date AND e.loa_end_date"""),
    ("every usage row has at least 1 prompt",
     "SELECT COUNT(*) FROM usage WHERE prompts < 1"),
    ("at most one usage row per employee per day",
     """SELECT COUNT(*) FROM (SELECT employee_id, usage_date FROM usage
                               GROUP BY employee_id, usage_date HAVING COUNT(*) > 1)"""),
    ("no usage after the data ends",
     "SELECT COUNT(*) FROM usage CROSS JOIN settings s WHERE usage_date > s.data_end_date"),

    # --- Surveys -------------------------------------------------------------
    ("every survey score is between 1 and 7",
     "SELECT COUNT(*) FROM surveys WHERE score NOT BETWEEN 1 AND 7"),
    ("surveys are answered only in scheduled survey weeks",
     """SELECT COUNT(*) FROM surveys sv JOIN survey_schedule w USING (survey_week)
        WHERE sv.response_date NOT BETWEEN w.wave_start AND w.wave_end"""),
    ("no survey answered while on leave",
     """SELECT COUNT(*) FROM surveys sv JOIN employees e USING (employee_id)
        WHERE sv.response_date BETWEEN e.loa_start_date AND e.loa_end_date"""),
    ("each respondent answers each question at most once per wave",
     """SELECT COUNT(*) FROM (SELECT employee_id, survey_week, question_id FROM surveys
                               GROUP BY 1, 2, 3 HAVING COUNT(*) > 1)"""),
    ("comments come only from people who answered that wave",
     """SELECT COUNT(*) FROM survey_comments c
        WHERE NOT EXISTS (SELECT 1 FROM surveys s
                          WHERE s.employee_id = c.employee_id AND s.survey_week = c.survey_week)"""),

    # --- Outcomes ------------------------------------------------------------
    ("outcome values and volumes are positive",
     "SELECT COUNT(*) FROM outcomes WHERE outcome_value <= 0 OR volume < 1"),
    ("at most one outcome row per employee per week",
     """SELECT COUNT(*) FROM (SELECT employee_id, week FROM outcomes
                               GROUP BY employee_id, week HAVING COUNT(*) > 1)"""),
    ("quality scores never exceed 100",
     """SELECT COUNT(*) FROM outcomes o JOIN employees e USING (employee_id)
        JOIN departments d USING (department)
        WHERE d.outcome_unit LIKE 'points%' AND o.outcome_value > 100"""),
]


@pytest.mark.parametrize("rule, query", RULES, ids=[r[0] for r in RULES])
def test_business_rule(db, rule, query):
    violations = count(db, query)
    assert violations == 0, f"{violations} row(s) break the rule: {rule}"


def test_headcount_matches_settings(db, config):
    assert count(db, "SELECT COUNT(*) FROM employees") == config["population"]["total_employees"]
    for dept in config["departments"]:
        actual = count(db, f"SELECT COUNT(*) FROM employees WHERE department = '{dept['name']}'")
        assert actual == dept["headcount"], dept["name"]


def test_same_seed_gives_identical_data(pipeline_run):
    first, second = pipeline_run
    assert first == second, "Re-running the generator with the same seed changed the data"
