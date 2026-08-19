-- When sales happen, bucketed by month.
--
-- Change 'month' to day, week, quarter or year for a different resolution.
-- The period is rendered as ISO 8601 text to match what the API returns.
-- Sorting stays chronological because ISO 8601 sorts correctly as text.
SELECT
    TO_CHAR(
        DATE_TRUNC('month', "order".ordered_at),
        'YYYY-MM-DD"T"HH24:MI:SS.MS'
    )                                       AS period,
    COUNT(DISTINCT "order".id)              AS orders,
    SUM(item.quantity)                      AS units,
    SUM(item.line_total)                    AS revenue
FROM order_items AS item
JOIN orders AS "order" ON "order".id = item.order_id
WHERE item.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  [[AND "order".ordered_at >= {{start}}]]
  [[AND "order".ordered_at <  {{end}}]]
GROUP BY period
ORDER BY period;
