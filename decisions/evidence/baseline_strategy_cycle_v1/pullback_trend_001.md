# pullback_trend_001 v0.2.0 — Evidence Card

## Identity

- Fingerprint: `fa3d18708ee6605cbe644ee580b06d0edb872f454bcb06e04cfd922632db4ac3`
- Original hypothesis: long-only EMA trend condition, deterministic ATR-distance pullback to the fast EMA, and close recovery confirmation; execution is next-bar open, with a 2-bar ATR stop and target at 2× ATR.

## Facts

| Evidence layer | Positive / negative / zero | Median return | Median PF | Median Sharpe | Worst DD | Trades |
|---|---:|---:|---:|---:|---:|---:|
| AAPL fixed OOS | n/a | 14.058% | 2.1648 | 1.3802 | 1.999% | 36 |
| AAPL rolling OOS | 7 / 0 / 0 folds | 2.979% | 1.4487 | not in source summary | 5.185% | 103 |
| Pilot fixed OOS | 5 / 0 / 0 symbols | 8.728% | 1.6978 | 0.8857 | 7.869% | 186 |
| Pilot rolling OOS | 24 / 11 / 0 cells | 2.593% | 1.3913 | 0.6907 | 7.878% | 460 |
| Holdout fixed OOS | 17 / 11 / 0 symbols | 1.923% | 1.1234 | 0.2046 | 13.417% | 886 |
| Holdout rolling OOS | 114 / 82 / 0 cells | 0.822% | 1.1472 | 0.2818 | 7.606% | 2,276 |

Holdout fixed OOS 25th-percentile return was -0.636%. Holdout rolling OOS 25th-percentile return was -1.158%.

## AAPL cost-sensitivity facts

| Costs | Return | PF | Sharpe | DD | Trades |
|---|---:|---:|---:|---:|---:|
| $0/fill, 0 bps | 14.678% | 2.2285 | 1.4352 | 1.988% | 36 |
| $1/fill, 5 bps | 14.058% | 2.1648 | 1.3802 | 1.999% | 36 |
| $1/fill, 10 bps | 13.521% | 2.1086 | 1.3312 | 2.026% | 36 |
| $2/fill, 20 bps | 9.163% | 1.6933 | 0.9637 | 2.215% | 35 |

## Known limitations

Yahoo provider-adjusted daily data; simplified execution costs; no broker execution validation; modern symbol snapshot; survivorship and constituent-history bias; correlated symbols and time folds; cells are not independent observations; no statistical-significance framework; no portfolio-level simulation; no real-capital execution. Phase 3D-4 followed disclosure of Phase 3D-3 results.
