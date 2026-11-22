"""
generate_data.py: builds the SYNTHETIC (made-up) data for the scorecard.

Reads rollout_config.toml and writes seven CSV files to data/:
    employees.csv        one row per employee (department, leave of absence dates)
    communications.csv   one row per email per employee (sent, opened)
    training.csv         one row per employee (assigned, registered, completed)
    surveys.csv          one row per survey answer (1-7 score)
    survey_comments.csv  one row per optional open-ended comment
    usage.csv            one row per employee per day they used the tool
    outcomes.csv         one row per employee per week worked (outcome + volume)

These files hold only RAW FACTS, the kind a real system would record.
Anything worked out from them ("on time", "late", "heavy user", "favorable")
is calculated later, in SQL, so every metric is visible and explainable.

Each department follows a planted pattern (see PATTERNS below) so we can check
that the scorecard detects it without being told. The same random seed gives
identical data on every run.

Run from the project folder:   python src/generate_data.py
"""

import csv
import math
import random
import tomllib
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "rollout_config.toml"
DATA_DIR = ROOT / "data"


# ---------------------------------------------------------------------------
# PLANTED PATTERNS
# Each department's test_pattern (in the settings file) picks one of these.
# Values are chances (0-1) or multipliers. Results land NEAR these targets,
# not exactly on them, because of random variation.
# ---------------------------------------------------------------------------
PATTERNS = {
    "strong_adopter": dict(
        email_open=0.90,             # chance of opening each non-training email
        on_time=0.995, late=0.005,   # training: share on time, share late (rest never)
        survey_response=0.70,        # chance of answering each optional survey
        favorable=(0.72, 0.88, 0.92),  # chance an answer is 6-7, per survey wave
        question_shift={},           # extra favorability for specific questions
        non_user=0.003,              # share who never touch the tool
        usage_level=0.45,            # typical share of workdays used, once trained
        untrained_factor=0.35,       # usage before training, vs. after (0-1)
        ramp_days=10,                # days after training to reach full usage
        outcome_gain=0.40,           # improvement for someone using it every workday
    ),
    "late_completers": dict(
        email_open=0.80,
        on_time=0.80, late=0.18,     # many finish only after the deadline
        survey_response=0.35,        # short-staffed: little time for surveys
        favorable=(0.66, 0.66, 0.74),
        question_shift={"prepared": -0.08},
        non_user=0.08,               # enough non-users to fail the 97% minimum-use gate
        usage_level=0.24,
        untrained_factor=0.30,
        ramp_days=14,
        outcome_gain=0.04,
    ),
    "trained_but_skeptical": dict(
        email_open=0.85,
        on_time=0.995, late=0.005,
        survey_response=0.65,
        favorable=(0.62, 0.52, 0.47),  # confidence drops as people try it
        question_shift={"accuracy": -0.15},
        non_user=0.004,
        usage_level=0.12,            # log in to meet the scorecard, little real use
        untrained_factor=0.60,
        ramp_days=10,
        outcome_gain=0.10,
    ),
    "usage_without_outcomes": dict(
        email_open=0.88,
        on_time=0.995, late=0.005,
        survey_response=0.68,
        favorable=(0.74, 0.88, 0.91),
        question_shift={},
        non_user=0.004,
        usage_level=0.45,
        untrained_factor=0.35,
        ramp_days=10,
        outcome_gain=0.0,            # heavy use, but the result doesn't move
    ),
    "slow_start_recovering": dict(
        email_open=0.82,
        on_time=0.94, late=0.05,
        survey_response=0.60,
        favorable=(0.68, 0.55, 0.80),  # dips mid-rollout, then recovers
        question_shift={},
        non_user=0.01,
        usage_level=0.27,
        untrained_factor=0.15,       # barely used before training
        ramp_days=35,                # slow climb after training
        outcome_gain=0.22,
    ),
    "middle_of_the_road": dict(
        email_open=0.84,
        on_time=0.955, late=0.04,
        survey_response=0.62,
        favorable=(0.70, 0.73, 0.76),
        question_shift={},
        non_user=0.01,
        usage_level=0.22,
        untrained_factor=0.40,
        ramp_days=14,
        outcome_gain=0.30,
    ),
}

