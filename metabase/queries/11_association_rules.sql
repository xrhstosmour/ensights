-- Association rules from the most recent mining run.
--
-- Lift above 1.0 is the filter that matters: support and confidence alone
-- promote rules whose consequent is merely popular.
SELECT
    rule.antecedent_descriptions AS "if the basket contains",
    rule.consequent_descriptions AS "it also tends to contain",
    ROUND(rule.support::numeric, 4)    AS support,
    ROUND(rule.confidence::numeric, 4) AS confidence,
    ROUND(rule.lift::numeric, 4)       AS lift,
    rule.algorithm,
    rule.computed_at
FROM association_rules AS rule
WHERE rule.deleted_at IS NULL
  AND rule.computed_at = (
      SELECT MAX(computed_at) FROM association_rules WHERE deleted_at IS NULL
  )
  AND rule.lift >= 1.0
ORDER BY rule.lift DESC
LIMIT 50;
