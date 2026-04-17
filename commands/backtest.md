---
description: Run a backtesting simulation on one or more tickers
argument-hint: TICKERS [--start DATE] [--end DATE] [--cash AMOUNT] [--analysts list]
---

Run the AI hedge fund backtester over a historical window.

Usage:
```
/backtest AAPL
/backtest AAPL,MSFT --start 2024-01-01 --end 2024-06-30
/backtest TSLA --cash 50000 --analysts warren_buffett,charlie_munger
```

Arguments: $ARGUMENTS

---

Parse `$ARGUMENTS`. Format: `TICKERS [--start DATE] [--end DATE] [--cash AMOUNT] [--analysts LIST]`.

Defaults:
- `--end`: today
- `--start`: 1 month before end date (backtester default)
- `--cash`: 100000
- `--analysts`: all (`--analysts-all`)

Run from the repo root:

```
poetry run python src/backtester.py --tickers <TICKERS> --start-date <START_DATE> --end-date <END_DATE> --initial-cash <CASH> <ANALYST_FLAG> --claude-subagent
```

Always pass `--claude-subagent` so no API key is required.

After the backtest completes, summarize:
1. Final portfolio value and total return %
2. Sharpe ratio and max drawdown if reported
3. Per-ticker P&L attribution
4. Any notable regime shifts or drawdown periods
