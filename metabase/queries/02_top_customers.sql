-- Customers with the most purchases, by value.
--
-- Anonymous sales are excluded here, and only here: they cannot be attributed
-- to a buyer. They remain in every product, region and time breakdown.
SELECT
    customer.external_identifier        AS "Customer",
    region.name                         AS "Region",
    COUNT(DISTINCT "order".id)          AS "Orders",
    SUM(item.quantity)                  AS "Units",
    SUM(item.line_total)                AS "Revenue"
FROM order_items AS item
JOIN orders    AS "order" ON "order".id = item.order_id
JOIN customers AS customer ON customer.id = "order".customer_id
LEFT JOIN regions AS region ON region.id = "order".region_id
WHERE item.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  AND customer.deleted_at IS NULL
  [[AND "order".ordered_at >= {{start}}]]
  [[AND "order".ordered_at <  {{end}}]]
GROUP BY customer.external_identifier, region.name
ORDER BY "Revenue" DESC
LIMIT 20;
