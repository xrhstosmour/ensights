-- Gross merchandise value, with refunds and net value alongside.
--
-- GMV is reported gross of refunds, the conventional definition. The refunded
-- and net columns sit beside it so neither figure can quietly disappear into
-- the other.
--
-- The period is rendered as ISO 8601 text to match what the API returns. Both
-- sides format identically, so the join below still pairs the right months,
-- and sorting stays chronological because ISO 8601 sorts correctly as text.
WITH sales AS (
    SELECT
        TO_CHAR(
            DATE_TRUNC('month', "order".ordered_at),
            'YYYY-MM-DD"T"HH24:MI:SS.MS'
        )                                       AS period,
        COUNT(DISTINCT "order".id)              AS orders,
        SUM(item.line_total)                    AS gross_merchandise_value
    FROM order_items AS item
    JOIN orders AS "order" ON "order".id = item.order_id
    WHERE item.deleted_at IS NULL
      AND "order".deleted_at IS NULL
    GROUP BY period
),
refunds AS (
    SELECT
        TO_CHAR(
            DATE_TRUNC('month', product_return.returned_at),
            'YYYY-MM-DD"T"HH24:MI:SS.MS'
        )                                               AS period,
        SUM(product_return.amount)                      AS refunds
    FROM returns AS product_return
    WHERE product_return.deleted_at IS NULL
    GROUP BY period
)
SELECT
    sales.period,
    sales.orders,
    sales.gross_merchandise_value,
    COALESCE(refunds.refunds, 0)                                AS refunds,
    sales.gross_merchandise_value - COALESCE(refunds.refunds, 0) AS net_merchandise_value
FROM sales
LEFT JOIN refunds ON refunds.period = sales.period
ORDER BY sales.period;
