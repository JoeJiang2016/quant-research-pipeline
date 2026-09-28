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

Every dataset has a reproducible manifest containing its identity, version, source, symbol, timeframe, timezone, date range, row count, SHA-256, and price-adjustment status. Adjustment status is one of `raw`, `split_adjusted`, `total_return_adjusted`, or `unknown`; `unknown` is never treated as adjusted and is reported as a warning.

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

`backtest/datasets.py` is the canonical historical dataset contract. `backtest/data.py` remains only as a compatibility loader for historical six-column demos. The provider-agnostic importer copies the source into immutable `data/raw/`, applies only explicit column mappings and timezone configuration, validates without repairing data, writes UTC seven-column OHLCV to `data/processed/`, and records checksums, mapping, timezone, session policy, adjustment status, and quality observations in `data/manifests/`.

Alternative source columns must be mapped explicitly, for example `--map timestamp=Date --map open=Open`. Naive timestamps require `--timezone`; bars are never filled or forward-filled. Large gaps are reported without assuming weekends or holidays are missing market bars. No real-data provider has been selected or connected in Phase 3A.
