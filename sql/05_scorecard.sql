-- =====================================================================
-- 05_scorecard.sql: THE SCORECARD
-- One row per department: the four headline numbers and their colors.
-- Built only from the four measure files above.
-- =====================================================================

DROP VIEW IF EXISTS scorecard;
CREATE VIEW scorecard AS
SELECT
    d.sort_order,
    d.department,
    r.on_time_rate,
    r.reach_color,
    rd.pct_favorable,
    rd.response_rate,
    rd.caution            AS readiness_caution,
    rd.readiness_color,
    a.heavy_user_rate,
    a.minimum_use_rate,
    a.gate_triggered,
    a.adoption_color,
    o.outcome_metric,
    o.improvement_pct,
    o.outcomes_color
FROM departments d
JOIN reach_by_department     r  USING (department)
JOIN readiness_by_department rd USING (department)
JOIN adoption_by_department  a  USING (department)
JOIN outcomes_by_department  o  USING (department)
ORDER BY d.sort_order;
