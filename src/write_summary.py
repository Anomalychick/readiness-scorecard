"""
write_summary.py: writes the plain-language findings summary.

For each department, checks the metric views for a fixed list of problems
(see PROBLEMS below). Every problem it finds becomes a sentence quoting the
numbers behind it, plus the recommended actions from the [playbook] section
of rollout_config.toml. No AI is involved: the same data always gives the
same summary, and every sentence traces back to a number on the dashboard.

Writes output/findings_summary.md. The dashboard also shows these findings
(build_dashboard.py calls build_findings below).

Run from the project folder (after calculate_metrics.py):
    python src/write_summary.py
"""

import sqlite3
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "scorecard.db"
OUTPUT = ROOT / "output" / "findings_summary.md"

MEASURES = [("reach_color", "Reach"), ("readiness_color", "Readiness"),
            ("adoption_color", "Adoption"), ("outcomes_color", "Outcomes")]
ICON = {"Green": "✓", "Amber": "!", "Red": "✕"}


def one(con, query, *params):
    cur = con.execute(query, params)
    row = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], row)) if row else {}


def pct(v):
    return f"{v:.1f}%"


def signed(v):
    return f"{'+' if v > 0 else ''}{v:.1f}%"


def change_words(v):
    """Improvement % in plain words: positive always means better."""
    if abs(v) < 0.05:
        return "didn't change"
    return f"improved {v:.1f}%" if v > 0 else f"got {abs(v):.1f}% worse"


def build_findings(con, cfg):
    """Returns one dict per department: status, colors, strengths, problems, actions."""
    th, playbook = cfg["thresholds"], cfg["playbook"]
    gate = th["adoption"]["minimum_use_gate"]
    results = []

    for dept in [r[0] for r in con.execute("SELECT department FROM departments ORDER BY sort_order")]:
        sc = one(con, "SELECT * FROM scorecard WHERE department = ?", dept)
        reach = one(con, "SELECT * FROM reach_by_department WHERE department = ?", dept)
        ready = one(con, "SELECT * FROM readiness_by_department WHERE department = ?", dept)
        adopt = one(con, "SELECT * FROM adoption_by_department WHERE department = ?", dept)
        outc = one(con, "SELECT * FROM outcomes_by_department WHERE department = ?", dept)
        weakest_q = one(con, """
            SELECT question_text, pct_favorable FROM readiness_by_question
            WHERE department = ? AND survey_week = (SELECT MAX(survey_week) FROM survey_schedule)
            ORDER BY pct_favorable LIMIT 1""", dept)
        heavy_out = one(con, """SELECT improvement_pct FROM outcomes_by_adoption_rating
                                WHERE department = ? AND adoption_rating = 'Exceeds'""", dept)
        usage = {r[0]: r[1] for r in con.execute(
            "SELECT period, pct_workdays_active FROM usage_by_training_period_department WHERE department = ?", (dept,))}

        colors = {label: sc[key] for key, label in MEASURES}
        problems, actions, strengths = [], [], []

        def add(problem_key, sentence):
            problems.append(sentence)
            for action in playbook[problem_key]:
                if action not in actions:
                    actions.append(action)

        # --- Problems (each rule reads only metric values, never the planted pattern) ---
        if sc["reach_color"] != "Green":
            add("late_training",
                f"Training ran late: {pct(reach['on_time_rate'])} finished on time "
                f"({reach['late']} of {reach['eligible']} eligible employees finished after the deadline). "
                f"{pct(reach['pct_registered_after_reminder'])} registered only after the reminder email.")

        if ready["caution"]:
            add("low_response",
                f"Only {pct(ready['response_rate'])} answered the latest survey, so its "
                f"{pct(ready['pct_favorable'])} favorable score may not represent the department.")

        falling = ready["change_since_first_wave"] <= -5
        if sc["readiness_color"] == "Red" or falling:
            trend = (f", down {abs(ready['change_since_first_wave']):.1f} points since the first survey"
                     if falling else "")
            add("low_confidence",
                f"Confidence is low: {pct(ready['pct_favorable'])} favorable{trend}. "
                f"Weakest item: \"{weakest_q['question_text']}\" ({pct(weakest_q['pct_favorable'])} favorable).")

        if adopt["gate_triggered"]:
            add("below_minimum",
                f"{adopt['not_using']} employees used the tool on zero days in the last 30, so only "
                f"{pct(adopt['minimum_use_rate'])} met the minimum (needs {gate:.0f}%). "
                f"That turns adoption red even though {pct(adopt['heavy_user_rate'])} are heavy users.")
        elif adopt["heavy_user_rate"] < th["adoption"]["amber"]:
            add("low_confidence",
                f"Box-checking: {pct(adopt['minimum_use_rate'])} meet the one-prompt minimum, but only "
                f"{pct(adopt['heavy_user_rate'])} are heavy users ({adopt['meets']} of {adopt['eligible']} "
                f"use it just 1-{th['adoption']['heavy_use_active_days'] - 1} days a month).")

        if sc["adoption_color"] == "Green" and sc["outcomes_color"] == "Red":
            heavy_note = (f" Even among heavy users it {change_words(heavy_out['improvement_pct'])}."
                          if heavy_out else "")
            add("use_without_results",
                f"Use isn't turning into results: {pct(adopt['heavy_user_rate'])} are heavy users, but "
                f"{outc['outcome_metric'].lower()} {change_words(outc['improvement_pct'])} vs. baseline.{heavy_note}")
        elif sc["outcomes_color"] == "Red":
            problems.append(
                f"{outc['outcome_metric']} has barely moved: it {change_words(outc['improvement_pct'])} vs. baseline. "
                f"This follows from the problems above.")

        # --- Watch notes: amber measures not already explained above ------------------
        watch = []
        if sc["readiness_color"] == "Amber" and not ready["caution"] and not falling:
            watch.append(f"Readiness is amber at {pct(ready['pct_favorable'])} favorable "
                         f"(green is {th['readiness']['green']:.0f}%).")
        if sc["adoption_color"] == "Amber":
            watch.append(f"Adoption is amber: {pct(adopt['heavy_user_rate'])} are heavy users "
                         f"(green is {th['adoption']['green']:.0f}%).")
        if sc["outcomes_color"] == "Amber":
            watch.append(f"{outc['outcome_metric']} {change_words(outc['improvement_pct'])} vs. baseline: "
                         f"amber (green is {th['outcomes']['green']:g}%).")

        # --- Strengths ----------------------------------------------------------------
        if sc["reach_color"] == "Green":
            strengths.append(f"Training landed on time ({pct(reach['on_time_rate'])}).")
        if sc["readiness_color"] == "Green":
            strengths.append(f"People feel ready: {pct(ready['pct_favorable'])} favorable.")
        if sc["adoption_color"] == "Green":
            strengths.append(f"Real use: {pct(adopt['heavy_user_rate'])} are heavy users.")
        if sc["outcomes_color"] == "Green":
            strengths.append(f"{outc['outcome_metric']} {change_words(outc['improvement_pct'])} vs. baseline.")
        before, after = usage.get("Before training"), usage.get("After training")
        if before and after and after >= 1.5 * before:
            strengths.append(f"Training paid off: use rose from {pct(before)} to {pct(after)} of workdays "
                             f"after people were trained.")

        reds = sum(c == "Red" for c in colors.values())
        greens = sum(c == "Green" for c in colors.values())
        if reds == 0 and greens == 4:
            status = "On track"
            actions = list(playbook["on_track"])
        elif reds == 0:
            status = "Watch"
        else:
            status = "Needs action"

        results.append(dict(department=dept, status=status, colors=colors,
                            strengths=strengths, problems=problems, watch=watch, actions=actions))
    return results


