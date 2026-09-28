# Quant research and deterministic backtesting — Phase 1

This repository is a research-only foundation: `Strategy Candidate → Deterministic Backtest → Structured Result`. It does not connect to TradeStation, place orders, call OpenAI, or use an LLM in calculations.

## Architecture

Candidate YAML in `strategies/candidates/` is validated, then evaluated by the deterministic bar engine against versioned CSV OHLCV data. Results go to `reports/<strategy_id>/` as a trade log and a result document. The engine records a close-time signal and only fills it at the next bar's open; this prevents look-ahead bias. A same-bar stop and target collision resolves conservatively to the stop.

`schemas/` is the portable contract for candidates, result records, and future risk policy. `backtest.splits.split_bars` exposes deterministic, non-overlapping `IN_SAMPLE` and `OUT_OF_SAMPLE` slices; it deliberately contains no optimizer or walk-forward tuning. Result creation validates the final result and every trade-log record against `schemas/backtest_result.schema.json` before writing either report.

## Run the demo

Install the two development dependencies, then run:

```powershell
python scripts/run_backtest.py strategies/candidates/demo_breakout.yaml
```

It uses 20 completed bars of history: `close > prior 20-bar high` signals a long order for next-open execution, with a 2-ATR stop, 4-ATR target, and 1% equity risk sizing.

## Add a strategy

Copy the demo YAML, use only the schema-defined fields and place matching OHLCV data at `data/<dataset_id>.csv`. Required columns are `timestamp,open,high,low,close,volume`. Preserve the causal execution contract (`bar_close` signal, `next_bar_open` fill). Every report stores exact parameters, engine version, data file identity plus SHA-256 checksum, timestamp, execution assumptions, and Git commit when available.

## Test

```powershell
pytest -q
```

Tests cover strategy/result schema validation, invalid parameters, causal execution, sizing, exits, conservative stop handling, fees/slippage, duplicate prevention, malformed or missing OHLCV data, insufficient history, zero trades, accounting consistency, and non-overlapping IS/OOS slices.

## Future interfaces (not implemented)

Meta Muse can write candidate YAML only. A future ChatGPT review can consume immutable result JSON and produce a separately schema-validated risk-policy proposal. A future execution adapter can consume an approved, signed strategy/result artifact; it must remain outside this research engine and retain independent hard risk controls.
