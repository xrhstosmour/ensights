-- Regions with the most sales.
--
-- The region is read from the order, not the customer: where a sale happened
-- is a property of that sale, and it stays correct if a buyer's region is
-- later corrected.
SELECT
    region.name                          AS "Region",
    COUNT(DISTINCT "order".id)           AS "Orders",
    COUNT(DISTINCT "order".customer_id)  AS "Customers",
    SUM(item.quantity)                   AS "Units",
    SUM(item.line_total)                 AS "Revenue"
FROM order_items AS item
JOIN orders  AS "order" ON "order".id = item.order_id
JOIN regions AS region  ON region.id = "order".region_id
WHERE item.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  AND region.deleted_at IS NULL
  [[AND "order".ordered_at >= {{start}}]]
  [[AND "order".ordered_at <  {{end}}]]
GROUP BY region.name
ORDER BY "Revenue" DESC;
