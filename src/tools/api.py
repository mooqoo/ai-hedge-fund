"""
api.py — yfinance-backed data layer (drop-in replacement for Financial Datasets API)

All public function signatures are identical to the original, so no agent code
needs to change.  Requires only: pip install yfinance

Data sources:
  - Prices, financials, metrics, news, insider trades → yfinance (Yahoo Finance)
  - No API key needed for any function
"""

import datetime
import logging
import math
from functools import lru_cache

import pandas as pd
import yfinance as yf

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    LineItem,
    LineItemResponse,
    Price,
    PriceResponse,
    InsiderTrade,
    InsiderTradeResponse,
    CompanyFactsResponse,
)

logger = logging.getLogger(__name__)
_cache = get_cache()


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe(value):
    """Return None for NaN / inf, otherwise the value."""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _row(df: pd.DataFrame, *names: str):
    """Return the first matching row from a DataFrame, or None."""
    for name in names:
        if name in df.index:
            return df.loc[name]
    return None


def _val(df: pd.DataFrame, names: list, col: int = 0):
    """Get a scalar float from a DataFrame by row names and column index."""
    if df is None or df.empty:
        return None
    row = _row(df, *names)
    if row is None or col >= len(row):
        return None
    v = row.iloc[col]
    return _safe(v) if pd.notna(v) else None


@lru_cache(maxsize=32)
def _yf(ticker: str) -> yf.Ticker:
    """Cached yfinance Ticker object."""
    return yf.Ticker(ticker)


def _info(ticker: str) -> dict:
    try:
        return _yf(ticker).info or {}
    except Exception as e:
        logger.warning("yfinance info failed for %s: %s", ticker, e)
        return {}


def _ratio(a, b_):
    """Safe division — returns None on zero / None."""
    if a is None or b_ is None or b_ == 0:
        return None
    return _safe(a / b_)


def _filter_cols(df: pd.DataFrame, end_date: str) -> pd.DataFrame:
    """Keep only columns (period dates) that are <= end_date."""
    if df is None or df.empty:
        return df
    valid = [c for c in df.columns if pd.to_datetime(c).strftime("%Y-%m-%d") <= end_date]
    return df[valid] if valid else df.iloc[:, :0]


# ──────────────────────────────────────────────────────────────────────────────
# Prices
# ──────────────────────────────────────────────────────────────────────────────

