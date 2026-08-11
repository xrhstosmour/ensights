-- Which days of the week sell most.
--
-- Weekly seasonality is invisible in monthly totals, so it gets its own card.
SELECT
    EXTRACT(DOW FROM "order".ordered_at)            AS weekday_number,
    TO_CHAR("order".ordered_at, 'Day')              AS weekday,
    COUNT(DISTINCT "order".id)                      AS orders,
    SUM(item.line_total)                            AS revenue
FROM order_items AS item
JOIN orders AS "order" ON "order".id = item.order_id
WHERE item.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  [[AND "order".ordered_at >= {{start}}]]
  [[AND "order".ordered_at <  {{end}}]]
GROUP BY weekday_number, weekday
ORDER BY weekday_number;
