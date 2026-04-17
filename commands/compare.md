---
description: Compare two or more tickers side by side across all analysts
argument-hint: TICKER1,TICKER2,... [--analysts list]
---

Compare tickers head-to-head using the full hedge fund workflow, then synthesize a relative ranking.

Usage:
```
/compare AAPL,MSFT
/compare TSLA,RIVN,LCID --analysts cathie_wood,peter_lynch
```

Arguments: $ARGUMENTS

---

Parse `$ARGUMENTS`. Require at least two tickers. Format: `TICKERS [--analysts LIST]`.

Defaults:
- `--end`: today
- `--start`: 3 months before end date
- `--analysts`: all

Run from the repo root:

```
poetry run python src/main.py --tickers <TICKERS> --start-date <START_DATE> --end-date <END_DATE> <ANALYST_FLAG> --claude-subagent --show-reasoning
```

After the analysis, produce a **comparison table** with columns:
- Ticker
- Overall signal (bullish/bearish/neutral)
- Confidence
- Portfolio manager action (buy/sell/hold + size)
- Top bullish analyst
- Top bearish analyst

Then give a one-paragraph verdict on which ticker offers the best risk-adjusted opportunity *according to this run* (emphasize this is not investment advice).
