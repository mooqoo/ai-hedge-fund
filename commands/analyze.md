---
description: Run AI hedge fund analysis on one or more tickers
argument-hint: TICKERS [--start DATE] [--end DATE] [--analysts list]
---

Run AI hedge fund analysis for the given ticker(s).

Usage:
```
/analyze TSLA
/analyze AAPL,MSFT,NVDA
/analyze TSLA --start 2026-01-01 --end 2026-04-17
/analyze TSLA --analysts warren_buffett,michael_burry
```

Arguments: $ARGUMENTS

---

Parse the arguments from `$ARGUMENTS`. Format: `TICKERS [--start START_DATE] [--end END_DATE] [--analysts ANALYST_LIST]`.

Defaults:
- `--end`: today
- `--start`: 3 months before end date
- `--analysts`: all (use `--analysts-all`)

Valid analyst keys: `aswath_damodaran`, `ben_graham`, `bill_ackman`, `cathie_wood`, `charlie_munger`, `michael_burry`, `mohnish_pabrai`, `nassim_taleb`, `peter_lynch`, `phil_fisher`, `rakesh_jhunjhunwala`, `stanley_druckenmiller`, `warren_buffett`, `technical_analyst`, `fundamentals_analyst`, `growth_analyst`, `news_sentiment_analyst`, `sentiment_analyst`, `valuation_analyst`.

Run from the repo root:

```
poetry run python src/main.py --tickers <TICKERS> --start-date <START_DATE> --end-date <END_DATE> <ANALYST_FLAG> --claude-subagent --show-reasoning
```

Where `<ANALYST_FLAG>` is `--analysts-all` (default) or `--analysts <comma-list>`.

Always pass `--claude-subagent` (no API key needed) and `--show-reasoning` (so the user sees per-agent reasoning).

After the command finishes, summarize:
1. For each ticker: overall signal (bullish / bearish / neutral) and the portfolio manager's trading decision
2. Notable disagreements between analysts
3. Portfolio manager's overall strategy (position sizing, risk flags)
