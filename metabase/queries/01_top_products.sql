-- Products with the highest sales.
--
-- Ranked by revenue rather than units: a cheap high-volume line and an
-- expensive low-volume one answer different questions, and marketing spend
-- follows value.
SELECT
    product.stock_code               AS "Stock Code",
    product.description              AS "Product",
    SUM(item.quantity)                  AS "Units",
    SUM(item.line_total)                AS "Revenue",
    COUNT(DISTINCT item.order_id)       AS "Orders"
FROM order_items AS item
JOIN products AS product ON product.id = item.product_id
JOIN orders   AS "order" ON "order".id = item.order_id
WHERE item.deleted_at IS NULL
  AND product.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  [[AND "order".ordered_at >= {{start}}]]
  [[AND "order".ordered_at <  {{end}}]]
GROUP BY product.stock_code, product.description
ORDER BY "Revenue" DESC
LIMIT 20;