SURVEY_QUESTIONS = {
    "prepared":        "I feel prepared to use {tool} in my work.",
    "accuracy":        "I am confident {tool}'s output is accurate.",
    "helps_job":       "{tool} helps me do my job.",
    "manager_support": "My manager supports my use of {tool}.",
}

FLOOR_GAP_DAYS = (15, 27)        # scorecard floor: users send at least one prompt
                                 # every 15-27 days, so they never show as "not using"
LOA_SHARE = 0.04                 # share of employees with one leave of absence
LOA_DAYS = (14, 84)              # leave length: 2 to 12 weeks
COMMENT_CHANCE = 0.30            # chance a survey respondent leaves a comment

# Open-ended comments: (theme, positive version, negative version).
COMMENT_BANK = [
    ("time_savings", "It saves me real time on routine write-ups.",
                     "I haven't seen it save me any time yet."),
    ("time_savings", "Drafting summaries is much faster now.",
                     "Checking its work takes as long as doing it myself."),
    ("accuracy_trust", "The answers have been accurate for what I use it for.",
                       "I don't trust the output enough to use it on real customer work."),
    ("accuracy_trust", "It gets the facts right more often than I expected.",
                       "It made up a policy detail once, so now I double-check everything."),
    ("training", "The training gave me practical examples I use every day.",
                 "The training was too general for my actual job."),
    ("training", "Training was well organized and easy to fit in.",
                 "I couldn't get off the floor to attend training on time."),
    ("workload", "Once I learned it, it made my day lighter.",
                 "We're short-staffed, so there's no time to learn something new."),
    ("manager_support", "My manager shares tips and encourages us to try it.",
                        "My manager never talks about it, so it doesn't feel like a priority."),
    ("use_cases", "I'd like more examples for my specific tasks, but it's useful.",
                  "I'm not sure what I'm supposed to use it for in my role."),
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def is_workday(day):
    """Day 0 is a Monday, so days 0-4 of each week are Monday-Friday."""
    return day % 7 < 5


def on_leave(emp, day):
    return emp["loa_start"] is not None and emp["loa_start"] <= day <= emp["loa_end"]


def pick_workday(emp, first, last):
    """A random workday in [first, last] when the employee is not on leave,
    or None if there isn't one."""
    days = [d for d in range(first, last + 1) if is_workday(d) and not on_leave(emp, d)]
    return random.choice(days) if days else None


def first_workday_from(emp, day, last_day):
    """The first workday on or after `day` when the employee is not on leave."""
    while day <= last_day:
        if is_workday(day) and not on_leave(emp, day):
            return day
        day += 1
    return None


def logistic(x):
    return 1 / (1 + math.exp(-x))


def logit(p):
    return math.log(p / (1 - p))


def clamp(x, low=0.0, high=1.0):
    return max(low, min(high, x))


def write_csv(name, rows, fields):
    try:
        f = open(DATA_DIR / name, "w", newline="", encoding="utf-8")
    except PermissionError:
        raise SystemExit(f"Can't write data/{name}: it's probably open in Excel. "
                         "Close it and run again.") from None
    with f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name:<22} {len(rows):>7,} rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    with open(CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)

    random.seed(cfg["population"]["random_seed"])
    roll, sched = cfg["rollout"], cfg["schedule"]
    tool = roll["change_name"]

    start_date = roll["first_week_start"]
    total_days = 7 * (roll["baseline_weeks"] + roll["rollout_weeks"])
    last_day = total_days - 1
    go_live = 7 * roll["baseline_weeks"]                  # first day of go-live week

    def week_start(week_number):                          # week 1 starts on day 0
        return 7 * (week_number - 1)

    def date_of(day):
        return "" if day is None else (start_date + timedelta(days=day)).isoformat()

    email_send = {t: week_start(w) for w, t in
                  zip(sched["communication_weeks"], sched["communication_types"])}
    link_emails = sched["registration_link_in"]
    training_open = week_start(min(sched["training_weeks"]))
    deadline = week_start(sched["training_deadline_week"]) + 6   # Sunday of deadline week

    assert sum(d["headcount"] for d in cfg["departments"]) == cfg["population"]["total_employees"]

    # --- Employees and leave of absence -----------------------------------
    employees = []
    for dept in cfg["departments"]:
        for _ in range(dept["headcount"]):
            emp = dict(id=f"E{len(employees) + 1:04d}", dept=dept,
                       pat=PATTERNS[dept["test_pattern"]],
                       loa_start=None, loa_end=None,
                       z=random.gauss(0, 1))     # personal attitude: drives both usage and survey
            if random.random() < LOA_SHARE:
                emp["loa_start"] = random.randint(0, last_day)
                emp["loa_end"] = emp["loa_start"] + random.randint(*LOA_DAYS) - 1
            employees.append(emp)

    comms, training, surveys, comments, usage, outcomes = [], [], [], [], [], []

    for emp in employees:
        pat = emp["pat"]

        # --- Training (decided first, so emails can be made consistent) ---
        roll_dice = random.random()
        if roll_dice < pat["on_time"]:
            completed = pick_workday(emp, training_open, deadline)
        elif roll_dice < pat["on_time"] + pat["late"]:
            # Late: most finish within a few weeks of the deadline (after escalation).
            target = deadline + 1 + min(int(random.expovariate(1 / 10)), 35)
            completed = first_workday_from(emp, target, last_day)
        else:
            completed = None
        if completed is None and roll_dice < pat["on_time"] + pat["late"]:
            # Their leave covered the whole window: they finish after returning.
            completed = first_workday_from(emp, (emp["loa_end"] or deadline) + random.randint(1, 10), last_day)

        # Which link email got them to register, and when they opened it.
        opened = {t: None for t in email_send}
        registered = None
        if completed is not None:
            via = "training_invitation"
            if len(link_emails) > 1 and completed >= email_send[link_emails[1]] and random.random() < 0.35:
                via = link_emails[1]                                 # the reminder did it
            opened[via] = pick_workday(emp, email_send[via], completed) or completed
            registered = pick_workday(emp, opened[via], completed) or completed
        elif random.random() < 0.5:
            # Never completed, but opened the invitation; some even registered.
            opened["training_invitation"] = pick_workday(emp, email_send["training_invitation"], last_day)
            if opened["training_invitation"] is not None and random.random() < 0.3:
                registered = pick_workday(emp, opened["training_invitation"], last_day)

        training.append(dict(employee_id=emp["id"],
                             assigned_date=date_of(email_send["training_invitation"]),
                             registered_date=date_of(registered),
                             completed_date=date_of(completed)))
        emp["completed"] = completed

        # --- Emails ------------------------------------------------------
        # Any email not already opened above is opened by chance, usually within
        # a couple of days. Extra opens never break the registration rule: the
        # email that led to registration was always opened first.
        for email_type, sent in email_send.items():
            never_registered_skip = (email_type == "training_invitation"
                                     and completed is None and opened[email_type] is None)
            if opened[email_type] is None and not never_registered_skip \
                    and random.random() < pat["email_open"]:
                delay = int(random.expovariate(1 / 1.5))
                opened[email_type] = first_workday_from(emp, sent + delay, last_day)
            comms.append(dict(employee_id=emp["id"], email_type=email_type,
                              sent_date=date_of(sent), opened_date=date_of(opened[email_type])))

        # --- Daily tool usage (only after go-live) -------------------------
        # Each person's usage level sits on a smooth scale around the department's
        # typical level; their personal attitude (z) moves it up or down.
        if random.random() < pat["non_user"]:
            full_level = 0.0
        else:
            full_level = logistic(logit(pat["usage_level"]) + 1.1 * emp["z"])
        # Scorecard floor: because use shows on each person's performance
        # scorecard, anyone who isn't a deliberate non-user sends a quick prompt
        # (1-2) if they've gone too long without one. Light users "check the box".
        emp["active_by_day"] = {}
        floor_due = go_live + random.randint(5, 20)
        for day in range(go_live, total_days):
            if not is_workday(day) or on_leave(emp, day):
                continue
            if completed is not None and day >= completed:
                progress = min(1.0, (day - completed) / pat["ramp_days"])
                level = full_level * (pat["untrained_factor"] + (1 - pat["untrained_factor"]) * progress)
            else:
                level = full_level * pat["untrained_factor"]
            if random.random() < level:
                prompts = max(1, round(random.lognormvariate(math.log(1.5 + 12 * full_level), 0.5)))
            elif full_level > 0 and day >= floor_due:
                prompts = random.randint(1, 2)
            else:
                continue
            usage.append(dict(employee_id=emp["id"], usage_date=date_of(day), prompts=prompts))
            emp["active_by_day"][day] = True
            floor_due = day + random.randint(*FLOOR_GAP_DAYS)

        # --- Surveys (optional) ---------------------------------------------
        for wave, survey_week in enumerate(sched["survey_weeks"]):
            first = week_start(survey_week)
            if random.random() >= pat["survey_response"]:
                continue
            answered = pick_workday(emp, first, first + 4)
            if answered is None:
                continue                                # on leave all survey week
            scores = []
            for q_id in SURVEY_QUESTIONS:
                p_fav = clamp(pat["favorable"][wave] + pat["question_shift"].get(q_id, 0)
                              + 0.06 * emp["z"], 0.02, 0.98)
                if random.random() < p_fav:
                    score = random.choices([6, 7], weights=[60, 40])[0]
                else:
                    score = random.choices([1, 2, 3, 4, 5], weights=[4, 8, 18, 35, 35])[0]
                scores.append(score)
                surveys.append(dict(employee_id=emp["id"], survey_week=survey_week,
                                    response_date=date_of(answered), question_id=q_id,
                                    question_text=SURVEY_QUESTIONS[q_id].format(tool=tool),
                                    score=score))
            if random.random() < COMMENT_CHANCE:
                theme, positive, negative = random.choice(COMMENT_BANK)
                text = positive if sum(scores) / len(scores) >= 5 else negative
                comments.append(dict(employee_id=emp["id"], survey_week=survey_week,
                                     response_date=date_of(answered), comment=text))

    # --- Outcomes: per employee per week --------------------------------------
    # A common weekly "shock" per department adds realistic week-to-week noise.
    n_weeks = roll["baseline_weeks"] + roll["rollout_weeks"]
    shocks = {d["name"]: [random.gauss(0, 0.015) for _ in range(n_weeks)] for d in cfg["departments"]}
    for emp in employees:
        dept, pat = emp["dept"], emp["pat"]
        personal_base = dept["outcome_baseline"] * random.gauss(1, 0.08)
        recent = []                                  # this week's and last week's usage intensity
        for w in range(n_weeks):
            workdays = [d for d in range(7 * w, 7 * w + 5) if not on_leave(emp, d)]
            if len(workdays) < 3:                     # mostly on leave: no outcome that week
                recent = []
                continue
            active = sum(1 for d in workdays if emp["active_by_day"].get(d))
            recent = (recent + [active / len(workdays)])[-2:]
            intensity = sum(recent) / len(recent)
            trained = emp["completed"] is not None and emp["completed"] <= 7 * w + 4
            effect = pat["outcome_gain"] * intensity * (1.0 if trained else 0.5)
            noise = random.gauss(1, 0.04) * (1 + shocks[dept["name"]][w])
            if dept["better_when"] == "lower":
                value = personal_base * (1 - effect) * noise
            else:
                value = min(100.0, personal_base * (1 + effect) * noise)
            volume = max(1, round(dept["weekly_volume"] * len(workdays) / 5 * random.gauss(1, 0.1)))
            outcomes.append(dict(employee_id=emp["id"], week=w + 1, week_start=date_of(7 * w),
                                 outcome_value=round(value, 2), volume=volume))

    # --- Write files -----------------------------------------------------------
    DATA_DIR.mkdir(exist_ok=True)
    print(f"SYNTHETIC DATA for {roll['organization']} / {tool} (seed {cfg['population']['random_seed']})")
    write_csv("employees.csv",
              [dict(employee_id=e["id"], department=e["dept"]["name"],
                    loa_start_date=date_of(e["loa_start"]), loa_end_date=date_of(e["loa_end"]))
               for e in employees],
              ["employee_id", "department", "loa_start_date", "loa_end_date"])
    write_csv("communications.csv", comms, ["employee_id", "email_type", "sent_date", "opened_date"])
    write_csv("training.csv", training, ["employee_id", "assigned_date", "registered_date", "completed_date"])
    write_csv("surveys.csv", surveys,
              ["employee_id", "survey_week", "response_date", "question_id", "question_text", "score"])
    write_csv("survey_comments.csv", comments, ["employee_id", "survey_week", "response_date", "comment"])
    write_csv("usage.csv", usage, ["employee_id", "usage_date", "prompts"])
    write_csv("outcomes.csv", outcomes, ["employee_id", "week", "week_start", "outcome_value", "volume"])


if __name__ == "__main__":
    main()
