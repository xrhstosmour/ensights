-- Monthly acquisition cohorts and their later activity.
--
-- Customers are grouped by the month of their first purchase and counted in
-- every month they bought again. period_index is whole months after
-- acquisition, so 0 is the cohort's own month. The grid is triangular by
-- construction: newer cohorts have had fewer months to come back.
WITH activity AS (
    SELECT DISTINCT
        "order".customer_id,
        DATE_TRUNC('month', "order".ordered_at) AS activity_month
    FROM orders AS "order"
    WHERE "order".deleted_at IS NULL
      AND "order".customer_id IS NOT NULL
),
first_purchase AS (
    SELECT customer_id, MIN(activity_month) AS cohort_month
    FROM activity
    GROUP BY customer_id
),
grid AS (
    SELECT
        first_purchase.cohort_month,
        ROUND(
            EXTRACT(EPOCH FROM (activity.activity_month - first_purchase.cohort_month))
            / 2629746.0
        )::int                                        AS period_index,
        COUNT(DISTINCT activity.customer_id)          AS active_customers
    FROM activity
    JOIN first_purchase ON first_purchase.customer_id = activity.customer_id
    GROUP BY first_purchase.cohort_month, period_index
)
SELECT
    -- Formatted only at output: the CTEs above do month arithmetic on the
    -- real timestamp, and ORDER BY below still uses that raw column.
    TO_CHAR(grid.cohort_month, 'YYYY-MM-DD"T"HH24:MI:SS.MS') AS cohort_month,
    grid.period_index,
    grid.active_customers,
    size.cohort_size,
    ROUND(grid.active_customers::numeric / size.cohort_size, 4) AS retention_rate
FROM grid
JOIN (
    SELECT cohort_month, active_customers AS cohort_size
    FROM grid
    WHERE period_index = 0
) AS size ON size.cohort_month = grid.cohort_month
ORDER BY grid.cohort_month, grid.period_index;
