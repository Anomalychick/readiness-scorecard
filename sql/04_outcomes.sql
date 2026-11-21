-- =====================================================================
-- 04_outcomes.sql: OUTCOMES
-- "Did the business result move?"
--
-- Outcomes are recorded per employee per week, with the work volume behind
-- each value (calls handled, applications processed...). All averages are
-- VOLUME-WEIGHTED:  SUM(value x volume) / SUM(volume).
--
-- Headline (sets the color): IMPROVEMENT VS. BASELINE
--   baseline = the weeks before go-live
--   recent   = the last 4 weeks of data
--   improvement % = (baseline - recent) / baseline   when lower is better
--                   (recent - baseline) / baseline   when higher is better
--   so a positive number always means "got better".
--
-- Periods for the before/after-training comparison (per employee):
--   Baseline              weeks before go-live (no tool yet)
--   Tool, before training weeks after go-live that end before their training date
--   Tool, after training  weeks that start after their training date
--   (the week they trained in is left out as a transition week)
--
-- Views created:
--   outcomes_with_period            every outcome row, tagged with its period
--   outcomes_by_department_week     weekly trend per department
--   outcomes_by_department          baseline vs. recent + color
--   outcomes_by_employee            baseline vs. recent per employee, + rating
--   outcomes_by_training_period     department value per period vs. baseline
--   outcomes_by_adoption_rating     improvement by Not using / Meets / Exceeds
-- =====================================================================

DROP VIEW IF EXISTS outcomes_with_period;
CREATE VIEW outcomes_with_period AS
SELECT
    o.employee_id,
    e.department,
    o.week,
    o.week_start,
    o.outcome_value,
    o.volume,
    CASE WHEN o.week <= s.baseline_weeks                          THEN 'Baseline'
         WHEN t.completed_date IS NULL
           OR date(o.week_start, '+6 days') < t.completed_date    THEN 'Tool, before training'
         WHEN o.week_start > t.completed_date                     THEN 'Tool, after training'
         ELSE 'Training week'
    END                                                           AS period,
    (o.week > s.total_weeks - s.outcome_comparison_weeks)         AS is_recent
FROM outcomes o
JOIN employees e USING (employee_id)
JOIN training  t USING (employee_id)
CROSS JOIN settings s;


DROP VIEW IF EXISTS outcomes_by_department_week;
CREATE VIEW outcomes_by_department_week AS
SELECT
    department,
    week,
    week_start,
    ROUND(SUM(outcome_value * volume) / SUM(volume), 2) AS outcome_value,
    SUM(volume)                                         AS volume
FROM outcomes_with_period
GROUP BY department, week, week_start;


DROP VIEW IF EXISTS outcomes_by_department;
CREATE VIEW outcomes_by_department AS
WITH periods AS (
    SELECT
        department,
        SUM(CASE WHEN period = 'Baseline' THEN outcome_value * volume END)
          / SUM(CASE WHEN period = 'Baseline' THEN volume END)          AS baseline_value,
        SUM(CASE WHEN is_recent THEN outcome_value * volume END)
          / SUM(CASE WHEN is_recent THEN volume END)                    AS recent_value
    FROM outcomes_with_period
    GROUP BY department
),
improvement AS (
    SELECT p.*, d.outcome_metric, d.outcome_unit, d.better_when, d.volume_unit,
           100.0 * CASE WHEN d.better_when = 'lower'
                        THEN (p.baseline_value - p.recent_value)
                        ELSE (p.recent_value - p.baseline_value) END
                 / p.baseline_value                                     AS improvement_pct
    FROM periods p
    JOIN departments d USING (department)
)
SELECT
    i.department,
    i.outcome_metric,
    i.outcome_unit,
    i.better_when,
    ROUND(i.baseline_value, 2)   AS baseline_value,
    ROUND(i.recent_value, 2)     AS recent_value,
    ROUND(i.improvement_pct, 1)  AS improvement_pct,
    CASE WHEN i.improvement_pct >= s.outcomes_green THEN 'Green'
         WHEN i.improvement_pct >= s.outcomes_amber THEN 'Amber'
         ELSE 'Red'
    END                          AS outcomes_color
FROM improvement i
CROSS JOIN settings s;


