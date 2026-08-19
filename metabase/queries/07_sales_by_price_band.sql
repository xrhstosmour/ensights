-- Sales per price range.
--
-- Banding uses the price actually charged on the line, not the product's
-- current price, so a product that moved between bands is counted where it
-- sold. The bands partition revenue, so they sum to the overall total.
SELECT
    CASE
        WHEN item.unit_price <  1  THEN '0-1'
        WHEN item.unit_price <  5  THEN '1-5'
        WHEN item.unit_price < 10  THEN '5-10'
        WHEN item.unit_price < 50  THEN '10-50'
        ELSE '50+'
    END                          AS "Price Band",
    COUNT(item.id)               AS "Lines",
    SUM(item.quantity)           AS "Units",
    SUM(item.line_total)         AS "Revenue"
FROM order_items AS item
JOIN orders AS "order" ON "order".id = item.order_id
WHERE item.deleted_at IS NULL
  AND "order".deleted_at IS NULL
  [[AND "order".ordered_at >= {{start}}]]
  [[AND "order".ordered_at <  {{end}}]]
GROUP BY "Price Band"
ORDER BY MIN(item.unit_price);
