-- =====================================================================
-- 01_reach.sql: REACH & ENGAGEMENT
-- "Did people get the communications, and did they complete training on time?"
--
-- Headline (sets the color): ON-TIME TRAINING COMPLETION RATE
--   = employees who completed training by the deadline
--     / ELIGIBLE employees
--   Eligible = NOT on leave of absence at any point during the training
--   window (LOA = TRUE is excluded from both numerator and denominator).
--
-- Views created:
--   reach_by_employee          one row per employee: status, LOA flag
--   reach_by_department        one row per department: rates + color
--   email_opens_by_department  open rate per email per department
-- =====================================================================

DROP VIEW IF EXISTS reach_by_employee;
CREATE VIEW reach_by_employee AS
SELECT
    e.employee_id,
    e.department,
    -- LOA = TRUE if the leave overlaps the training window at all.
    -- (Employees with no leave have NULL dates, so the test is false -> 0.)
    CASE WHEN e.loa_start_date <= s.training_deadline_date
          AND e.loa_end_date   >= s.training_start_date
         THEN 1 ELSE 0 END                                AS loa_in_training_window,
    t.registered_date,
    t.completed_date,
    CASE WHEN t.completed_date IS NULL                     THEN 'Not completed'
         WHEN t.completed_date <= s.training_deadline_date THEN 'On time'
         ELSE 'Late'
    END                                                   AS training_status,
    -- Did the reminder email get them to register, or did they register before it?
    CASE WHEN t.registered_date IS NULL               THEN NULL
         WHEN t.registered_date >= s.reminder_sent_date THEN 'After reminder'
         ELSE 'Before reminder'
    END                                                   AS registered_when
FROM employees e
JOIN training  t USING (employee_id)
CROSS JOIN settings s;


DROP VIEW IF EXISTS reach_by_department;
CREATE VIEW reach_by_department AS
WITH counts AS (
    SELECT
        department,
        COUNT(*)                                                         AS employees,
        SUM(loa_in_training_window)                                      AS loa_excluded,
        SUM(1 - loa_in_training_window)                                  AS eligible,
        SUM(loa_in_training_window = 0 AND training_status = 'On time')       AS on_time,
        SUM(loa_in_training_window = 0 AND training_status = 'Late')          AS late,
        SUM(loa_in_training_window = 0 AND training_status = 'Not completed') AS not_completed,
        SUM(loa_in_training_window = 0 AND registered_date IS NOT NULL)       AS registered,
        SUM(loa_in_training_window = 0 AND registered_when = 'After reminder') AS registered_after_reminder
    FROM reach_by_employee
    GROUP BY department
),
rates AS (
    SELECT *,
        100.0 * on_time / eligible                       AS on_time_rate,
        100.0 * (on_time + late) / eligible              AS completed_by_data_end_rate,
        100.0 * registered_after_reminder / registered   AS pct_registered_after_reminder
    FROM counts
)
SELECT
    r.department,
    r.employees,
    r.loa_excluded,
    r.eligible,
    r.on_time,
    r.late,
    r.not_completed,
    ROUND(r.on_time_rate, 1)                    AS on_time_rate,
    ROUND(r.completed_by_data_end_rate, 1)      AS completed_by_data_end_rate,
    ROUND(r.pct_registered_after_reminder, 1)   AS pct_registered_after_reminder,
    CASE WHEN r.on_time_rate >= s.reach_green THEN 'Green'
         WHEN r.on_time_rate >= s.reach_amber THEN 'Amber'
         ELSE 'Red'
    END                                         AS reach_color
FROM rates r
CROSS JOIN settings s;


DROP VIEW IF EXISTS email_opens_by_department;
CREATE VIEW email_opens_by_department AS
SELECT
    e.department,
    c.email_type,
    c.sent_date,
    COUNT(*)                                                 AS sent,
    SUM(c.opened_date IS NOT NULL)                           AS opened,
    ROUND(100.0 * SUM(c.opened_date IS NOT NULL) / COUNT(*), 1) AS open_rate
FROM communications c
JOIN employees e USING (employee_id)
GROUP BY e.department, c.email_type, c.sent_date;
