-- The 3 required SQL demonstrations (spec > Required SQL demonstrations).
-- Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
-- EY brief section 03 "Required SQL demonstrations". The same SQL is used by
-- backend/app/repositories/report_repo.py for the manager's Spending Summary page.
-- To run in pgAdmin: replace :manager_id with the manager's employee_id (1 = Vikram Iyer in the seed).

-- 1. Join trips and expenses: employee, destination, expense type and amount
SELECT e.full_name AS employee_name, t.trip_code, t.destination,
       x.expense_code, x.expense_type, x.amount, x.status
FROM expenses x
JOIN travel_requests t ON t.trip_id = x.trip_id
JOIN employees e       ON e.employee_id = t.employee_id
WHERE e.manager_id = :manager_id
ORDER BY t.trip_code, x.expense_code;

-- 2. Spending by trip and category (approved money only), with a trip total row
SELECT t.trip_code, t.destination, x.expense_type,
       COUNT(*) AS line_count, SUM(x.amount) AS total_amount
FROM expenses x
JOIN travel_requests t ON t.trip_id = x.trip_id
JOIN employees e       ON e.employee_id = t.employee_id
WHERE x.status IN ('APPROVED','AUTO_APPROVED') AND e.manager_id = :manager_id
GROUP BY GROUPING SETS ((t.trip_code, t.destination, x.expense_type), (t.trip_code, t.destination))
ORDER BY t.trip_code, x.expense_type NULLS LAST;

-- 3. Pending manager approvals: flagged lines not yet decided
SELECT x.expense_code, k.ticket_code, t.trip_code, e.full_name AS employee_name, t.destination,
       x.expense_type, x.amount, ARRAY_AGG(f.rule_code ORDER BY f.rule_code) AS flag_codes, k.submitted_at
FROM expenses x
JOIN expense_tickets k ON k.ticket_id = x.ticket_id
JOIN travel_requests t ON t.trip_id = x.trip_id
JOIN employees e       ON e.employee_id = t.employee_id
JOIN policy_flags f    ON f.expense_id = x.expense_id
WHERE k.status = 'PENDING' AND e.manager_id = :manager_id
GROUP BY x.expense_id, k.ticket_id, t.trip_id, e.employee_id
ORDER BY k.submitted_at;
