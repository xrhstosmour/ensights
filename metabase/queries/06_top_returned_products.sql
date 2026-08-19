-- Products with the most refunds, by value.
--
-- Returns are their own rows with positive quantities, never negative order
-- lines, so refunds are never silently netted out of revenue.
SELECT
    product.stock_code            AS "Stock Code",
    product.description           AS "Product",
    SUM(product_return.quantity)  AS "Units Returned",
    SUM(product_return.amount)    AS "Value Returned",
    COUNT(product_return.id)      AS "Return Lines"
FROM returns AS product_return
JOIN products AS product ON product.id = product_return.product_id
WHERE product_return.deleted_at IS NULL
  AND product.deleted_at IS NULL
  [[AND product_return.returned_at >= {{start}}]]
  [[AND product_return.returned_at <  {{end}}]]
GROUP BY product.stock_code, product.description
ORDER BY "Value Returned" DESC
LIMIT 20;