def get_prices(ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
    """Fetch daily OHLCV prices via yfinance."""
    cache_key = f"{ticker}_{start_date}_{end_date}"
    if cached := _cache.get_prices(cache_key):
        return [Price(**p) for p in cached]

    try:
        df = _yf(ticker).history(start=start_date, end=end_date, auto_adjust=True)
    except Exception as e:
        logger.warning("yfinance prices failed for %s: %s", ticker, e)
        return []

    if df is None or df.empty:
        return []

    prices = [
        Price(
            open=round(float(row["Open"]), 4),
            close=round(float(row["Close"]), 4),
            high=round(float(row["High"]), 4),
            low=round(float(row["Low"]), 4),
            volume=int(row["Volume"]),
            time=ts.strftime("%Y-%m-%d"),
        )
        for ts, row in df.iterrows()
    ]

    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
    return prices


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert a list of Price objects to a DataFrame."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    for col in ["open", "close", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


def get_price_data(ticker: str, start_date: str, end_date: str, api_key: str = None) -> pd.DataFrame:
    return prices_to_df(get_prices(ticker, start_date, end_date))


# ──────────────────────────────────────────────────────────────────────────────
# Financial metrics
# ──────────────────────────────────────────────────────────────────────────────

def _build_metrics(
    ticker: str,
    period_label: str,
    period_type: str,
    fin: pd.DataFrame,
    bal: pd.DataFrame,
    cf: pd.DataFrame,
    info: dict,
    col: int = 0,
) -> FinancialMetrics:
    """Compute one FinancialMetrics record from yfinance DataFrames at column index col."""

    def i(*n):      return _val(fin, list(n), col)
    def b(*n):      return _val(bal, list(n), col)
    def c(*n):      return _val(cf,  list(n), col)
    def i_p(*n):    return _val(fin, list(n), col + 1)  # prior period
    def b_p(*n):    return _val(bal, list(n), col + 1)

    # ── Core line items ──────────────────────────────────────────────────────
    revenue    = i("Total Revenue")
    gross      = i("Gross Profit")
    op_income  = i("Operating Income", "Total Operating Income As Reported")
    net_income = i("Net Income", "Net Income Common Stockholders")
    ebit       = i("EBIT", "Operating Income")
    ebitda     = i("EBITDA", "Normalized EBITDA")
    interest   = i("Interest Expense", "Interest Expense Non Operating")

    total_assets = b("Total Assets")
    total_liab   = b("Total Liabilities Net Minority Interest")
    equity       = b("Common Stock Equity", "Stockholders Equity", "Total Stockholder Equity")
    curr_assets  = b("Current Assets", "Total Current Assets")
    curr_liab    = b("Current Liabilities", "Total Current Liabilities")
    cash         = b("Cash And Cash Equivalents",
                     "Cash Cash Equivalents And Short Term Investments")
    total_debt   = b("Total Debt")
    inventory    = b("Inventory")

    op_cf  = c("Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex  = c("Capital Expenditure")         # negative in yfinance
    fcf    = c("Free Cash Flow")
    if fcf is None and op_cf is not None and capex is not None:
        fcf = op_cf + capex                   # capex is negative, so subtraction is correct

    # ── Market data (always current snapshot from info) ──────────────────────
    mkt_cap = _safe(info.get("marketCap"))
    shares  = _safe(info.get("sharesOutstanding"))
    ev      = _safe(info.get("enterpriseValue"))

    # ── Valuation ratios ─────────────────────────────────────────────────────
    pe        = (_ratio(mkt_cap, net_income) if net_income and net_income > 0
                 else _safe(info.get("trailingPE")))
    pb        = (_ratio(mkt_cap, equity) if equity and equity > 0
                 else _safe(info.get("priceToBook")))
    ps        = (_ratio(mkt_cap, revenue) if revenue and revenue > 0
                 else _safe(info.get("priceToSalesTrailing12Months")))
    ev_ebitda = (_ratio(ev, ebitda) if ebitda and ebitda > 0
                 else _safe(info.get("enterpriseToEbitda")))
    ev_rev    = (_ratio(ev, revenue) if revenue and revenue > 0
                 else _safe(info.get("enterpriseToRevenue")))
    fcf_yield = _ratio(fcf, mkt_cap)
    peg       = _safe(info.get("pegRatio"))

    # ── Profitability ─────────────────────────────────────────────────────────
    gross_margin = _ratio(gross, revenue)
    op_margin    = _ratio(op_income, revenue)
    net_margin   = _ratio(net_income, revenue)
    roe          = (_ratio(net_income, equity) if equity and equity > 0
                    else _safe(info.get("returnOnEquity")))
    roa          = (_ratio(net_income, total_assets) if total_assets
                    else _safe(info.get("returnOnAssets")))
    invested_cap = (equity + total_debt) if equity is not None and total_debt is not None else None
    roic         = _ratio(net_income, invested_cap)
    asset_turn   = _ratio(revenue, total_assets)

    # ── Liquidity / Leverage ──────────────────────────────────────────────────
    curr_ratio  = (_ratio(curr_assets, curr_liab) if curr_liab
                   else _safe(info.get("currentRatio")))
    quick_assets = (curr_assets - (inventory or 0)) if curr_assets is not None else None
    quick_ratio  = (_ratio(quick_assets, curr_liab) if curr_liab
                    else _safe(info.get("quickRatio")))
    cash_ratio   = _ratio(cash, curr_liab)
    op_cf_ratio  = _ratio(op_cf, curr_liab)

    de_ratio = (_ratio(total_debt, equity) if equity and equity > 0
                else _safe(info.get("debtToEquity")))
    # yfinance sometimes returns de_ratio as a percentage (e.g. 123.5 = 1.235x)
    if de_ratio is not None and de_ratio > 20:
        de_ratio = de_ratio / 100
    da_ratio     = _ratio(total_debt, total_assets)
    interest_cov = (_ratio(ebit, abs(interest))
                    if interest is not None and interest != 0 else None)

    payout = _safe(info.get("payoutRatio"))
    eps    = _safe(info.get("trailingEps")) or _ratio(net_income, shares)
    bvps   = _safe(info.get("bookValue"))   or _ratio(equity, shares)
    fcfps  = _ratio(fcf, shares)

    # ── Growth (period-over-period where prior data exists) ───────────────────
    rev_prev = i_p("Total Revenue")
    ni_prev  = i_p("Net Income", "Net Income Common Stockholders")
    bv_prev  = b_p("Common Stock Equity", "Stockholders Equity", "Total Stockholder Equity")

    rev_growth = (_ratio(revenue - rev_prev, abs(rev_prev))
                  if revenue is not None and rev_prev
                  else _safe(info.get("revenueGrowth")))
    ni_growth  = (_ratio(net_income - ni_prev, abs(ni_prev))
                  if net_income is not None and ni_prev and ni_prev != 0
                  else _safe(info.get("earningsGrowth")))
    bv_growth  = (_ratio(equity - bv_prev, abs(bv_prev))
                  if equity is not None and bv_prev and bv_prev != 0
                  else None)

    # ── Additional growth fields ─────────────────────────────────────────────
    eps_prev = _safe(info.get("trailingEps"))  # fallback
    eps_p    = i_p("Basic EPS", "Diluted EPS")
    eps_cur  = i("Basic EPS", "Diluted EPS") or eps
    eps_growth = (_ratio(eps_cur - eps_p, abs(eps_p))
                  if eps_cur is not None and eps_p and eps_p != 0
                  else _safe(info.get("earningsQuarterlyGrowth")))

    fcf_prev = None
    if col + 1 < (cf.shape[1] if cf is not None and not cf.empty else 0):
        fcf_prev_raw = _val(cf, ["Free Cash Flow"], col + 1)
        if fcf_prev_raw is None:
            ocf_p = _val(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], col + 1)
            cap_p = _val(cf, ["Capital Expenditure"], col + 1)
            if ocf_p is not None and cap_p is not None:
                fcf_prev_raw = ocf_p + cap_p
        fcf_prev = fcf_prev_raw
    fcf_growth = (_ratio(fcf - fcf_prev, abs(fcf_prev))
                  if fcf is not None and fcf_prev and fcf_prev != 0
                  else None)

    op_income_prev = i_p("Operating Income", "Total Operating Income As Reported")
    op_income_growth = (_ratio(op_income - op_income_prev, abs(op_income_prev))
                        if op_income is not None and op_income_prev and op_income_prev != 0
                        else None)

    ebitda_prev = i_p("EBITDA", "Normalized EBITDA")
    ebitda_growth_val = (_ratio(ebitda - ebitda_prev, abs(ebitda_prev))
                         if ebitda is not None and ebitda_prev and ebitda_prev != 0
                         else None)

    return FinancialMetrics(
        ticker=ticker,
        report_period=period_label,
        period=period_type,
        currency="USD",
        market_cap=mkt_cap,
        enterprise_value=ev,
        price_to_earnings_ratio=pe,
        price_to_book_ratio=pb,
        price_to_sales_ratio=ps,
        enterprise_value_to_ebitda_ratio=ev_ebitda,
        enterprise_value_to_revenue_ratio=ev_rev,
        free_cash_flow_yield=fcf_yield,
        peg_ratio=peg,
        gross_margin=gross_margin,
        operating_margin=op_margin,
        net_margin=net_margin,
        return_on_equity=roe,
        return_on_assets=roa,
        return_on_invested_capital=roic,
        asset_turnover=asset_turn,
        inventory_turnover=None,
        receivables_turnover=None,
        days_sales_outstanding=None,
        operating_cycle=None,
        working_capital_turnover=None,
        current_ratio=curr_ratio,
        quick_ratio=quick_ratio,
        cash_ratio=cash_ratio,
        operating_cash_flow_ratio=op_cf_ratio,
        debt_to_equity=de_ratio,
        debt_to_assets=da_ratio,
        interest_coverage=interest_cov,
        revenue_growth=rev_growth,
        earnings_growth=ni_growth,
        book_value_growth=bv_growth,
        earnings_per_share_growth=eps_growth,
        free_cash_flow_growth=fcf_growth,
        operating_income_growth=op_income_growth,
        ebitda_growth=ebitda_growth_val,
        payout_ratio=payout,
        earnings_per_share=eps,
        book_value_per_share=bvps,
        free_cash_flow_per_share=fcfps,
    )


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    """Compute financial metrics from yfinance data."""
    cache_key = f"{ticker}_{period}_{end_date}_{limit}"
    if cached := _cache.get_financial_metrics(cache_key):
        return [FinancialMetrics(**m) for m in cached]

    try:
        t    = _yf(ticker)
        info = t.info or {}

        if period == "ttm":
            # Generate rolling TTM snapshots from quarterly data.
            # Each snapshot sums 4 consecutive quarters for flow statements
            # and uses the most recent quarter's balance sheet.
            q_fin = _filter_cols(t.quarterly_income_stmt, end_date)
            q_bal = _filter_cols(t.quarterly_balance_sheet, end_date)
            q_cf  = _filter_cols(t.quarterly_cashflow, end_date)

            n_quarters = min(
                len(q_fin.columns) if q_fin is not None and not q_fin.empty else 0,
                len(q_cf.columns)  if q_cf  is not None and not q_cf.empty  else 0,
            )
            # Number of rolling TTM windows we can build (need 4 quarters per window)
            n_windows = max(0, n_quarters - 3)
            n_windows = min(n_windows, limit)

            if n_windows == 0 and n_quarters >= 1:
                # Not enough for a full TTM, but return what we can with available quarters
                n_windows = 1

            result = []
            for w in range(n_windows):
                # Window w: sum quarters [w, w+4) for flow stmts, use quarter w for balance sheet
                end_q = min(w + 4, n_quarters)

                def _sum_window(df, start=w, stop=end_q):
                    if df is None or df.empty or start >= len(df.columns):
                        return pd.DataFrame()
                    stop = min(stop, len(df.columns))
                    label = pd.to_datetime(df.columns[start]).strftime("%Y-%m-%d")
                    return df.iloc[:, start:stop].sum(axis=1).to_frame(name=label)

                def _snap(df, idx=w):
                    if df is None or df.empty or idx >= len(df.columns):
                        return pd.DataFrame()
                    label = pd.to_datetime(df.columns[idx]).strftime("%Y-%m-%d")
                    return df.iloc[:, idx:idx+1].rename(columns={df.columns[idx]: label})

                fin_w = _sum_window(q_fin)
                cf_w  = _sum_window(q_cf)
                bal_w = _snap(q_bal)

                # Period label = end of the most recent quarter in this window
                if q_fin is not None and not q_fin.empty and w < len(q_fin.columns):
                    period_label = pd.to_datetime(q_fin.columns[w]).strftime("%Y-%m-%d")
                else:
                    period_label = end_date

                # Build metrics — for growth calc we need adjacent columns,
                # so we concatenate adjacent window data
                if w + 1 < n_windows:
                    fin_next = _sum_window(q_fin, w + 1, min(w + 5, n_quarters))
                    cf_next  = _sum_window(q_cf,  w + 1, min(w + 5, n_quarters))
                    bal_next = _snap(q_bal, w + 1)
                    fin_pair = pd.concat([fin_w, fin_next], axis=1)
                    cf_pair  = pd.concat([cf_w, cf_next], axis=1)
                    bal_pair = pd.concat([bal_w, bal_next], axis=1)
                else:
                    fin_pair = fin_w
                    cf_pair  = cf_w
                    bal_pair = bal_w

                result.append(_build_metrics(ticker, period_label, "ttm",
                                             fin_pair, bal_pair, cf_pair, info, 0))

        else:
            # Annual statements — up to 4 years from yfinance
            fin = _filter_cols(t.income_stmt, end_date)
            bal = _filter_cols(t.balance_sheet, end_date)
            cf  = _filter_cols(t.cashflow, end_date)

            if fin is None or fin.empty:
                return []

            n = min(limit, len(fin.columns))
            result = []
            for i in range(n):
                period_label = pd.to_datetime(fin.columns[i]).strftime("%Y-%m-%d")
                result.append(
                    _build_metrics(ticker, period_label, "annual",
                                   fin, bal, cf, info, i)
                )

    except Exception as e:
        logger.warning("get_financial_metrics failed for %s: %s", ticker, e)
        return []

    if not result:
        return []

    _cache.set_financial_metrics(cache_key, [m.model_dump() for m in result])
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Line items
# ──────────────────────────────────────────────────────────────────────────────

# Maps Financial Datasets field names → (statement, [yfinance row labels])
_LINE_ITEM_MAP: dict[str, tuple[str, list[str]]] = {
    # ── Income statement ──────────────────────────────────────────────────────
    "revenue":                               ("income",   ["Total Revenue"]),
    "gross_profit":                          ("income",   ["Gross Profit"]),
    "operating_income":                      ("income",   ["Operating Income",
                                                           "Total Operating Income As Reported"]),
    "ebit":                                  ("income",   ["EBIT", "Operating Income"]),
    "ebitda":                                ("income",   ["EBITDA", "Normalized EBITDA"]),
    "net_income":                            ("income",   ["Net Income",
                                                           "Net Income Common Stockholders"]),
    "earnings_per_share":                    ("income",   ["Basic EPS", "Diluted EPS"]),
    "interest_expense":                      ("income",   ["Interest Expense",
                                                           "Interest Expense Non Operating"]),
    "depreciation_and_amortization":         ("income",   ["Reconciled Depreciation"]),
    # ── Balance sheet ────────────────────────────────────────────────────────
    "total_assets":                          ("balance",  ["Total Assets"]),
    "total_liabilities":                     ("balance",  ["Total Liabilities Net Minority Interest"]),
    "shareholders_equity":                   ("balance",  ["Common Stock Equity",
                                                           "Stockholders Equity",
                                                           "Total Stockholder Equity"]),
    "current_assets":                        ("balance",  ["Current Assets",
                                                           "Total Current Assets"]),
    "current_liabilities":                   ("balance",  ["Current Liabilities",
                                                           "Total Current Liabilities"]),
    "cash_and_equivalents":                  ("balance",  ["Cash And Cash Equivalents",
                                                           "Cash Cash Equivalents And Short Term Investments"]),
    "total_debt":                            ("balance",  ["Total Debt"]),
    "long_term_debt":                        ("balance",  ["Long Term Debt",
                                                           "Long Term Debt And Capital Lease Obligation"]),
    "goodwill":                              ("balance",  ["Goodwill",
                                                           "Goodwill And Other Intangible Assets"]),
    "inventory":                             ("balance",  ["Inventory"]),
    # ── Cash flow ────────────────────────────────────────────────────────────
    "operating_cash_flow":                   ("cashflow", ["Operating Cash Flow",
                                                           "Cash Flow From Continuing Operating Activities"]),
    "capital_expenditure":                   ("cashflow", ["Capital Expenditure"]),
    "free_cash_flow":                        ("cashflow", ["Free Cash Flow"]),
    "dividends_and_other_cash_distributions": ("cashflow", ["Common Stock Dividend Paid",
                                                            "Cash Dividends Paid",
                                                            "Payment Of Dividends"]),
    "issuance_or_purchase_of_equity_shares":  ("cashflow", ["Repurchase Of Capital Stock",
                                                            "Common Stock Repurchase"]),
    # ── From info (same value across all periods) ────────────────────────────
    "outstanding_shares":                    ("info",     ["sharesOutstanding"]),
    "book_value_per_share":                  ("info",     ["bookValue"]),
}


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    """Fetch specific financial line items from yfinance statements."""
    try:
        t    = _yf(ticker)
        info = t.info or {}

        if period in ("ttm", "quarterly"):
            fin = _filter_cols(t.quarterly_income_stmt, end_date)
            bal = _filter_cols(t.quarterly_balance_sheet, end_date)
            cf  = _filter_cols(t.quarterly_cashflow, end_date)
            period_type = period
        else:
            fin = _filter_cols(t.income_stmt, end_date)
            bal = _filter_cols(t.balance_sheet, end_date)
            cf  = _filter_cols(t.cashflow, end_date)
            period_type = "annual"

        # Number of available periods
        n_periods = max(
            len(fin.columns) if fin is not None and not fin.empty else 0,
            len(bal.columns) if bal is not None and not bal.empty else 0,
            len(cf.columns)  if cf  is not None and not cf.empty  else 0,
        )
        n_periods = min(n_periods, limit)

        if n_periods == 0:
            return []

        results = []
        for col_idx in range(n_periods):
            # Determine the period label from whichever DataFrame has that column
            period_label = None
            for df_ref in [fin, bal, cf]:
                if df_ref is not None and not df_ref.empty and col_idx < len(df_ref.columns):
                    period_label = pd.to_datetime(df_ref.columns[col_idx]).strftime("%Y-%m-%d")
                    break
            if period_label is None:
                continue

            fields: dict = {
                "ticker":        ticker,
                "report_period": period_label,
                "period":        period_type,
                "currency":      "USD",
            }

            for item in line_items:
                if item not in _LINE_ITEM_MAP:
                    fields[item] = None
                    continue

                stmt, yf_names = _LINE_ITEM_MAP[item]

                if stmt == "info":
                    raw = info.get(yf_names[0])
                    fields[item] = _safe(raw) if raw is not None else None
                elif stmt == "income":
                    fields[item] = _val(fin, yf_names, col_idx)
                elif stmt == "balance":
                    fields[item] = _val(bal, yf_names, col_idx)
                elif stmt == "cashflow":
                    fields[item] = _val(cf, yf_names, col_idx)

            # Derive free_cash_flow if missing
            if "free_cash_flow" in line_items and not fields.get("free_cash_flow"):
                ocf   = fields.get("operating_cash_flow") or _val(cf, ["Operating Cash Flow",
                    "Cash Flow From Continuing Operating Activities"], col_idx)
                cap   = fields.get("capital_expenditure") or _val(cf, ["Capital Expenditure"], col_idx)
                if ocf is not None and cap is not None:
                    fields["free_cash_flow"] = ocf + cap  # capex is negative

            # Derive outstanding_shares from info if not set
            if "outstanding_shares" in line_items and not fields.get("outstanding_shares"):
                fields["outstanding_shares"] = _safe(info.get("sharesOutstanding"))

            # Derive depreciation from cashflow if income statement didn't have it
            if "depreciation_and_amortization" in line_items and not fields.get("depreciation_and_amortization"):
                fields["depreciation_and_amortization"] = _val(
                    cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"], col_idx
                )

            results.append(LineItem(**fields))

    except Exception as e:
        logger.warning("search_line_items failed for %s: %s", ticker, e)
        return []

    return results[:limit]


# ──────────────────────────────────────────────────────────────────────────────
# Insider trades
# ──────────────────────────────────────────────────────────────────────────────

def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    """Fetch insider transactions via yfinance."""
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    if cached := _cache.get_insider_trades(cache_key):
        return [InsiderTrade(**t) for t in cached]

    try:
        df = _yf(ticker).insider_transactions
    except Exception as e:
        logger.warning("yfinance insider_transactions failed for %s: %s", ticker, e)
        return []

    if df is None or df.empty:
        return []

    trades = []
    for _, row in df.iterrows():
        # Date parsing — yfinance uses "Start Date" column
        date_raw = row.get("Start Date") or row.get("Date") or row.get("startDate")
        if date_raw is None:
            continue
        try:
            filing_date = pd.to_datetime(date_raw).strftime("%Y-%m-%d")
        except Exception:
            continue

        if filing_date > end_date:
            continue
        if start_date and filing_date < start_date:
            continue

        try:
            shares_val = _safe(row.get("Shares") or row.get("shares") or 0)
        except Exception:
            shares_val = None

        try:
            value_raw = str(row.get("Value") or row.get("value") or "0").replace(",", "")
            value_val = _safe(float(value_raw))
        except Exception:
            value_val = None

        trades.append(InsiderTrade(
            ticker=ticker,
            issuer=ticker,
            name=str(row.get("Insider") or row.get("name") or ""),
            title=str(row.get("Position") or row.get("title") or ""),
            is_board_director=None,
            transaction_date=filing_date,
            transaction_shares=shares_val,
            transaction_price_per_share=None,
            transaction_value=value_val,
            shares_owned_before_transaction=None,
            shares_owned_after_transaction=None,
            security_title=str(row.get("Text") or row.get("Transaction") or ""),
            filing_date=filing_date,
        ))

        if len(trades) >= limit:
            break

    if not trades:
        return []

    _cache.set_insider_trades(cache_key, [t.model_dump() for t in trades])
    return trades


# ──────────────────────────────────────────────────────────────────────────────
# Company news
# ──────────────────────────────────────────────────────────────────────────────

def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    """Fetch company news via yfinance."""
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    if cached := _cache.get_company_news(cache_key):
        return [CompanyNews(**n) for n in cached]

    try:
        raw_news = _yf(ticker).news or []
    except Exception as e:
        logger.warning("yfinance news failed for %s: %s", ticker, e)
        return []

    news_items = []
    for item in raw_news:
        # yfinance ≥0.2 nests metadata under "content"
        content = item.get("content", {}) if isinstance(item, dict) else {}

        title = content.get("title") or item.get("title", "No title")

        # Source / publisher
        provider = content.get("provider") or {}
        if isinstance(provider, dict):
            source = provider.get("displayName") or item.get("publisher", "Unknown")
        else:
            source = item.get("publisher", "Unknown")

        # Published date
        pub_time = content.get("pubDate") or content.get("publishedAt")
        if not pub_time:
            ts_raw = item.get("providerPublishTime")
            if ts_raw:
                try:
                    pub_time = datetime.datetime.fromtimestamp(int(ts_raw)).strftime("%Y-%m-%d")
                except Exception:
                    pub_time = end_date
            else:
                pub_time = end_date
        else:
            try:
                pub_time = pd.to_datetime(pub_time).strftime("%Y-%m-%d")
            except Exception:
                pub_time = end_date

        if pub_time > end_date:
            continue
        if start_date and pub_time < start_date:
            continue

        # URL
        canon = content.get("canonicalUrl") or {}
        url   = (canon.get("url") if isinstance(canon, dict) else None) or item.get("link", "")

        news_items.append(CompanyNews(
            ticker=ticker,
            title=title,
            author=None,
            source=source,
            date=pub_time,
            url=url,
            sentiment=None,
        ))

        if len(news_items) >= limit:
            break

    if news_items:
        _cache.set_company_news(cache_key, [n.model_dump() for n in news_items])
    return news_items


# ──────────────────────────────────────────────────────────────────────────────
# Market cap
# ──────────────────────────────────────────────────────────────────────────────

def get_market_cap(ticker: str, end_date: str, api_key: str = None) -> float | None:
    """Get market cap from yfinance info."""
    info = _info(ticker)

    mc = _safe(info.get("marketCap"))
    if mc:
        return mc

    # Fallback: price × shares outstanding
    shares = _safe(info.get("sharesOutstanding"))
    price  = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))
    if shares and price:
        return _safe(shares * price)

    # Last resort: pull from the first financial metrics record
    metrics = get_financial_metrics(ticker, end_date)
    if metrics and metrics[0].market_cap:
        return metrics[0].market_cap

    return None
