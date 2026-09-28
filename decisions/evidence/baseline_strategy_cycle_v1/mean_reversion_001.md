# mean_reversion_001 v0.2.0 — Evidence Card

## Identity

- Fingerprint: `fd60a50a0d1ac3b4181b48e3e07ec03325ded150f2294c4b5c037596fc0e2ab0`
- Original hypothesis: a long entry is signaled when a five-bar rolling z-score is at or below -1.5; exit occurs when z-score reaches 0 or the 2-bar ATR stop is reached; execution is next-bar open.

## Facts

| Evidence layer | Positive / negative / zero | Median return | Median PF | Median Sharpe | Worst DD | Trades |
|---|---:|---:|---:|---:|---:|---:|
| AAPL fixed OOS | n/a | 1.256% | 1.1000 | 0.1822 | 5.072% | 45 |
| AAPL rolling OOS | 6 / 1 / 0 folds | 2.981% | 2.1014 | not in source summary | 5.066% | 113 |
| Pilot fixed OOS | 5 / 0 / 0 symbols | 6.202% | 1.9506 | 0.9070 | 5.072% | 213 |
| Pilot rolling OOS | 28 / 7 / 0 cells | 1.884% | 1.6149 | 0.7569 | 5.066% | 565 |
| Holdout fixed OOS | 16 / 12 / 0 symbols | 1.739% | 1.1726 | 0.2487 | 9.255% | 1,335 |
| Holdout rolling OOS | 122 / 74 / 0 cells | 0.521% | 1.1960 | 0.2627 | 5.715% | 3,344 |

Holdout fixed OOS 25th-percentile return was -2.376%. Holdout rolling OOS 25th-percentile return was -0.876%.

## AAPL cost-sensitivity facts

| Costs | Return | PF | Sharpe | DD | Trades |
|---|---:|---:|---:|---:|---:|
| $0/fill, 0 bps | 2.308% | 1.1874 | 0.3226 | 4.884% | 45 |
| $1/fill, 5 bps | 1.256% | 1.1000 | 0.1822 | 5.072% | 45 |
| $1/fill, 10 bps | 0.306% | 1.0240 | 0.0545 | 5.277% | 45 |
| $2/fill, 20 bps | -1.629% | 0.8770 | -0.2068 | 5.802% | 45 |

## Known limitations

Yahoo provider-adjusted daily data; simplified execution costs; no broker execution validation; modern symbol snapshot; survivorship and constituent-history bias; correlated symbols and time folds; cells are not independent observations; no statistical-significance framework; no portfolio-level simulation; no real-capital execution. Phase 3D-4 followed disclosure of Phase 3D-3 results.
