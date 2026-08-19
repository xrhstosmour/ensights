-- Association rules from the most recent mining run.
--
-- Lift above 1.0 is the filter that matters: support and confidence alone
-- promote rules whose consequent is merely popular.
SELECT
    rule.antecedent_descriptions AS "If Basket Contains",
    rule.consequent_descriptions AS "Also Contains",
    ROUND(rule.support::numeric, 4)    AS "Support",
    ROUND(rule.confidence::numeric, 4) AS "Confidence",
    ROUND(rule.lift::numeric, 4)       AS "Lift",
    rule.algorithm                     AS "Algorithm",
    rule.computed_at                   AS "Computed At"
FROM association_rules AS rule
WHERE rule.deleted_at IS NULL
  AND rule.computed_at = (
      SELECT MAX(computed_at) FROM association_rules WHERE deleted_at IS NULL
  )
  AND rule.lift >= 1.0
ORDER BY rule.lift DESC
LIMIT 50;
