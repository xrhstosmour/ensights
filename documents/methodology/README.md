# Methodology

One note per analytical module: what it computes, the judgement calls behind
it, and where it stops being trustworthy.

These are for whoever extends the code, so they cover the reasoning that the
docstrings are too small to hold and the thesis states too formally to be
useful at a keyboard. The Greek manuscript in `thesis/` is the academic
account; this is the working one.

| Note | Module |
| --- | --- |
| [Ingestion](ingestion.md) | `app/ingestion/`, `app/services/ingestion_service.py` |
| [Descriptive analytics](descriptive-analytics.md) | `app/repositories/analytics_repository.py` |
| [Business metrics](business-metrics.md) | `app/repositories/business_metrics_repository.py` |
| [Growth accounting](growth-accounting.md) | `app/analysis/growth_accounting.py` |
| [Frequent itemsets](frequent-itemsets.md) | `app/analysis/frequent_itemsets.py` |
| [Clustering](clustering.md) | `app/analysis/clustering.py` |
| [Forecasting](forecasting.md) | `app/analysis/forecasting.py` |
| [Profitability](profitability.md) | `app/analysis/profitability.py` |

## The rule that runs through all of them

Measured and assumed never mix. Everything except `profitability.py` is
computed from the transaction record alone. `profitability.py` requires
assumptions the data cannot supply, so it is quarantined: separate module,
separate endpoints, a disclaimer on every response, and no dashboard card.

When adding a module, decide which side of that line it sits on before writing
any code, and make the answer obvious from the outside.
