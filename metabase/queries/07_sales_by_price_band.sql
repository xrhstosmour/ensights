-- Sales per price range.
--
-- Banding uses the price actually charged on the line, not the product's
-- current price, so a product that moved between bands is counted where it
-- sold. The bands partition revenue, so they sum to the overall total.
--
-- The band list is spelled out as a CTE rather than left implicit in a CASE,
-- so this card matches `PRICE_BANDS` in
-- `app/repositories/analytics_repository.py` on both edges the endpoint is
-- careful about: every band appears even when nothing sold in it, and a line
-- that no band claims, which needs a price below zero, is reported as
-- "unknown" after the bands instead of being folded into "0-1".
WITH band AS (
    SELECT * FROM (
        VALUES
            (1, '0-1',    0::numeric,   1::numeric),
            (2, '1-5',    1::numeric,   5::numeric),
            (3, '5-10',   5::numeric,  10::numeric),
            (4, '10-50', 10::numeric,  50::numeric),
            (5, '50+',   50::numeric, NULL::numeric)
    ) AS bands(sort_order, label, lower_bound, upper_bound)
),
line AS (
    SELECT
        item.id,
        item.quantity,
        item.line_total,
        item.unit_price
    FROM order_items AS item
    JOIN orders AS "order" ON "order".id = item.order_id
    WHERE item.deleted_at IS NULL
      AND "order".deleted_at IS NULL
      [[AND "order".ordered_at >= {{start}}]]
      [[AND "order".ordered_at <  {{end}}]]
),
banded AS (
    SELECT
        band.sort_order,
        band.label,
        COUNT(line.id)                    AS lines,
        COALESCE(SUM(line.quantity), 0)   AS units,
        COALESCE(SUM(line.line_total), 0) AS revenue
    FROM band
    LEFT JOIN line
           ON line.unit_price >= band.lower_bound
          AND (band.upper_bound IS NULL OR line.unit_price < band.upper_bound)
    GROUP BY band.sort_order, band.label

    UNION ALL

    -- Reported only when it has something in it, which is how the endpoint
    -- appends its own "unknown" row.
    SELECT
        6,
        'unknown',
        COUNT(line.id),
        COALESCE(SUM(line.quantity), 0),
        COALESCE(SUM(line.line_total), 0)
    FROM line
    WHERE line.unit_price < 0
    HAVING COUNT(line.id) > 0
)
SELECT
    banded.label   AS "Price Band",
    banded.lines   AS "Lines",
    banded.units   AS "Units",
    banded.revenue AS "Revenue"
FROM banded
ORDER BY banded.sort_order;
