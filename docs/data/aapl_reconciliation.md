# AAPL legacy versus controlled Yahoo reconciliation

This report reconciles the legacy AAPL daily CSV with two controlled Yahoo Finance downloads. It does not select a research adjustment policy and does not authorize strategy execution.

## FACT

Environment:

- Python 3.10.11
- yfinance 1.7.0
- pandas 2.3.3
- pyarrow 17.0.0 available but not used for the CSV downloads
- OS reported by Python: `Windows-10-10.0.26200-SP0`

Both downloads use `yfinance.download`, symbol `AAPL`, start-inclusive `2015-05-26`, end-exclusive `2025-10-17`, and `interval="1d"`. Both explicitly set `back_adjust=False`, `actions=True`, `prepost=False`, `repair=False`, `progress=False`, `threads=False`, `multi_level_index=False`, `ignore_tz=True`, `group_by="column"`, `keepna=False`, `rounding=False`, and `timeout=30`. The raw profile sets `auto_adjust=False`; the comparison profile sets `auto_adjust=True`. No `period` default is used.

The exact acquisition contract is `config/data_sources/yfinance_daily.json`. Downloaded source files remain ignored under `data/raw/`. The deterministic machine-readable comparison is `reports/data_reconciliation/aapl_legacy_vs_yfinance.json`.

All three inputs contain the same 2,616 session dates. The legacy source SHA-256 remained `93e2c2bd5468a534a71c35a797f58f2c9cc11b886c3a6b11801d905e09f3a1c5` before and after reconciliation.

Controlled source identities:

- raw SHA-256: `82b62ab9abd2a66af4e4597d15b1f27844c1822a2d5ea7adbb62ec899d2c8eb5`
- auto-adjusted SHA-256: `a77ae8e5dffd3e6991e88d5ad0d1b8463e05c59301c9371014f959f474d30d2f`

Comparison tolerance is absolute `1e-10` plus relative `1e-12` times the larger magnitude.

### Legacy versus raw

| Field | Exact | Within tolerance | Mismatch | Max absolute difference | Max relative difference |
|---|---:|---:|---:|---:|---:|
| Open | 55 | 57 | 2,559 | 3.60188661342397 | 10.4133% |
| High | 55 | 58 | 2,558 | 3.61209617529776 | 10.4133% |
| Low | 56 | 58 | 2,558 | 3.4633044601271 | 10.4133% |
| Close | 53 | 58 | 2,558 | 3.51260375976563 | 10.4133% |
| Volume | 2,563 | 2,563 | 53 | 4,616,300 | 2.0528% |

### Legacy versus provider auto-adjusted

| Field | Exact | Within tolerance | Mismatch | Max absolute difference | Max relative difference |
|---|---:|---:|---:|---:|---:|
| Open | 0 | 0 | 2,616 | 1.23884593187023 | 0.4811% |
| High | 0 | 0 | 2,616 | 1.24801050154485 | 0.4811% |
| Low | 0 | 0 | 2,616 | 1.23615895448628 | 0.4811% |
| Close | 0 | 0 | 2,616 | 1.24282836914065 | 0.4811% |
| Volume | 2,563 | 2,563 | 53 | 4,616,300 | 2.0528% |

The raw download preserved `Dividends` and `Stock Splits`. The comparison window contains 41 nonzero dividend events and one 4-for-1 split event on 2020-08-31. No `Capital Gains` column was returned.

## EVIDENCE

Across 10,464 OHLC cell comparisons, current auto-adjusted data is closer to legacy in 9,024 cases, while raw is closer in 1,440. Total absolute OHLC difference is 5,241.7051 for auto-adjusted versus 22,082.3870 for raw.

Of 42 five-session corporate-action windows, legacy is closer to current auto-adjusted data in 37. The 2020-08-31 split window is closer to auto-adjusted. Five recent dividend windows from 2024-08-12 through 2025-08-11 are closer to raw.

The current auto-adjusted series differs systematically from legacy rather than by floating noise, and both current downloads contain 53 Volume revisions. Examples with exact dates, fields, values, and differences are retained in the JSON report. This supports `possible provider revision`; it does not prove that legacy data is erroneous.

## INFERENCE

Legacy OHLC is substantially closer to provider-adjusted history than to the current raw series over most of the window and most corporate-action windows. However, the match is not consistent enough for the strict classification rule: only 86.24% of OHLC cells are closer to current auto-adjusted data, and five recent dividend windows are closer to raw.

The mixed result is compatible with an older provider-adjusted snapshot whose historical adjustment factors were subsequently revised, but the missing legacy yfinance version and unspecified `auto_adjust` prevent proving that explanation.

## UNKNOWN

The legacy adjustment classification remains `unknown`. This audit does not choose raw, split-adjusted, or total-return-adjusted data for research. It also does not establish whether every observed difference is caused by provider revision, a legacy package default, or a combination of both.

No strategy was run, no strategy version was created, and the legacy CSV was not modified.