DROP VIEW IF EXISTS outcomes_by_employee;
CREATE VIEW outcomes_by_employee AS
WITH per_employee AS (
    SELECT
        employee_id,
        department,
        SUM(CASE WHEN period = 'Baseline' THEN outcome_value * volume END)
          / SUM(CASE WHEN period = 'Baseline' THEN volume END)                 AS baseline_value,
        SUM(CASE WHEN period = 'Tool, before training' THEN outcome_value * volume END)
          / SUM(CASE WHEN period = 'Tool, before training' THEN volume END)    AS before_training_value,
        SUM(CASE WHEN period = 'Tool, after training' THEN outcome_value * volume END)
          / SUM(CASE WHEN period = 'Tool, after training' THEN volume END)     AS after_training_value,
        SUM(CASE WHEN is_recent THEN outcome_value * volume END)
          / SUM(CASE WHEN is_recent THEN volume END)                           AS recent_value
    FROM outcomes_with_period
    GROUP BY employee_id, department
)
SELECT
    p.employee_id,
    p.department,
    a.adoption_rating,
    a.active_days_30,
    ROUND(p.baseline_value, 2)          AS baseline_value,
    ROUND(p.before_training_value, 2)   AS before_training_value,
    ROUND(p.after_training_value, 2)    AS after_training_value,
    ROUND(p.recent_value, 2)            AS recent_value,
    ROUND(100.0 * CASE WHEN d.better_when = 'lower'
                       THEN (p.baseline_value - p.recent_value)
                       ELSE (p.recent_value - p.baseline_value) END
          / p.baseline_value, 1)        AS improvement_pct
FROM per_employee p
JOIN departments d USING (department)
JOIN adoption_by_employee a USING (employee_id);


DROP VIEW IF EXISTS outcomes_by_training_period;
CREATE VIEW outcomes_by_training_period AS
WITH by_period AS (
    SELECT department, period,
           COUNT(DISTINCT employee_id)              AS employees,
           SUM(outcome_value * volume) / SUM(volume) AS value
    FROM outcomes_with_period
    WHERE period <> 'Training week'
    GROUP BY department, period
)
SELECT
    p.department,
    p.period,
    p.employees,
    ROUND(p.value, 2)                                       AS outcome_value,
    ROUND(100.0 * CASE WHEN d.better_when = 'lower'
                       THEN (b.value - p.value)
                       ELSE (p.value - b.value) END
          / b.value, 1)                                     AS improvement_vs_baseline_pct
FROM by_period p
JOIN by_period b ON b.department = p.department AND b.period = 'Baseline'
JOIN departments d ON d.department = p.department;


DROP VIEW IF EXISTS outcomes_by_adoption_rating;
CREATE VIEW outcomes_by_adoption_rating AS
-- Compares outcome change for groups of employees by their final adoption
-- rating. This shows whether heavier use LINES UP with bigger gains. It does
-- not prove the tool caused them (e.g., strong performers may adopt first).
WITH groups AS (
    SELECT
        o.department,
        a.adoption_rating,
        COUNT(DISTINCT o.employee_id)                                           AS employees,
        SUM(CASE WHEN o.period = 'Baseline' THEN o.outcome_value * o.volume END)
          / SUM(CASE WHEN o.period = 'Baseline' THEN o.volume END)              AS baseline_value,
        SUM(CASE WHEN o.is_recent THEN o.outcome_value * o.volume END)
          / SUM(CASE WHEN o.is_recent THEN o.volume END)                        AS recent_value
    FROM outcomes_with_period o
    JOIN adoption_by_employee a USING (employee_id)
    WHERE a.loa_in_window = 0
    GROUP BY o.department, a.adoption_rating
)
SELECT
    g.department,
    g.adoption_rating,
    g.employees,
    ROUND(g.baseline_value, 2) AS baseline_value,
    ROUND(g.recent_value, 2)   AS recent_value,
    ROUND(100.0 * CASE WHEN d.better_when = 'lower'
                       THEN (g.baseline_value - g.recent_value)
                       ELSE (g.recent_value - g.baseline_value) END
          / g.baseline_value, 1) AS improvement_pct
FROM groups g
JOIN departments d USING (department);
