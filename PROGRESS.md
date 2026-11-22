# PROGRESS — Change & AI Adoption Readiness Scorecard

Last updated: 2026-11-21

**Status:** Planning. Plan proposed, waiting for Audrey's review. No code written yet.

**How to resume:** Open this folder in PowerShell and run `claude --continue`. Read this file first.

All data in this project is **synthetic (made up)**. No real employer data is used anywhere.

---

## The question this tool answers
"Did this change actually take hold, and where do we need to act?"

First scenario: a fictional company rolls out an AI assistant to its employees.
The framework is built so any rollout (process, system, tool, AI tool) can be swapped in by changing one settings file.

## Four measures
1. **Reach & engagement:** communications sent/opened, training attended/completed
2. **Readiness & sentiment:** survey scores, confidence, open-ended comments
3. **Adoption & behavior change:** active users over time, usage depth, errors before vs. after
4. **Outcomes:** business results before vs. after (e.g., handle time, error rate, quality score)

---

## Planned project layout
```
readiness-scorecard/
├── PROGRESS.md              ← this file
├── README.md                ← business problem, measures, how to run (written last)
├── rollout_config.toml      ← the rollout definition: name, dates, teams, RAG thresholds
├── requirements.txt         ← Python packages needed (kept minimal)
├── run_all.py               ← one command runs the whole pipeline
├── src/
│   ├── generate_data.py     ← builds the synthetic employees, training, surveys, usage, outcomes
│   ├── load_database.py     ← loads the data into a SQLite database
│   ├── calculate_metrics.py ← runs the SQL files, applies red/amber/green rules
│   ├── build_dashboard.py   ← writes the one-page HTML dashboard
│   └── write_summary.py     ← writes the plain-language findings summary
├── sql/                     ← one SQL file per measure, readable on their own
│   ├── 01_reach.sql
│   ├── 02_readiness.sql
│   ├── 03_adoption.sql
│   └── 04_outcomes.sql
├── tests/                   ← data-validation checks (row counts, ranges, no impossible values)
├── data/                    ← generated files (re-created by the generator, not hand-edited)
└── output/                  ← dashboard.html and findings_summary.md
```

## Tools
- **Python** (standard library + very few add-ons) for data generation and pipeline glue
- **SQLite** for the metric queries. Built into Python, no account or server, anyone who clones the repo can run it
- **HTML + Chart.js** for the dashboard. Opens in any browser, no server needed
- **pytest** for validation checks
- **Git + GitHub** for version control and a public link

---

## Build order (small steps, review and run each before moving on)

### Step 0: Setup
- [x] Install Python: 3.13.17 installed via winget (2026-11-21); SQLite 3.50.4 and tomllib confirmed built in
- [x] Confirmed `python --version` → 3.13.17 in a fresh window (needed a full app restart, not just a new tab)
- [x] Git for Windows installed (version 2.56.1 found)
- [x] Git identity set: Audrey Apelbaum <anomalychic@gmail.com>
- [x] `git init` (branch `main`), `.gitignore` added, first commit
- [x] Folder structure created (`src/`, `sql/`, `tests/`, `data/`, `output/`)
- [ ] `requirements.txt` (added in Step 4 when pytest is needed)

### Step 1: Rollout settings file
- [x] `rollout_config.toml` drafted (2026-11-21); parse check passed: dates line up, headcounts sum to 600
- [x] Revised from Audrey's review: training is mandatory (escalated to skip-levels), so Reach = on-time completion
      among eligible employees; LOA = TRUE during training window excluded from numerator and denominator
      and shown as a count; green ≥ 97%, amber ≥ 90%; Branch Operations pattern → "late_completers"
- [x] Adoption revised from Audrey's review: use appears on employee scorecards, so 1 prompt in a rolling
      30 days = "using" (meets); 5+ active days in rolling 30 days = "heavy use" (exceeds). Color = heavy-user
      rate; minimum-use gate (< 97% meeting minimum → red). Generator must produce DAILY usage.
- [x] Adoption numbers confirmed: heavy-user green ≥ 60%, amber ≥ 40%; minimum-use gate 97%
- [x] Readiness thresholds set by Audrey: percent favorable green ≥ 85%, amber ≥ 65%
- [x] Readiness revised from Audrey's review: surveys optional, 7-point scale, favorable = 6 or 7
- [x] Low-response caution: response rate < 50% of eligible employees (10-person minimum removed by Audrey)
- [x] Outcomes reviewed: metrics and thresholds (green ≥ 10%, amber ≥ 3%) approved; AHT changed to seconds (450)
- [x] Step 1 complete and committed
- Open: employees returning from LOA after the deadline. For now they are excluded from this rate;
  a separate later due date could be added later

