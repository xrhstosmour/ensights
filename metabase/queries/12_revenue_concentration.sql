-- How concentrated revenue is across customers.
--
-- This is the card that catches a false positive: a store whose top handful of
-- customers produce most of its revenue behaves like a wholesaler with key
-- accounts, however it brands itself, and no growth rate reveals that alone.
WITH per_customer AS (
    SELECT
        customer.external_identifier AS customer,
        SUM(item.line_total)         AS revenue
    FROM order_items AS item
    JOIN orders    AS "order"  ON "order".id = item.order_id
    JOIN customers AS customer ON customer.id = "order".customer_id
    WHERE item.deleted_at IS NULL
      AND "order".deleted_at IS NULL
      AND customer.deleted_at IS NULL
    GROUP BY customer.external_identifier
    HAVING SUM(item.line_total) > 0
),
ranked AS (
    SELECT
        customer,
        revenue,
        PERCENT_RANK() OVER (ORDER BY revenue DESC) AS descending_rank
    FROM per_customer
)
SELECT
    CASE
        WHEN descending_rank < 0.10 THEN 'top 10%'
        WHEN descending_rank < 0.20 THEN 'next 10% (to top 20%)'
        WHEN descending_rank < 0.50 THEN 'next 30% (to top 50%)'
        ELSE 'bottom 50%'
    END                                                       AS "Segment",
    COUNT(*)                                                  AS "Customers",
    SUM(revenue)                                              AS "Revenue",
    ROUND(SUM(revenue) / SUM(SUM(revenue)) OVER (), 4)        AS "Revenue Share"
FROM ranked
GROUP BY "Segment"
ORDER BY "Revenue" DESC;
