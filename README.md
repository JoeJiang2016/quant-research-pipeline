# Quant research and deterministic backtesting — Phase 2A

This repository is a research-only foundation: `Strategy Candidate → Deterministic Backtest → Structured Result`. It does not connect to TradeStation, place orders, call OpenAI, or use an LLM in calculations.

## Architecture

Candidate YAML in `strategies/candidates/` is validated, then evaluated by the deterministic bar engine against versioned CSV OHLCV data. Results go to `reports/<strategy_id>/` as a trade log and a result document. The engine records a close-time signal and only fills it at the next bar's open; this prevents look-ahead bias. A same-bar stop and target collision resolves conservatively to the stop.

`schemas/` is the portable contract for candidates, result records, and future risk policy. `backtest.splits.split_bars` exposes deterministic, non-overlapping `IN_SAMPLE` and `OUT_OF_SAMPLE` slices; it deliberately contains no optimizer or walk-forward tuning. Result creation validates the final result and every trade-log record against `schemas/backtest_result.schema.json` before writing either report.

## Run the demo

Install the two development dependencies, then run:

```powershell
python scripts/run_backtest.py strategies/breakout_001/v1.0.0/strategy.yaml
```

It uses 20 completed bars of history: `close > prior 20-bar high` signals a long order for next-open execution, with a 2-ATR stop, 4-ATR target, and 1% equity risk sizing.

## Add a strategy

Copy the demo YAML, use only the schema-defined fields and place matching OHLCV data at `data/<dataset_id>.csv`. Required columns are `timestamp,open,high,low,close,volume`. Preserve the causal execution contract (`bar_close` signal, `next_bar_open` fill). Every report stores exact parameters, engine version, data file identity plus SHA-256 checksum, timestamp, execution assumptions, and Git commit when available.

## Test

```powershell
pytest -q
```

Tests cover strategy/result schema validation, invalid parameters, causal execution, sizing, exits, conservative stop handling, fees/slippage, duplicate prevention, malformed or missing OHLCV data, insufficient history, zero trades, accounting consistency, and non-overlapping IS/OOS slices.

## Meta Muse Integration

Meta Muse has one canonical repository entry point: [`integration/muse_entry.json`](integration/muse_entry.json). In the future, provide Muse only the stable GitHub link to this repository and it can resolve the candidate schema, example, output directory, required `status: candidate`, and its limits from that file. Muse is limited to `Research / Hypothesis -> candidate strategy`; its candidate then proceeds to schema validation and deterministic backtesting. It cannot validate, approve, promote, alter results, or issue trading instructions.

## Future interfaces (not implemented)

Meta Muse can write candidate YAML only. A future ChatGPT review can consume immutable result JSON and produce a separately schema-validated risk-policy proposal. A future execution adapter can consume an approved, signed strategy/result artifact; it must remain outside this research engine and retain independent hard risk controls.

## Historical data and walk-forward framework

Phase 2A adds a fail-fast historical data layer for CSV and optional Parquet data. Input bars must include `timestamp, open, high, low, close, volume, symbol`; timestamps require an explicit timezone, symbols and timeframes are mandatory metadata, and malformed OHLC, duplicate/non-monotonic timestamps, NaN/infinite values, and negative volume are rejected. Gaps are reported explicitly rather than repaired.

Every dataset has a reproducible manifest containing its identity, version, source, symbol, timeframe, timezone, date range, row count, SHA-256, and price-adjustment status. Adjustment status is one of `raw`, `split_adjusted`, `total_return_adjusted`, `provider_adjusted`, or `unknown`; `provider_adjusted` requires an explicit adjustment method, while `unknown` is never treated as adjusted and is reported as a warning.

Walk-forward windows are deterministic rolling or expanding (`--anchored`) boundaries. The runner uses fixed candidate parameters: there is no optimizer, parameter selection, strategy promotion, or use of future/OOS bars in a training window. Headline output consists only of OOS folds and a stitched OOS equity curve. Cost sensitivity reports fixed base, 1.5x/2x slippage, and 2x commission scenarios; it does not choose a winner.

Run the offline synthetic demo (it creates clearly labeled deterministic synthetic data locally):

```powershell
python scripts/run_walk_forward.py --strategy strategies/breakout_001/v1.0.0/strategy.yaml --dataset data/processed/demo.csv
```

It writes `manifest.json`, per-fold reports, `walk_forward_summary.json`, `stitched_oos_equity.json`, and `cost_sensitivity.json` below `reports/walk_forward/demo_20bar_breakout/`. Meta Muse remains a future candidate producer only; TradeStation and all paper/live trading remain unconnected.

