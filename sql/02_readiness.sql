-- =====================================================================
-- 02_readiness.sql: READINESS & SENTIMENT
-- "Do people feel prepared and positive about the change?"
--
-- Surveys are optional, on a 1-7 scale. An answer of 6 or 7 is favorable.
--
-- Headline (sets the color): PERCENT FAVORABLE, latest survey wave
--   = answers scored 6-7 / all answers, from eligible respondents
--   Eligible = NOT on leave of absence at any point during the survey week.
--
-- Caution flag: if under 50% of eligible employees responded, the color
-- still shows but is marked "low response".
--
-- Views created:
--   eligible_survey_answers          answers from eligible employees only
--   readiness_by_department_wave     one row per department per survey wave
--   readiness_by_question            percent favorable per question per wave
--   readiness_by_department          latest wave + color + caution flag
-- =====================================================================

DROP VIEW IF EXISTS eligible_survey_answers;
CREATE VIEW eligible_survey_answers AS
SELECT
    e.department,
    sv.survey_week,
    sv.employee_id,
    sv.question_id,
    sv.question_text,
    sv.score,
    (sv.score >= s.favorable_minimum) AS is_favorable
FROM surveys sv
JOIN employees       e USING (employee_id)
JOIN survey_schedule w USING (survey_week)
CROSS JOIN settings  s
WHERE CASE WHEN e.loa_start_date <= w.wave_end
            AND e.loa_end_date   >= w.wave_start
           THEN 1 ELSE 0 END = 0;


DROP VIEW IF EXISTS readiness_by_department_wave;
CREATE VIEW readiness_by_department_wave AS
WITH eligible AS (
    -- Everyone NOT on leave during the survey week could have answered.
    SELECT e.department, w.survey_week, w.wave_number, COUNT(*) AS eligible
    FROM employees e
    CROSS JOIN survey_schedule w
    WHERE CASE WHEN e.loa_start_date <= w.wave_end
                AND e.loa_end_date   >= w.wave_start
               THEN 1 ELSE 0 END = 0
    GROUP BY e.department, w.survey_week, w.wave_number
),
answers AS (
    SELECT department, survey_week,
           COUNT(DISTINCT employee_id) AS respondents,
           COUNT(*)                    AS answers,
           SUM(is_favorable)           AS favorable_answers
    FROM eligible_survey_answers
    GROUP BY department, survey_week
)
SELECT
    el.department,
    el.survey_week,
    el.wave_number,
    el.eligible,
    COALESCE(a.respondents, 0)                                   AS respondents,
    ROUND(100.0 * COALESCE(a.respondents, 0) / el.eligible, 1)   AS response_rate,
    COALESCE(a.answers, 0)                                       AS answers,
    COALESCE(a.favorable_answers, 0)                             AS favorable_answers,
    100.0 * a.favorable_answers / a.answers                      AS pct_favorable_exact
FROM eligible el
LEFT JOIN answers a USING (department, survey_week);


DROP VIEW IF EXISTS readiness_by_question;
CREATE VIEW readiness_by_question AS
SELECT
    department,
    survey_week,
    question_id,
    question_text,
    COUNT(*)                                     AS answers,
    ROUND(100.0 * SUM(is_favorable) / COUNT(*), 1) AS pct_favorable
FROM eligible_survey_answers
GROUP BY department, survey_week, question_id, question_text;


DROP VIEW IF EXISTS readiness_by_department;
CREATE VIEW readiness_by_department AS
WITH latest AS (
    SELECT * FROM readiness_by_department_wave
    WHERE survey_week = (SELECT MAX(survey_week) FROM survey_schedule)
),
first_wave AS (
    SELECT department, pct_favorable_exact AS first_pct
    FROM readiness_by_department_wave
    WHERE survey_week = (SELECT MIN(survey_week) FROM survey_schedule)
)
SELECT
    l.department,
    l.survey_week                                AS latest_survey_week,
    l.eligible,
    l.respondents,
    l.response_rate,
    ROUND(l.pct_favorable_exact, 1)              AS pct_favorable,
    ROUND(l.pct_favorable_exact - f.first_pct, 1) AS change_since_first_wave,
    CASE WHEN l.response_rate < s.low_response_rate
         THEN 'Low response: interpret with caution' END AS caution,
    CASE WHEN l.pct_favorable_exact >= s.readiness_green THEN 'Green'
         WHEN l.pct_favorable_exact >= s.readiness_amber THEN 'Amber'
         ELSE 'Red'
    END                                          AS readiness_color
FROM latest l
JOIN first_wave f USING (department)
CROSS JOIN settings s;
