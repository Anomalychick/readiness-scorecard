-- =====================================================================
-- 03_adoption.sql: ADOPTION & BEHAVIOR CHANGE
-- "Are people actually using it?"
--
-- Measured over a ROLLING 30-DAY WINDOW. An active day = a day with 1+ prompt.
-- Ratings (per employee):
--   Not using = 0 active days    Meets = 1-4    Exceeds = 5+ ("heavy use")
-- Eligible = NOT on leave of absence at any point during the window.
--
-- Headline (sets the color): HEAVY-USER RATE at the end of the data
--   = eligible employees rated Exceeds / eligible employees
-- Minimum-use gate: if under 97% of eligible employees meet the 1-prompt
-- minimum, the department is RED regardless of its heavy-user rate.
--
-- Views created:
--   adoption_by_employee              rating per employee (final 30 days)
--   adoption_by_department            rates + gate + color
--   adoption_active_days_distribution how many people at 0, 1, 2 ... active days
--   adoption_trend                    rolling 30-day rates at the end of each week
--   usage_by_training_period          use before vs. after each person's training
--   usage_by_training_period_department   the same, rolled up by department
-- =====================================================================

DROP VIEW IF EXISTS adoption_by_employee;
CREATE VIEW adoption_by_employee AS
WITH window_usage AS (
    SELECT u.employee_id,
           COUNT(*)       AS active_days,
           SUM(u.prompts) AS prompts
    FROM usage u
    CROSS JOIN settings s
    WHERE u.usage_date BETWEEN s.adoption_window_start AND s.data_end_date
      AND u.prompts >= s.minimum_prompts
    GROUP BY u.employee_id
)
SELECT
    e.employee_id,
    e.department,
    CASE WHEN e.loa_start_date <= s.data_end_date
          AND e.loa_end_date   >= s.adoption_window_start
         THEN 1 ELSE 0 END                         AS loa_in_window,
    COALESCE(w.active_days, 0)                     AS active_days_30,
    COALESCE(w.prompts, 0)                         AS prompts_30,
    CASE WHEN COALESCE(w.active_days, 0) = 0           THEN 'Not using'
         WHEN w.active_days >= s.heavy_use_active_days THEN 'Exceeds'
         ELSE 'Meets'
    END                                            AS adoption_rating
FROM employees e
CROSS JOIN settings s
LEFT JOIN window_usage w USING (employee_id);


DROP VIEW IF EXISTS adoption_by_department;
CREATE VIEW adoption_by_department AS
WITH counts AS (
    SELECT department,
           COUNT(*)                                        AS employees,
           SUM(loa_in_window)                              AS loa_excluded,
           SUM(1 - loa_in_window)                          AS eligible,
           SUM(loa_in_window = 0 AND adoption_rating = 'Not using') AS not_using,
           SUM(loa_in_window = 0 AND adoption_rating = 'Meets')     AS meets,
           SUM(loa_in_window = 0 AND adoption_rating = 'Exceeds')   AS exceeds
    FROM adoption_by_employee
    GROUP BY department
),
rates AS (
    SELECT *,
           100.0 * exceeds / eligible             AS heavy_user_rate,
           100.0 * (meets + exceeds) / eligible   AS minimum_use_rate
    FROM counts
)
SELECT
    r.department,
    r.employees,
    r.loa_excluded,
    r.eligible,
    r.not_using,
    r.meets,
    r.exceeds,
    ROUND(r.heavy_user_rate, 1)                         AS heavy_user_rate,
    ROUND(r.minimum_use_rate, 1)                        AS minimum_use_rate,
    (r.minimum_use_rate < s.minimum_use_gate)           AS gate_triggered,
    CASE WHEN r.minimum_use_rate < s.minimum_use_gate THEN 'Red'
         WHEN r.heavy_user_rate  >= s.adoption_green  THEN 'Green'
         WHEN r.heavy_user_rate  >= s.adoption_amber  THEN 'Amber'
         ELSE 'Red'
    END                                                 AS adoption_color
