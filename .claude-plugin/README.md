# AI Hedge Fund — Claude Code Plugin

Slash commands and investor-persona subagents that drive the AI Hedge Fund multi-agent stock analysis tool from inside Claude Code.

## What's included

### Slash commands

| Command | Purpose |
|---|---|
| `/analyze TICKERS` | Run the full 19-agent workflow on one or more tickers and summarize signals + portfolio manager decision. |
| `/backtest TICKERS` | Run a historical backtest and summarize performance. |
| `/analysts` | List all available analyst agents (13 investor personas + 6 specialists). |
| `/compare TICKER1,TICKER2,...` | Side-by-side comparison across tickers with a relative ranking. |

All commands pass `--claude-subagent` so no LLM API key is needed.

### Subagents (investor personas)

Ask any of these directly: *"use the warren-buffett agent to analyze NVDA"*.

- `warren-buffett` — value investing, wide moats, fair-price wonderful businesses
- `charlie-munger` — inversion, mental models, avoid-stupidity
- `ben-graham` — defensive investor, margin of safety, net-nets
- `michael-burry` — contrarian deep value, balance-sheet forensics
- `bill-ackman` — activist catalyst-driven concentrated bets
- `cathie-wood` — disruptive innovation, 5-year growth
- `peter-lynch` — buy-what-you-know, ten-baggers, PEG
- `phil-fisher` — scuttlebutt, management quality, long-term growth
- `mohnish-pabrai` — Dhandho, heads-I-win-big asymmetry
- `nassim-taleb` — antifragility, tail risk, barbell strategy
- `stanley-druckenmiller` — macro-driven conviction bets
- `aswath-damodaran` — story + numbers, disciplined DCF
- `rakesh-jhunjhunwala` — emerging-market secular growth

## Install

### Option A — from the local filesystem (personal use)

```
/plugin marketplace add /home/albert/projects/custom-ai-hedge-fund/ai-hedge-fund
/plugin install ai-hedge-fund
```

### Option B — from GitHub (share with others)

Once pushed to GitHub:
```
/plugin marketplace add mooqoo/ai-hedge-fund
/plugin install ai-hedge-fund
```

## Prerequisites

- `poetry install` has been run in this directory
- Claude Code CLI is available on `$PATH` (the `--claude-subagent` flag shells out to `claude -p`)

## Disclaimer

Educational and research purposes only. Not investment advice.
