# Descriptive analytics

Answers the seven questions the business actually asked. All SQL, no Python
aggregation: the datasets run to millions of rows and grouping belongs in the
database.

## Decisions worth knowing

**Rankings are by revenue, not units.** A cheap high-volume line and an
expensive low-volume one answer different questions, and marketing spend
follows value.

**Region comes from the order, not the customer.** Where a sale happened is a
property of that sale. The denormalised `Order.region_id` also keeps results
correct if a buyer's region is later corrected, and keeps the most frequent
query in the project off a join.

**Price bands use the line's own price.** A product that moved between bands
over time is counted where it actually sold, not where its current price would
put it.

**Both partitions sum to total revenue.** Price bands are open-ended at the
top; a product is attributed to the first characteristic it matches. Neither
double counts, and the tests assert both sum back to the same total. If you
add a band or a characteristic, keep that property.

## The product characteristics are a stated limitation

Online Retail II has no structured category, only free-text descriptions, so
characteristics are keyword-derived in `PRODUCT_CHARACTERISTICS`.

The tags are only as good as that vocabulary. Products matching nothing are
reported as `uncategorised` rather than dropped, and **the share of revenue
landing there is the honest measure of how well the rules work**. Watch it.

A source with real categories should feed them through the adapter and bypass
this entirely.
