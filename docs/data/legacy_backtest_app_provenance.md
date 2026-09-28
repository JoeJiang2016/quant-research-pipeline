# Legacy backtest_app market-data provenance

Audit scope: read-only inspection of `C:\Projects\backtest_app` and its existing data files. No network lookup, redownload, data mutation, or strategy execution was performed.

## Evidence standard

- **Confirmed** means the value is directly established by surviving source code or file metadata.
- **Content evidence** means the files strongly support a lineage relationship, but the generating code is missing.
- **Unknown** means the surviving local evidence cannot establish the value.

## CSV acquisition and generation

The surviving CSV pipeline uses Yahoo Finance through the Python `yfinance` package. `data_download.py` imports `yfinance as yf` and calls:

```python
yf.download(ticker, start=start, end=end, interval=interval, progress=False)
```

Evidence: `C:\Projects\backtest_app\data_download.py:5` and `:55-63`.

The call does not set `auto_adjust`, `back_adjust`, `actions`, `prepost`, `repair`, or a timeout. No requirements, lockfile, environment file, or Git repository survives in the old project, so the yfinance version and the defaults active when each segment was downloaded are unknown.

The downloaded frame is flattened if it has MultiIndex columns, its index is reset and renamed to `Date`, converted with `pandas.to_datetime`, stripped of timezone information with `dt.tz_localize(None)`, indexed by `Date`, and supplemented with locally calculated SMA, EMA, RSI, MACD, signal, and ATR columns. Existing and new rows are concatenated, duplicate dates keep the last row, the full series is sorted, indicators are recalculated, and the result is written with `to_csv(index=False)`. Evidence: `C:\Projects\backtest_app\data_download.py:74-101` and `:104-147`.

The runner reads `C:\Projects\backtest_app\data\0.0 list.csv`, processes only `1d` in the surviving active loop, updates an existing file from its last date, or requests ten calendar years for a missing file. Evidence: `C:\Projects\backtest_app\data_download.py:151-198`.

An older archived implementation uses the same unspecific `yf.download(ticker, start, end, interval)` pattern and the same timezone removal and CSV write steps. Evidence: `C:\Projects\backtest_app\Z.Archive\indicator_calculator.py:7-14` and `:63-115`.

## Price adjustment and corporate actions

The exact OHLC adjustment semantics remain **unknown**. The active call omits both `auto_adjust` and `back_adjust`, while the yfinance version is not pinned. Therefore the default behavior in force at each download/update cannot be reconstructed from the project.

No surviving acquisition code explicitly downloads or stores splits, dividends, or actions, and no manual corporate-action adjustment is present. The absence of `Adj Close` in the CSV is not sufficient proof of one adjustment mode because the relevant yfinance defaults are version-dependent and unspecified.

The Parquet files contain an `Adj close` column, but for AAPL it is populated only for the 30 dates added after the CSV endpoint and equals `Close` on those rows. No surviving code defines this field, so its semantics remain unknown.

## CSV and Parquet lineage

No `to_parquet`, Parquet writer, or Parquet update path exists in the surviving old-project source. The Parquet generator is **unknown**.

File and content evidence establishes:

- all 496 Parquet files were created in one batch on 2025-11-29 between 15:28:33 and 15:31:04 local filesystem time;
- their symbol set exactly matches the 496 entries in `0.0 list.csv`;
- Parquet metadata records `pyarrow 14.0.2`, `pandas 2.1.4`, and a `Date` DatetimeIndex;
- AAPL CSV contains 2,616 rows through 2025-10-16, while AAPL Parquet contains the same 2,616 dates plus 30 dates through 2025-11-28;
- AAPL Open, High, Low, Close, and Volume are exactly equal across all overlapping dates;
- locally calculated indicator values differ only at floating serialization/recalculation scale.

This is strong content evidence that the AAPL Parquet incorporated the CSV history and appended a later update, but it does not prove the missing conversion/download command, its parameters, its adjustment settings, or which format was intended as source of truth. CSV and Parquet must not be treated as equivalent immutable versions.

## Timestamp and session semantics

For downloaded data the code resets the provider index, parses it as `Date`, explicitly removes timezone information, and writes it to CSV. AAPL is stored as date-only `YYYY-MM-DD`. The reliable canonical interpretation is therefore `timestamp_semantics: session_date`; no midnight instant or timezone should be reconstructed.

The original provider timezone, if any, was discarded. `source_timezone` remains null/unknown and `canonical_timezone` remains null/not applicable. The code does not set `prepost`; without a pinned yfinance version or explicit parameter, `session_policy` remains unknown.

## Symbol-list provenance and survivorship risk

`0.0 list.csv` contains 496 symbols and has filesystem creation/modified time 2025-10-18. No surviving code creates this file or identifies its upstream source. The name `SP500` in `watchlists.json` is not provenance evidence: `Z.Archive/update_sp500_watchlist.py` merely extracts tickers from existing filenames and labels that set `SP500` (`:8-33`).

The data directory contains 501 symbols. The five not present in `0.0 list.csv` are ANSS, HES, JNPR, KIM, and PARA; these also lack Parquet counterparts. This indicates retained older files, not a documented delisting or membership-history process.

The surviving downloader applies a single symbol-list snapshot to a ten-year request for missing files. There is no code for historical index membership, delisted securities, ticker changes, mergers, or acquisitions. The research universe therefore has **potentially high survivorship bias** and must not be described as point-in-time membership.

## Impact on `aapl_1d_legacy_v1`

The audit can reliably add the following provenance facts in a future immutable metadata revision:

- acquisition library: `yfinance`;
- API function: `yfinance.download`;
- explicit arguments: ticker, start, end, interval, and `progress=False`;
- legacy transformation pipeline and explicit timezone stripping;
- `timestamp_semantics: session_date` remains correct.

The following remain unknown and must not be filled by inference:

- yfinance package version;
- `price_adjustment` and exact OHLC adjustment semantics;
- `Adj close` semantics for the Parquet tail;
- `session_policy`;
- original provider timezone;
- symbol-list upstream source and point-in-time membership status;
- Parquet generation function and its download/adjustment parameters.

Do not overwrite the v1 manifest. The current dataset contract does not define an in-place metadata-only revision. If the confirmed provider evidence is adopted into the canonical manifest, create `aapl_1d_legacy_v2` as a separately approved immutable dataset version while keeping `price_adjustment: unknown`, `session_policy: unknown`, and null timezone fields. Until adjustment semantics are established, the dataset remains suitable for onboarding engineering validation, not performance research.
