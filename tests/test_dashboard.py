"""
DASHBOARD TESTS: the HTML file is built, complete and honest.
"""

import json
import re

from conftest import ROOT

DASHBOARD = ROOT / "output" / "dashboard.html"


def dashboard_data(html):
    match = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert match, "Data block not found in dashboard"
    return json.loads(match.group(1))


def test_dashboard_is_built(pipeline_run):
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "__DASHBOARD_DATA__" not in html, "Data placeholder was never filled in"


def test_dashboard_says_synthetic(pipeline_run):
    html = DASHBOARD.read_text(encoding="utf-8").lower()
    assert html.count("synthetic") >= 2, "The synthetic-data label must appear in the header and footer"


def test_dashboard_numbers_match_database(pipeline_run, db):
    data = dashboard_data(DASHBOARD.read_text(encoding="utf-8"))
    from_db = db.execute("""SELECT department, on_time_rate, pct_favorable, heavy_user_rate, improvement_pct,
                                   reach_color, readiness_color, adoption_color, outcomes_color
                            FROM scorecard ORDER BY sort_order""").fetchall()
    on_page = [(s["department"], s["on_time_rate"], s["pct_favorable"], s["heavy_user_rate"], s["improvement_pct"],
                s["reach_color"], s["readiness_color"], s["adoption_color"], s["outcomes_color"])
               for s in data["scorecard"]]
    assert on_page == from_db


def test_dashboard_lists_every_employee(pipeline_run, config):
    data = dashboard_data(DASHBOARD.read_text(encoding="utf-8"))
    assert len(data["employees"]) == config["population"]["total_employees"]