FROM rates r
CROSS JOIN settings s;


DROP VIEW IF EXISTS adoption_active_days_distribution;
CREATE VIEW adoption_active_days_distribution AS
SELECT department, active_days_30, COUNT(*) AS employees
FROM adoption_by_employee
WHERE loa_in_window = 0
GROUP BY department, active_days_30;


DROP VIEW IF EXISTS adoption_trend;
CREATE VIEW adoption_trend AS
WITH week_ends AS (
    -- The Sunday ending each week from go-live onward
    SELECT c.week, MAX(c.cal_date) AS week_end
    FROM calendar c
    CROSS JOIN settings s
    WHERE c.cal_date >= s.go_live_date
    GROUP BY c.week
),
per_employee AS (
    SELECT
        e.department,
        we.week,
        we.week_end,
        (SELECT COUNT(*)
           FROM usage u
          WHERE u.employee_id = e.employee_id
            AND u.prompts >= s.minimum_prompts
            AND u.usage_date BETWEEN date(we.week_end, '-' || (s.adoption_window_days - 1) || ' days')
                                 AND we.week_end)                      AS active_days
    FROM employees e
    CROSS JOIN week_ends we
    CROSS JOIN settings s
    WHERE CASE WHEN e.loa_start_date <= we.week_end
                AND e.loa_end_date   >= date(we.week_end, '-' || (s.adoption_window_days - 1) || ' days')
               THEN 1 ELSE 0 END = 0
)
SELECT
    p.department,
    p.week,
    p.week_end,
    COUNT(*)                                                                   AS eligible,
    ROUND(100.0 * SUM(p.active_days >= s.heavy_use_active_days) / COUNT(*), 1) AS heavy_user_rate,
    ROUND(100.0 * SUM(p.active_days >= 1) / COUNT(*), 1)                       AS minimum_use_rate
FROM per_employee p
CROSS JOIN settings s
GROUP BY p.department, p.week, p.week_end;


DROP VIEW IF EXISTS usage_by_training_period;
CREATE VIEW usage_by_training_period AS
-- For each employee: share of available workdays (after go-live, not on leave)
-- with 1+ prompt, BEFORE vs. AFTER their own training completion date.
WITH workdays AS (
    SELECT e.employee_id, e.department, t.completed_date, c.cal_date,
           CASE WHEN t.completed_date IS NULL OR c.cal_date < t.completed_date
                THEN 'Before training' ELSE 'After training' END AS period
    FROM employees e
    JOIN training t USING (employee_id)
    JOIN calendar c
    CROSS JOIN settings s
    WHERE c.is_workday = 1
      AND c.cal_date >= s.go_live_date
      AND CASE WHEN c.cal_date BETWEEN e.loa_start_date AND e.loa_end_date
               THEN 1 ELSE 0 END = 0
)
SELECT
    w.employee_id,
    w.department,
    w.completed_date,
    w.period,
    COUNT(*)                                          AS workdays_available,
    COUNT(u.usage_date)                               AS active_days,
    ROUND(100.0 * COUNT(u.usage_date) / COUNT(*), 1)  AS pct_workdays_active
FROM workdays w
LEFT JOIN usage u
       ON u.employee_id = w.employee_id AND u.usage_date = w.cal_date
GROUP BY w.employee_id, w.department, w.completed_date, w.period;


DROP VIEW IF EXISTS usage_by_training_period_department;
CREATE VIEW usage_by_training_period_department AS
SELECT
    department,
    period,
    COUNT(*)                                                       AS employees,
    SUM(workdays_available)                                        AS workdays_available,
    SUM(active_days)                                               AS active_days,
    ROUND(100.0 * SUM(active_days) / SUM(workdays_available), 1)   AS pct_workdays_active
FROM usage_by_training_period
GROUP BY department, period;
