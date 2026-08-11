-- Recency, frequency and monetary value per customer.
--
-- Recency is measured against the latest order in the data rather than the
-- current date, which keeps results reproducible for a historical dataset.
--
-- The monetary column is observed value to date. It is NOT a predicted
-- lifetime value; no model is involved.
WITH reference AS (
    SELECT MAX(ordered_at) AS as_of
    FROM orders
    WHERE deleted_at IS NULL
)
SELECT
    customer.external_identifier                                AS customer,
    region.name                                                 AS region,
    FLOOR(
        EXTRACT(EPOCH FROM (reference.as_of - MAX("order".ordered_at))) / 86400.0
    )::int                                                      AS recency_days,
    COUNT(DISTINCT "order".id)                                  AS frequency,
    SUM(item.line_total)                                        AS monetary,
    MIN("order".ordered_at)                                     AS first_purchase,
    MAX("order".ordered_at)                                     AS last_purchase
FROM order_items AS item
JOIN orders    AS "order"  ON "order".id = item.order_id
JOIN customers AS customer ON customer.id = "order".customer_id
LEFT JOIN regions AS region ON region.id = "order".region_id
CROSS JOIN reference
WHERE item.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  AND customer.deleted_at IS NULL
GROUP BY customer.external_identifier, region.name, reference.as_of
ORDER BY monetary DESC;
