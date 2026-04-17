---
description: List all available analyst agents and their investing styles
---

List every analyst available in the AI hedge fund, grouped by type.

Arguments: $ARGUMENTS

---

Print a formatted list from `src/utils/analysts.py`. Do not run Python — read the file directly and render a table with columns: key, display name, description, style.

Group into two sections:
1. **Investor personas** — the 13 real-world-investor agents
2. **Specialist analysts** — technical, fundamentals, growth, sentiment, news_sentiment, valuation

At the end, remind the user they can:
- Run `/analyze <TICKER>` with `--analysts <key1,key2>` to use a subset
- Invoke a single-persona subagent, e.g. "ask the warren-buffett agent about NVDA"