## Strategy lifecycle

`strategy.yaml` is the canonical machine-readable source of every trading behavior parameter. Versions live at `strategies/<strategy_id>/vMAJOR.MINOR.PATCH/strategy.yaml`; historical version files are immutable and must be rerun from their own path. Create a new version instead of editing an existing version.

`strategy_fingerprint` is a deterministic SHA-256 of behavior fields (universe, timeframe, entry, exits, risk, pyramiding, sizing, session, execution costs and assumptions). Descriptions and other metadata do not change it. Every single-run result records the strategy id, version, fingerprint, parameter snapshot, code commit, and data checksum.

The migrated demo is `strategies/breakout_001/v1.0.0/strategy.yaml`:

```powershell
python scripts/run_backtest.py strategies/breakout_001/v1.0.0/strategy.yaml
python scripts/run_walk_forward.py --strategy strategies/breakout_001/v1.0.0/strategy.yaml
python scripts/compare_strategy_versions.py strategies/breakout_001/v1.0.0/strategy.yaml strategies/breakout_001/v1.1.0/strategy.yaml
```

Future Muse candidates may add a new strategy family and new candidate version only; they cannot overwrite historical versions, results, approvals, or produce trading instructions.

## Strategy Candidate Pool

Batch 1 contains three canonical research candidates: `breakout_trend_001 v0.1.0`, `pullback_trend_001 v0.1.0`, and `mean_reversion_001 v0.1.0`. `strategies/candidates.json` is metadata-only; all behavior remains in each immutable `strategy.yaml`.

Run the complete pool without ranking or selection:

```powershell
python scripts/run_candidate_batch.py
```

The batch writes a provenance manifest, one standard result per candidate, and a factual `candidate_summary.json` below `reports/candidates/<batch_id>/`. The candidates currently use different deterministic smoke-test datasets, so `comparable_performance` is false. These synthetic results validate implementation, engine integration, reproducibility, and provenance only; they do not demonstrate market efficacy and must not be used to select or promote a strategy.

## Research Experiment Layer

A strategy, dataset, and experiment are separate immutable inputs:

```text
Immutable Strategy Version
+ Immutable Dataset Version
+ Research Experiment Spec
→ Deterministic Research Run
```

Strategy YAML contains trading behavior. Dataset manifests contain data identity and provenance. Experiment YAML selects one dataset, immutable strategy versions, research/IS/OOS windows, walk-forward settings, and cost scenarios. Dataset and experiment changes therefore do not change a strategy behavior fingerprint; experiments have their own fingerprint.

Run the sample shared-dataset experiment after importing its deterministic fixture:

```powershell
python scripts/import_dataset.py --input data/demo_ohlcv.csv --dataset-id phase3a_shared_demo --version 1 --symbol DEMO --timeframe 1d --timezone UTC --source synthetic/integration --price-adjustment unknown --session-policy all_sessions --asset-class synthetic
python scripts/run_research_experiment.py research/experiments/batch1_baseline.yaml
```

All candidates in one experiment use the same processed checksum, research window, timeframe, and baseline cost scenario before `comparable_performance` may be true. This permits factual side-by-side research output but does not rank, select, or promote strategies.

## Real Data Intake

`backtest/datasets.py` is the canonical historical dataset contract. `backtest/data.py` remains only as a compatibility loader for historical six-column demos. The provider-agnostic importer copies the source into immutable `data/raw/`, applies only explicit column mappings and timestamp semantics, validates without repairing data, writes canonical seven-column OHLCV to `data/processed/`, and records checksums, mapping, timezone, session policy, adjustment status, and quality observations in `data/manifests/`.

Alternative source columns must be mapped explicitly, for example `--map timestamp=Date --map open=Open`. Naive instant timestamps require `--timezone`; explicitly declared daily/weekly session dates follow the rules below. Bars are never filled or forward-filled. Large gaps are reported without assuming weekends or holidays are missing market bars. No real-data provider has been selected or connected in Phase 3A.

### Daily/Weekly Session-Date Semantics

Daily and weekly bars may explicitly use `timestamp_semantics: session_date`. Their canonical timestamp is the unchanged `YYYY-MM-DD` exchange-session label; the importer does not fabricate midnight, UTC, or an exchange timezone. Such manifests record `source_timezone` and `canonical_timezone` as null when the source does not establish them. Intraday bars continue to require timezone-aware timestamps, or an explicit source timezone that can be normalized to UTC.

