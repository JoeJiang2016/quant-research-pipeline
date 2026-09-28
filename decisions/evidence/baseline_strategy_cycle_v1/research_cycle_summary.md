# Baseline Strategy Cycle v1 — Evidence Summary

## FACT

### Frozen identities

| Strategy | Version | Fingerprint |
|---|---|---|
| breakout_trend_001 | 0.2.0 | `546931f68ca652e24e73da177b08084452ce3183f51d9b17446f39940c52c577` |
| pullback_trend_001 | 0.2.0 | `fa3d18708ee6605cbe644ee580b06d0edb872f454bcb06e04cfd922632db4ac3` |
| mean_reversion_001 | 0.2.0 | `fd60a50a0d1ac3b4181b48e3e07ec03325ded150f2294c4b5c037596fc0e2ab0` |

All baseline evaluations used Yahoo provider-adjusted daily data and canonical costs of $1 per fill plus 5 bps slippage, except the explicitly labeled AAPL cost-sensitivity scenarios.

### Evidence sequence

1. Phase 3C-2: AAPL fixed IS/OOS.
2. Phase 3C-3: AAPL cost sensitivity and seven fixed-parameter rolling OOS folds.
3. Phase 3D-1: fixed IS/OOS for the five-symbol pilot cohort.
4. Phase 3D-2: seven rolling OOS folds for the five-symbol pilot cohort.
5. Phase 3D-3: first performance evaluation of the mechanically selected, precommitted `us_equity_holdout_v1`; 28 symbols had full history and CTVA/SOLV remained recorded as insufficient-history.
6. Phase 3D-4: seven rolling OOS folds on the same 28 valid symbols after Phase 3D-3 results had been viewed. Strategy specifications, costs, cohort membership, and datasets remained frozen.

Phase 3D-3 was the pristine precommitted symbol-holdout evaluation at execution time. Phase 3D-4 has status `revealed_holdout_after_3d3` and is a separate secondary evidence layer. Fixed OOS and rolling OOS cells were not combined.

### Holdout facts

| Strategy | Fixed OOS pos/neg | Fixed median / 25th | Fixed median PF / Sharpe | Fixed worst DD / trades | Rolling pos/neg cells | Rolling median / 25th | Rolling median PF / Sharpe | Rolling worst DD / trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| breakout_trend_001 | 16/12 | 1.644% / -2.532% | 1.1662 / 0.2103 | 10.498% / 397 | 109/87 | 0.809% / -1.182% | 1.0618 / 0.2065 | 7.265% / 1,029 |
| pullback_trend_001 | 17/11 | 1.923% / -0.636% | 1.1234 / 0.2046 | 13.417% / 886 | 114/82 | 0.822% / -1.158% | 1.1472 / 0.2818 | 7.606% / 2,276 |
| mean_reversion_001 | 16/12 | 1.739% / -2.376% | 1.1726 / 0.2487 | 9.255% / 1,335 | 122/74 | 0.521% / -0.876% | 1.1960 / 0.2627 | 5.715% / 3,344 |

### Limitations

- Yahoo provider-adjusted daily data.
- Simplified $1/fill plus 5 bps execution model.
- No broker execution validation and no real-capital execution.
- The source universe is a modern symbol snapshot, not point-in-time constituent history.
- Survivorship bias and constituent-history bias remain.
- Symbols are correlated; folds are correlated through market time.
- Symbol/fold cells are not independent observations.
- No statistical-significance framework.
- No portfolio-level simulation.

## JUDGMENT

No Research Director decision is recorded in this evidence packet. The separate decision template remains unset. No strategy state transition is authorized by this document.
