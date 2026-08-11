# Forecasting

Holt-Winters exponential smoothing, with a naive baseline and an honest
backtest.

## The baseline is the point

Every forecast reports a naive last-value baseline and a **skill score**: the
fractional improvement in MAE over it.

A model that cannot beat "tomorrow looks like today" has demonstrated nothing,
and a MAPE quoted without that comparison is an unfalsifiable number. The skill
score can be negative, and is reported as such. Do not remove it to make a
chart look better.

## The backtest excludes the holdout

The model fits only on data before the holdout, so the errors describe
genuinely unseen points. The final forecast is then refitted on the whole
series, because there is no reason to discard recent observations when
predicting forward.

## MAPE can be undefined

It is `None` when any held-out actual is zero. Substituting a small constant or
skipping those points would quietly flatter the model. MAE and RMSE remain
valid and are always reported.

## Net, not gross

The series forecast is net of refunds. Refunds are money that left again, and
forecasting gross would systematically overstate what the business keeps.

## Seasonality

A seasonal fit needs two complete cycles. With less history the model falls
back to trend-only rather than raising. `SEASONAL_PERIODS_BY_GRANULARITY` maps
bucket size to cycle length.

## Where it stops

Holt-Winters assumes a reasonably regular series. A merchant with sporadic
trading, or one whose history is dominated by a single promotional spike, will
get a poor skill score, which is the correct signal rather than a bug. Check
the skill score before quoting the forecast.
