# breakout_trend_001 v0.2.0 — Evidence Card

## Identity

- Fingerprint: `546931f68ca652e24e73da177b08084452ce3183f51d9b17446f39940c52c577`
- Original hypothesis: a long entry is signaled when the current close exceeds the highest high of the previous 20 bars; execution is next-bar open, with a 14-bar ATR stop at 2× ATR and target at 4× ATR.

## Facts

| Evidence layer | Positive / negative / zero | Median return | Median PF | Median Sharpe | Worst DD | Trades |
|---|---:|---:|---:|---:|---:|---:|
| AAPL fixed OOS | n/a | 14.429% | 3.2067 | 1.5389 | 3.123% | 16 |
| AAPL rolling OOS | 7 / 0 / 0 folds | 4.893% | 2.5362 | not in source summary | 3.244% | 46 |
| Pilot fixed OOS | 5 / 0 / 0 symbols | 9.668% | 2.1643 | 0.8750 | 6.649% | 87 |
| Pilot rolling OOS | 26 / 9 / 0 cells | 2.279% | 1.4436 | 0.5750 | 7.278% | 224 |
| Holdout fixed OOS | 16 / 12 / 0 symbols | 1.644% | 1.1662 | 0.2103 | 10.498% | 397 |
| Holdout rolling OOS | 109 / 87 / 0 cells | 0.809% | 1.0618 | 0.2065 | 7.265% | 1,029 |

Holdout fixed OOS 25th-percentile return was -2.532%. Holdout rolling OOS 25th-percentile return was -1.182%.

## AAPL cost-sensitivity facts

| Costs | Return | PF | Sharpe | DD | Trades |
|---|---:|---:|---:|---:|---:|
| $0/fill, 0 bps | 14.711% | 3.2867 | 1.5755 | 3.102% | 16 |
| $1/fill, 5 bps | 14.429% | 3.2067 | 1.5389 | 3.123% | 16 |
| $1/fill, 10 bps | 14.117% | 3.1276 | 1.5113 | 3.137% | 16 |
| $2/fill, 20 bps | 13.567% | 2.9877 | 1.4571 | 3.164% | 16 |

## Known limitations

Yahoo provider-adjusted daily data; simplified execution costs; no broker execution validation; modern symbol snapshot; survivorship and constituent-history bias; correlated symbols and time folds; cells are not independent observations; no statistical-significance framework; no portfolio-level simulation; no real-capital execution. Phase 3D-4 followed disclosure of Phase 3D-3 results.
