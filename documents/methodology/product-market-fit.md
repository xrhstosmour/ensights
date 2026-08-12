# Product-market fit metrics, in plain words

The other notes in this folder explain the *code*. This one explains the
*ideas* behind the growth-accounting and business-metrics modules, in plain
language, with a link back to wherever each idea actually comes from. Read
this one if you want to remember, months later, why a metric exists and
what it is actually telling you, without re-deriving it from the SQL.

Every metric below is measured straight from the transaction record. None of
them assume a cost, a margin, or an acquisition budget the data does not
contain.

## Already implemented

### The six flows (growth accounting)

Revenue does not just "go up" or "go down". Every customer's revenue in a
period is exactly one of six things: brand **new**, **resurrected** (a
returning customer who had gone quiet), **retained** (repeat business),
**expansion** (an existing customer spending more), **contraction** (an
existing customer spending less, but not zero), or **churned** (gone to
zero). Splitting revenue this way answers a more useful question than "did
we grow": *why*.

- **Where it comes from**: Tribe Capital, [A Quantitative Approach to
  Product Market Fit](https://tribecap.co/essays/a-quantitative-approach-to-product-market-fit).
- **In the code**: `app/analysis/growth_accounting.py`, endpoint
  `/api/v1/growth-accounting`.

### Quick ratio

One number that says whether the business is growing or shrinking:
`(new + resurrected + expansion) / (churned + contraction)`. Above 1.0,
you're gaining more than you're losing. Below 1.0, you're not. It is
arithmetic, not a value judgement, there is no universal "good" quick
ratio, it depends on the business.

- **Where it comes from**: same Tribe Capital essay as above.
- **In the code**: `PeriodFlows.quick_ratio` in `growth_accounting.py`.

### Net churn rate

How much revenue was lost on net, as a share of last period's revenue:
`(churned + contraction - resurrected - expansion) / previous revenue`.
A **negative** net churn rate is a strong signal: it means the existing
customer base alone is growing the business, before counting a single new
customer.

- **Where it comes from**: Tribe Capital, same essay.
- **In the code**: `PeriodFlows.net_churn_rate`.

### Gross retention rate

The simplest of the three: how much of last period's revenue simply
repeated, `retained / previous revenue`. It ignores expansion on purpose,
so a store cannot hide a shrinking customer base behind a few customers who
spent a lot more.

- **Where it comes from**: Tribe Capital, same essay. The SaaS world calls
  the identical idea Gross Revenue Retention (GRR), see
  [ChartMogul's definition](https://chartmogul.com/saas-metrics/grr/) if
  that vocabulary is more familiar.
- **In the code**: `PeriodFlows.gross_retention_rate`.

### Revenue concentration and the Gini coefficient

What share of revenue comes from the top 10%, 20%, and 50% of customers,
and from the single biggest one, plus a Gini coefficient (0 = every
customer spends equally, 1 = one customer produces everything). A store
whose revenue is this concentrated behaves like a wholesaler with a few key
accounts, whatever it calls itself, and no growth rate alone reveals that.

- **Where it comes from**: Tribe Capital, same essay ("distribution of
  product-market fit"). The Gini coefficient itself predates the essay by a
  century: Corrado Gini, *Variabilità e Mutabilità* (1912), also cited in
  the thesis bibliography as `gini1912`.
- **In the code**: `concentration()` in `growth_accounting.py`.

### Cohort retention (logo retention)

Group customers by the month they first bought, then track what fraction
of each group is still buying in every later month. `period_index` counts
months since acquisition, 0 is the cohort's own month. This is "logo"
retention, it counts customers, not revenue.

- **Where it comes from**: the cohort half of the same Tribe Capital essay.
  Cohort analysis as a general technique is much older and is the
  centrepiece of David Skok's widely cited
  [SaaS Metrics 2.0](https://www.forentrepreneurs.com/saas-metrics-2/),
  which calls it "the single most important tool for understanding the
  health of your... business."
- **In the code**: `cohort_retention()` in
  `app/repositories/business_metrics_repository.py`, endpoint
  `/api/v1/business-metrics/cohort-retention`.

### RFM: recency, frequency, monetary value

For each customer: how long since their last order, how many orders total,
and how much they've spent. This is not a prediction of future value, it
is what has actually happened so far. It also happens to be exactly the
feature set the two-level clustering (see
[clustering.md](clustering.md)) segments customers on.

- **Where it comes from**: a much older lineage than the rest of this
  document, decades of direct-marketing practice, formalised in Arthur
  Middleton Hughes, *Strategic Database Marketing* (1994). Included here
  because it sits right next to the growth-accounting and cohort work in
  the business-metrics module, not because it's part of the Tribe Capital
  framework.
- **In the code**: `rfm()` in `business_metrics_repository.py`.

## New: cohort revenue and its shape

The logo-retention cohort grid above answers "how many customers came
back". It does not answer "did they spend more or less when they did", which
is the other half of the article's cohort section.

### Cohort revenue retention

Alongside `retention_rate` (customers), the cohort grid now also carries
`revenue_retention_rate`: this period's revenue from the cohort, divided by
what that same cohort produced in its own first month. 0.2 three months in
means the cohort is now spending a fifth of what it spent when it was
acquired.

- **Where it comes from**: Tribe Capital, "Revenue Retention" in the same
  cohort section.
- **In the code**: `cohort_retention()`, same endpoint as logo retention,
  the new columns just ride along.

### Cohort shape: super-linear, linear, sub-linear

Fit a trend line through a cohort's `revenue_retention_rate` over time
(excluding its own first month, which is always 1.0 by definition and says
nothing about a trend). The slope gets a label:

- **super-linear**: the slope is clearly positive, the cohort spends more
  the longer it sticks around. The strongest possible retention signal.
- **linear**: the slope is close enough to flat that it isn't a trend,
  spend holds roughly steady.
- **sub-linear**: the slope is clearly negative, spend fades over time.

A cohort needs at least two months of data after its own acquisition month
to fit a line at all, younger cohorts are left out of the result rather
than forced into a guess.

- **Where it comes from**: Tribe Capital, same essay, "super-linear /
  linear / sub-linear" is the article's own vocabulary.
- **In the code**: `app/analysis/cohort_shape.py`, endpoint
  `/api/v1/business-metrics/cohort-shape`.

## Considered, not implemented, and why

### Net revenue retention / gross revenue retention (NRR / GRR)

These are SaaS-world names for numbers this project already reports:
GRR is the same arithmetic as `gross_retention_rate`, NRR is the same
arithmetic as `1 + (expansion - contraction - churned + resurrected) /
previous revenue`, one algebraic step from the quick ratio and net churn
rate already implemented. Building a second module under different names
for the same math would add vocabulary, not information. See
[ChartMogul's NRR](https://chartmogul.com/saas-metrics/nrr/) and
[GRR](https://chartmogul.com/saas-metrics/grr/) pages if you want the
SaaS-native framing.

### Sean Ellis's 40% "very disappointed" survey

A well-known product-market-fit test: ask users "how would you feel if you
could no longer use this product", and if 40%+ say "very disappointed",
that's read as a strong PMF signal. Documented in Sean Ellis and Morgan
Brown's book *Hacking Growth* (2017). Deliberately not implemented here:
it needs real survey responses from real users, and this project has no
survey pipeline, only a transaction record. Faking survey data to compute
a survey-based metric would be worse than not having the metric.

## Where these numbers stop being trustworthy

None of the above needs a cost, a margin, or an acquisition budget, that
is what keeps it in this "measured" half of the codebase instead of the
"assumed" half (`app/analysis/profitability.py`, see
[profitability.md](profitability.md)). What they cannot tell you is
*whether* the growth is profitable, only whether it is happening and where
it is coming from.
