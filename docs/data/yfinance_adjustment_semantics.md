# yfinance 1.7.0 adjustment semantics

This audit is based on the locally installed, pinned `yfinance==1.7.0` source. It does not infer the meaning of old files and does not use the legacy AAPL file as an input.

## Local implementation evidence

- Source: `.deps/yfinance-1.7.0/yfinance/utils.py`
- Function: `auto_adjust(data)` (starts at line 506 in the audited installation)
- Caller: `.deps/yfinance-1.7.0/yfinance/scrapers/history.py`, where `auto_adjust=True` calls `utils.auto_adjust(df)` after Yahoo quote/action parsing and repair stages.

The function computes `ratio = Adj Close / Close`. It multiplies `Open`, `High`, and `Low` by that ratio, removes the original `Open`, `High`, `Low`, and `Close`, then renames the adjusted OHLC fields so that `Adj Close` becomes canonical `Close`. It returns the surviving columns in their original order.

`Volume` is not multiplied by the ratio. The history caller later fills missing Volume values with zero and casts them to an integer; this is representation handling, not price adjustment. With `actions=True`, `Dividends`, `Stock Splits`, and `Capital Gains` (when supplied) remain separate provider evidence columns because the caller only drops them when `actions=False`.

## Classification decision

The local code proves that yfinance's adjusted OHLC is derived from Yahoo's `Adj Close` factor. It does not, on its own, establish a complete contractual definition of every upstream Yahoo `Adj Close` value or prove that every value is a total-return series incorporating both splits and dividends. Therefore the canonical research view is classified as:

- `price_adjustment = provider_adjusted`
- `adjustment_method = yfinance_auto_adjust`
- `auto_adjust = true`

The provider evidence view is classified as `price_adjustment = raw` with `auto_adjust=false`, `back_adjust=false`, and `actions=true`. “Raw” here means the explicit yfinance provider view, not an assertion about undocumented upstream transformations.

## Reproducibility boundary

The acquisition contract pins yfinance 1.7.0 and pandas 2.3.3, records every material `yfinance.download` argument, and retains both provider views with distinct checksums. Corporate-action columns are retained in the raw evidence artifact. The adjusted canonical dataset links back to that acquisition ID, acquisition manifest, provider raw path, and provider raw checksum.