### Step 2: Synthetic data generator
- [x] `src/generate_data.py` written (2026-11-21); writes 7 CSVs to `data/`:
      employees 600 · communications 2,400 · training 600 · surveys 4,296 answers ·
      survey_comments 324 · usage 9,719 active days · outcomes 11,884 employee-weeks
- [x] Added `volume_unit` / `weekly_volume` per department to `rollout_config.toml` (for volume-weighting)
- [x] Added a "scorecard floor": users send a quick prompt every 15–27 days, so box-checkers meet the minimum
- [x] Planted patterns verified with a rough check script (Claude's scratchpad, not the project):
      Contact Center GGGG · Branch Ops RARR (heavy-user rate amber, but 94.8% minimum use → gate makes it red;
      32% survey response → low-response caution) · Lending GRRR · Deposit Ops GGGR · Fraud & Disputes AAGA ·
      Risk & Compliance AAAA  (Reach / Readiness / Adoption / Outcomes)
- [x] 14 business-rule checks pass (e.g., nobody registered without opening a link email; no usage before go-live
      or while on LOA; scores 1–7). These become the Step 4 pytest tests.
- [x] Fixed seed confirmed: re-running gives byte-identical files
- [x] Generator run and spot-checked (E0182, Branch Ops: opened invitation, registered after reminder,
      completed 1 day late), then committed

### Step 3: Database + SQL metrics
- [x] `src/load_database.py`: builds `data/scorecard.db` (7 raw tables + departments, settings, calendar,
      survey_schedule). SQL reads every date/threshold from the one-row `settings` table. `test_pattern` is NOT loaded.
- [x] SQL files (each creates views): `01_reach.sql`, `02_readiness.sql`, `03_adoption.sql`, `04_outcomes.sql`,
      plus `05_scorecard.sql` joining the four headlines
- [x] Breakdowns by employee and department; before vs. after go-live AND before vs. after each employee's own
      training date (usage and outcomes); outcome change by adoption rating; rolling 30-day adoption trend
- [x] Red/amber/green rules + minimum-use gate + low-response caution applied in SQL from settings
- [x] `src/calculate_metrics.py`: runs the SQL, prints the scorecard, exports all 20 views to `output/metrics/*.csv`
- [x] SQL results match the independent Python check exactly; all 6 departments get their planned colors
- [x] Added `comparison_weeks = 4` to settings; `output/metrics/` added to .gitignore
- [x] Hand check 1 (Branch Ops on-time 90 ÷ 116 = 77.6%): Audrey got 94 incl. the 4 on leave → 90 after
      excluding them. Matches. Decision confirmed: LOA during the window is excluded even if they finished
      on time, because there's no full performance record for that period.
- [x] Committed (hand check 2, Lending heavy users 17 ÷ 89, skipped for now; can do anytime)

### Step 4: Validation tests
- [x] pytest 9.2.0 installed; `requirements.txt` and `pytest.ini` added
- [x] `tests/conftest.py`: rebuilds everything (generate → load → metrics) before tests run
- [x] `tests/test_data_rules.py`: 25 business rules as SQL violation counts + headcount + same-seed reproducibility
- [x] `tests/test_metrics.py`: rates 0–100, counts add up, LOA never eligible, colors follow thresholds and gate,
      low-response flag, 3 headline numbers recalculated independently in Python, planted patterns detected
- [x] All 55 tests pass (`python -m pytest`)
- [x] Generator now gives a plain message if a CSV is open in Excel (Windows file lock) instead of a crash
- [x] Audrey ran the tests herself: 55 passed
- [x] Break-it test: Audrey changed reach green 97 → 99; `test_scorecard_detects_planted_patterns` failed on
      Deposit Operations (98.9% → Amber) while `test_colors_follow_thresholds` still passed (logic correct,
      expected result changed). Reverted; 55 pass again. Committed.

### Step 5: Dashboard
- Decisions (Audrey): audience = portfolio/recruiter (project story first, then scorecard); department charts +
  filterable employee table; RAG cells show tint + value + icon + word (readable without color)
- [x] `src/build_dashboard.py` + `src/dashboard_template.html` → `output/dashboard.html` (single file, Chart.js 4.4.1 via CDN)
- [x] Sections: about (problem, bank-practice rules, how built) → scorecard → training effect (usage + outcomes
      before/after own training) → outcome by adoption rating (with causation caveat) → department detail cards
      (heavy-user trend, % favorable by survey, active-days distribution, weekly outcome with go-live line)
      → methods (from settings) → employee table (filter/sort, 600 rows) → synthetic-data footer
- [x] Light + dark mode, "Show as table" for each main chart, sticky department column on narrow screens
- [x] Rendered and checked with headless Edge; fixed card overflow and skipped axis labels
- [x] `run_all.py` runs the whole pipeline; 4 dashboard tests added (59 total, all pass)
- [x] Audrey's review: too much red → outcome thresholds lowered to green ≥ 7.5%, amber ≥ 2.5% (were 10 / 3).
      Fraud & Disputes and Risk & Compliance outcomes → Green; Branch Ops outcomes → Amber. Red cells 7 → 6.
      Planted-pattern test expectations updated to match. 59 tests pass.
- Note: Branch Ops outcome is 2.51%, just 0.01 above the amber line. Any change to the generator could flip it.
- [x] Committed (Branch Ops borderline left as is)

### Step 6: Findings summary
- [ ] Rule-based write-up: where it's working, where it isn't, recommended next action per department
- Check: every statement traces back to a number on the dashboard

### Step 7: README + GitHub
- [ ] README: business problem, the four measures and how each is calculated, how to run, synthetic-data notice
- [ ] Push to GitHub (walk through Git basics along the way)

### Stretch (only if time allows)
- [ ] AI theme sorting for open-ended comments, with a human-reviewed validation sample
- [ ] Second scenario (process change) to prove the framework is reusable

---

## Decisions (2026-11-21)
- **Company:** Monolith National Bank (fictional)
- **AI tool:** "AI Assistant HAL"
- **Size:** ~600 employees, 6 departments, 8 baseline weeks + 12 rollout weeks
- **Database:** SQLite
- **Departments:** Contact Center, Branch Operations, Lending, Deposit Operations, Fraud & Disputes, Risk & Compliance

## Still open
- Employees returning from LOA after the training deadline (currently excluded; see Step 1)

## Step 2 design rules (from Audrey's review)
- Training registration link is in the invitation (week 6) and the reminder (week 8): nobody can register
  without opening one of them. Training table records assigned → registered → completed; registered date must
  be on/after the earliest open of either email.
  Validation test: zero employees registered or completed without an opened invitation or reminder.
- Usage is a continuous spread, not two clusters. Active days (rolling 30) sets the rating; prompts per active day
  is detail only. Three ratings: Not using (0), Meets (1–4), Exceeds (5+). (An in-between rating was
  considered and dropped by Audrey.)
  Department color still = Exceeds share + 97% minimum-use gate. Dashboard gets an active-days distribution chart.
- Outcomes recorded per employee per week with work volume; department values are volume-weighted.
  Breakdowns by employee and by department, incl. outcome change by adoption rating.
- Before/after comparisons two ways: (1) before vs. after go-live (department baseline), and (2) before vs. after
  EACH EMPLOYEE'S OWN training completion date, rolled up by department.
- HAL access is NOT gated by training, and HAL goes live BEFORE anyone trains. Schedule revised:
  go-live + announcement wk 9 (2026-03-02) → invitation wk 10 → training wks 10–13 → reminder wk 12 →
  deadline end of wk 13 (2026-04-05) → tips email wk 15. Surveys stay wks 8, 14, 20.
  Every employee has untrained usage first, so usage and outcomes get compared before vs. after each
  employee's own training date.
- Interview caveat: scorecard shows where the reach → readiness → adoption → outcomes chain breaks; it is
  monitoring, not a controlled experiment, so links line up but don't prove cause.

## Done
- 2026-11-21: Read project plan, proposed structure, created PROGRESS.md
- 2026-11-21: Installed Python 3.13.17 (winget, user scope)

- 2026-11-21: Plan decisions made; Git set up; folders created; first commit
- 2026-11-21: Step 1 done: `rollout_config.toml` reviewed and revised to match real bank practice
- 2026-11-21: Step 2 done: synthetic data generator written, verified and committed
- 2026-11-21: Step 3 done: SQLite database + SQL metric views; scorecard matches planned colors; hand check passed
- 2026-11-21: Step 4 done: 55 pytest tests; Audrey ran them and confirmed they catch a deliberate threshold change
- 2026-11-21: Step 5 done: HTML dashboard + run_all.py; outcome thresholds lowered to 7.5 / 2.5; 59 tests pass

## Next
- Step 6: findings summary (and add it to the dashboard)