def overview(con, findings):
    """Organization-wide sentences for the top of the summary."""
    counts = {s: sum(f["status"] == s for f in findings) for s in ("On track", "Watch", "Needs action")}
    lines = [f"{counts['On track']} of {len(findings)} departments {'is' if counts['On track'] == 1 else 'are'} "
             f"on track, {counts['Watch']} to watch, and {counts['Needs action']} "
             f"{'needs' if counts['Needs action'] == 1 else 'need'} action."]
    before, after = con.execute("""
        SELECT 100.0 * SUM(CASE WHEN period = 'Before training' THEN active_days END)
                     / SUM(CASE WHEN period = 'Before training' THEN workdays_available END),
               100.0 * SUM(CASE WHEN period = 'After training' THEN active_days END)
                     / SUM(CASE WHEN period = 'After training' THEN workdays_available END)
        FROM usage_by_training_period_department""").fetchone()
    lines.append(f"Training is where behavior changed: across the bank, employees used the tool on "
                 f"{pct(before)} of workdays before their own training and {pct(after)} after.")
    breaks = [f for f in findings if f["status"] == "Needs action"]
    if breaks:
        lines.append("Where the chain from training to results breaks: " + "; ".join(
            f"{f['department']} at {', '.join(m.lower() for m, c in f['colors'].items() if c == 'Red')}"
            for f in breaks) + ".")
    return lines


def to_markdown(settings, findings, intro):
    out = [f"# Findings: {settings['change_name']} rollout at {settings['organization']}",
           "",
           f"**SYNTHETIC DATA.** All people, numbers and the bank are made up. "
           f"Data runs {settings['first_week_start']} to {settings['data_end_date']}; "
           f"go-live {settings['go_live_date']}.",
           "",
           "## Summary", ""]
    out += [f"- {line}" for line in intro]
    out += ["", "## By department", ""]
    for f in findings:
        chips = " ".join(f"{m} {ICON[c]} {c}" for m, c in f["colors"].items())
        out += [f"### {f['department']}: {f['status']}", "", chips, ""]
        if f["strengths"]:
            out += ["**What's working**", ""] + [f"- {s}" for s in f["strengths"]] + [""]
        if f["problems"]:
            out += ["**What isn't**", ""] + [f"- {p}" for p in f["problems"]] + [""]
        if f["watch"]:
            out += ["**Watch**", ""] + [f"- {w}" for w in f["watch"]] + [""]
        if f["actions"]:
            out += ["**Recommended next actions**", ""] + [f"- {a}" for a in f["actions"]] + [""]
    out += ["## How this summary is written", "",
            "Each sentence comes from a fixed rule applied to the scorecard data (for example: if on-time "
            "training is below green, report it and recommend the late-training actions). Recommended "
            "actions come from the playbook in the settings file. The rules never see how the synthetic "
            "data was generated; they read only the calculated metrics.", ""]
    return "\n".join(out)


def main():
    if not DB_PATH.exists():
        raise SystemExit("No database found. Run load_database.py and calculate_metrics.py first.")
    with open(ROOT / "rollout_config.toml", "rb") as f:
        cfg = tomllib.load(f)
    con = sqlite3.connect(DB_PATH)
    settings = one(con, "SELECT * FROM settings")
    findings = build_findings(con, cfg)
    md = to_markdown(settings, findings, overview(con, findings))
    con.close()
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    for f in findings:
        print(f"  {f['department']:<20} {f['status']:<13} {len(f['problems'])} problem(s), {len(f['actions'])} action(s)")


if __name__ == "__main__":
    main()
