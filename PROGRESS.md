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
- [ ] `rollout_config.toml`: fictional company, AI tool name, timeline (baseline weeks + rollout weeks), departments, RAG thresholds
- Check: Audrey can read it and explain every setting

### Step 2: Synthetic data generator
- [ ] Employees and departments
- [ ] Communications and training records
- [ ] Survey responses (scores + open-ended comments)
- [ ] Weekly usage logs
- [ ] Outcome metrics before and after
- [ ] Planted "stories": each department gets a deliberate pattern (e.g., strong adopter; low training reach → low adoption; trained but negative sentiment; high usage but no outcome gain) so we can check that the scorecard finds them
- [ ] Fixed random seed, so numbers are identical every run
- Check: row counts, value ranges, totals make sense; spot-check a few employees by hand

### Step 3: Database + SQL metrics
- [ ] Load data into SQLite
- [ ] Write the four SQL files, one per measure, by department and by week
- [ ] Red/amber/green rules applied from the settings file
- Check: hand-calculate 2–3 metrics in a spreadsheet and compare; confirm planted stories show up

### Step 4: Validation tests
- [ ] pytest checks: no negative counts, rates between 0–100%, completions ≤ enrollments, every employee in exactly one department, etc.

### Step 5: Dashboard
- [ ] One-page HTML: scorecard grid (department × measure with RAG colors), adoption trend over time, before/after outcomes
- [ ] "Synthetic data" label visible on the page
- Check: open in browser, numbers match SQL results

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
- RAG thresholds: proposed defaults to be set in Step 1, then adjusted together

## Done
- 2026-11-21: Read project plan, proposed structure, created PROGRESS.md
- 2026-11-21: Installed Python 3.13.17 (winget, user scope)

- 2026-11-21: Plan decisions made; Git set up; folders created; first commit

## Next
- Step 1: write `rollout_config.toml` (bank, HAL, timeline, departments, proposed RAG thresholds)