Datasets with unknown price-adjustment semantics may be onboarded for provenance, normalization, and engineering validation. They must not be treated as research-grade performance datasets until their adjustment semantics are established. Date gaps are informational without an exchange calendar: the importer does not forward-fill, insert bars, or assume that a calendar gap represents missing trading data.

## Yahoo research-data contract

`config/data_sources/yfinance_daily.json` is the explicit acquisition contract for the first controlled AAPL daily dataset. `scripts/download_yfinance_dataset.py` requests two immutable Yahoo/yfinance 1.7.0 views: provider evidence (`auto_adjust=false`, actions preserved) and a research price view (`auto_adjust=true`). It delegates normalization, validation, quality reporting, and dataset manifests to `backtest/datasets.py`; no provider-specific second loader exists. The adjusted view is conservatively classified as `provider_adjusted` with `adjustment_method: yfinance_auto_adjust`. See `docs/data/yfinance_adjustment_semantics.md` for the local source audit.

The historical Yahoo files under `C:\Projects\backtest_app\data` remain historical reconciliation and engineering smoke-test evidence only. Their yfinance version and adjustment semantics are `UNKNOWN`; they are not inputs to this acquisition pipeline and are not a canonical research baseline. They are neither changed nor deleted by this repository.

## Asset Eligibility / Universe Semantics

A strategy universe defines which assets are eligible; it does not bind the strategy to the symbol selected by a research experiment. Historical strategies retain the exact-symbol list form (`universe: [DEMO]`). New strategy versions may use the machine-readable asset-class form, for example `universe: {mode: asset_class, asset_class: equity, country: US}`. Compatibility is checked centrally against the dataset manifest's symbol or explicit `asset_class` and `country`, plus timeframe, and returns explainable reasons for every mismatch.

This lets one immutable `US equity / 1d` strategy version be evaluated by separate experiments selecting AAPL, MSFT, NVDA, or another explicitly classified dataset. It avoids creating ticker-specific copies of identical strategy behavior. Eligibility alone is not evidence of performance and does not run or approve a backtest.

## Fixed IS/OOS evaluation boundaries

Research experiments execute `evaluation.in_sample` and `evaluation.out_of_sample` as two independent runs rather than descriptive metadata. Both use `boundary_mode: flat_start`: initial equity is reset, and positions, pending entries, and pending exits never cross the boundary. Bars before a segment remain readable only as causal indicator warmup; the engine does not traverse them for signals, fills, trades, or P&L. A signal before OOS therefore cannot fill on its first bar. Equity curves and trade logs contain active evaluation bars only.

IS and OOS summaries are factual and separate. Comparability is established within a segment only when dataset checksum, timeframe, dates, and effective canonical strategy costs match. IS and OOS are never treated as one performance sample, and the baseline output does not rank, select, approve, or modify strategies.

## Fixed-parameter robustness

Robustness analysis applies explicit cost overrides at runtime without changing canonical strategy YAML or fingerprints. Rolling OOS folds use fixed parameters, 756 warmup bars, 252 test bars, a 252-bar step, independent flat-start state, and exclude an incomplete final fold. Stitched curves are labeled as chronological aggregation of independent fold curves, not a continuous reinvested portfolio.

Engine 1.3.0 defines exposure as evaluation bars during which a position was actually open for any part of the bar, divided by total evaluation bars. Earlier reports incorrectly inferred exposure from equity differing from initial equity; their exposure field is unreliable, while their other metrics remain reproducible. Results now also record whether a position remains open at the evaluation end and its marked-to-final-close unrealized P&L; no synthetic closing trade is inserted.

## Cross-symbol pilot validation

The fixed pilot cohort is AAPL, MSFT, GOOGL, AMZN, and NVDA. Each symbol has an independent immutable acquisition contract, provider raw evidence, provider-adjusted canonical research view, dataset manifest, and fixed-date experiment using the same three v0.2.0 strategy fingerprints and canonical costs. `scripts/run_cross_symbol_validation.py` only validates inputs, invokes the existing experiment runner, checks AAPL reproduction, and aggregates factual IS/OOS records; it does not implement trading logic or modify parameters.

This cohort was specified before observing its cross-symbol results, but it consists of modern large-cap survivors and has material selection and survivorship limitations. Its output is an engineering and fixed-parameter generalization pilot, not evidence that the strategies apply to the full US equity universe and not an investment or production recommendation.
