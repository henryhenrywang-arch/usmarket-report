#!/usr/bin/env python3
"""Build data/latest.json (and an archived copy under data/history/)
for the "每日市場觀察" static report.

Data sources (all free, no key required, except the optional AI commentary):
  - Yahoo Finance (yfinance)        indices, VIX, commodities, DXY, fed funds futures
  - FRED graph CSV endpoint         Treasury par yields, CPI, initial claims, Fed target range
  - Anthropic API (optional)        one short paragraph of commentary per section

If ANTHROPIC_API_KEY is not set, the script still runs and fills in
template-based (non-AI) commentary so the site never breaks.
"""

import io
import json
import os
import sys
from datetime import datetime, timezone, date

import pandas as pd
import requests
import yfinance as yf

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

# ---- static calendar: update once a year from federalreserve.gov -----------
FOMC_MEETINGS_2026 = [
    "2026-01-27", "2026-01-28",
    "2026-03-17", "2026-03-18",
    "2026-04-28", "2026-04-29",
    "2026-06-16", "2026-06-17",
    "2026-07-28", "2026-07-29",
    "2026-09-15", "2026-09-16",
    "2026-10-27", "2026-10-28",
    "2026-12-08", "2026-12-09",
]
FOMC_BLACKOUT_DAYS_BEFORE = 10  # Fed's own convention is roughly this

# ---------------------------------------------------------------------------


def fred_series(series_id):
    """Return a pandas Series indexed by date for a FRED series, no API key needed."""
    url = FRED_CSV.format(sid=series_id)
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), na_values=["."])
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna().set_index("date")["value"]
    return df


def pct(new, old):
    if new is None or old is None or old == 0:
        return None
    return round((new / old - 1) * 100, 2)


def bp(new, old):
    if new is None or old is None:
        return None
    return round((new - old) * 100, 1)


def clean(x, d=2):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return round(f, d)


def close_series(raw, sym):
    """Safely pull a 1-D Close series for one ticker out of a yf.download()
    result, no matter whether pandas gave back a Series or (due to a partial
    download failure / duplicate column) a DataFrame."""
    try:
        s = raw["Close"][sym]
    except Exception:
        return None
    if isinstance(s, pd.DataFrame):
        if s.shape[1] == 0:
            return None
        s = s.iloc[:, 0]
    s = s.dropna()
    return s if len(s) >= 2 else None


# ---------------------------- indices & vix ---------------------------------

def build_indices():
    tickers = {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq 綜合",
        "^DJI": "道瓊工業",
        "^SOX": "費城半導體",
    }
    raw = yf.download(list(tickers.keys()), period="3mo", interval="1d",
                       auto_adjust=True, progress=False, group_by="column")
    out = []
    for sym, name in tickers.items():
        s = close_series(raw, sym)
        if s is None:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        w1 = float(s.iloc[-6]) if len(s) > 5 else None
        m1 = float(s.iloc[-22]) if len(s) > 21 else None
        out.append({
            "symbol": sym, "name": name,
            "close": clean(last), "chg": clean(last - prev), "chg_pct": pct(last, prev),
            "w1": clean(w1), "w1_pct": pct(last, w1),
            "m1": clean(m1), "m1_pct": pct(last, m1),
            "asof": s.index[-1].strftime("%Y-%m-%d"),
        })

    vix = yf.download("^VIX", period="1mo", interval="1d", auto_adjust=True, progress=False)
    vix_note = None
    v_last = v_prev = None
    if not vix.empty and len(vix) > 1:
        s = vix["Close"]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        s = s.dropna()
        v_last, v_prev = float(s.iloc[-1]), float(s.iloc[-2])
        chg_pct = pct(v_last, v_prev)
        streak_high = (s.tail(10) > 17).sum()
        vix_note = f"較前一交易日 {v_prev:.2f} {'上升' if v_last>v_prev else '下降'}約 {abs(chg_pct):.1f}%"
        if v_last > 17 and v_prev <= 17:
            vix_note += "，為近期首度收在 17 以上"
    return out, {
        "close": clean(v_last), "chg_pct": pct(v_last, v_prev), "note": vix_note,
    }


# ---------------------------- treasury yields -------------------------------

def build_yields():
    tenors = {"2年期": "DGS2", "5年期": "DGS5", "10年期": "DGS10", "30年期": "DGS30"}
    rows = []
    latest = {}
    for label, sid in tenors.items():
        try:
            s = fred_series(sid)
        except Exception as e:
            print(f"FRED fetch failed for {sid}: {e}", file=sys.stderr)
            continue
        if len(s) < 2:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        w1 = float(s.iloc[-6]) if len(s) > 5 else None
        m1 = float(s.iloc[-22]) if len(s) > 21 else None
        latest[label] = last
        rows.append({
            "tenor": label, "yield": clean(last), "prior": clean(prev),
            "chg_bp": bp(last, prev),
            "w1": clean(w1), "w1_chg_bp": bp(last, w1),
            "m1": clean(m1), "m1_chg_bp": bp(last, m1),
            "asof": s.index[-1].strftime("%Y-%m-%d"),
        })

    spreads = {}
    if "2年期" in latest and "10年期" in latest:
        spreads["2s10s"] = clean((latest["10年期"] - latest["2年期"]) * 100, 1)
    if "10年期" in latest and "30年期" in latest:
        spreads["30s10s"] = clean((latest["30年期"] - latest["10年期"]) * 100, 1)
    return rows, spreads


# ---------------------------- commodities & fx -------------------------------

def build_commodities():
    tickers = {
        "CL=F": ("WTI 原油（期貨結算）", "美元/桶"),
        "BZ=F": ("Brent 原油（期貨結算）", "美元/桶"),
        "GC=F": ("黃金（期貨）", "美元/盎司"),
        "DX-Y.NYB": ("美元指數 DXY", None),
    }
    raw = yf.download(list(tickers.keys()), period="5d", interval="1d",
                       auto_adjust=True, progress=False, group_by="column")
    out = []
    for sym, (name, unit) in tickers.items():
        s = close_series(raw, sym)
        if s is None:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        out.append({
            "symbol": sym, "name": name, "unit": unit,
            "value": clean(last), "chg_pct": pct(last, prev),
            "asof": s.index[-1].strftime("%Y-%m-%d"),
        })
    return out


# ---------------------------- CPI & claims -----------------------------------

def build_cpi():
    headline = fred_series("CPIAUCSL")
    core = fred_series("CPILFESL")

    def yoy_mom(series):
        last = series.iloc[-1]
        mom = pct(last, series.iloc[-2])
        yoy = pct(last, series.iloc[-13]) if len(series) > 12 else None
        prev_yoy = pct(series.iloc[-2], series.iloc[-14]) if len(series) > 13 else None
        prev_mom = pct(series.iloc[-2], series.iloc[-3]) if len(series) > 2 else None
        return yoy, prev_yoy, mom, prev_mom, series.index[-1]

    h_yoy, h_yoy_prev, h_mom, h_mom_prev, h_date = yoy_mom(headline)
    c_yoy, c_yoy_prev, c_mom, c_mom_prev, _ = yoy_mom(core)

    return {
        "period": h_date.strftime("%Y-%m"),
        "yoy": h_yoy, "yoy_prev": h_yoy_prev,
        "mom": h_mom, "mom_prev": h_mom_prev,
        "core_yoy": c_yoy, "core_yoy_prev": c_yoy_prev,
        "core_mom": c_mom, "core_mom_prev": c_mom_prev,
    }


def build_claims():
    s = fred_series("ICSA")
    last = s.iloc[-1]
    prev = s.iloc[-2]
    return {
        "value_k": clean(last / 1000, 1),
        "prior_k": clean(prev / 1000, 1),
        "week_of": s.index[-1].strftime("%Y-%m-%d"),
    }


# ---------------------------- fed funds futures proxy ------------------------

def build_fedwatch():
    """Rough probability of a 25bp move, inferred from 30-day Fed Funds futures.
    This is an approximation of the CME methodology, NOT official CME FedWatch
    data (that feed isn't publicly accessible without a license)."""
    try:
        upper = fred_series("DFEDTARU").iloc[-1]
        lower = fred_series("DFEDTARL").iloc[-1]
        target_mid = (upper + lower) / 2
    except Exception:
        return None

    try:
        fut = yf.download("ZQ=F", period="5d", interval="1d", auto_adjust=True, progress=False)
        price = float(fut["Close"].dropna().iloc[-1])
    except Exception:
        return None

    implied = 100 - price
    hike_prob = (implied - lower) / 0.25 * 100
    hike_prob = max(0.0, min(100.0, hike_prob))

    next_meeting = None
    today = date.today()
    for d in FOMC_MEETINGS_2026:
        if datetime.strptime(d, "%Y-%m-%d").date() >= today:
            next_meeting = d
            break

    return {
        "meeting_date": next_meeting,
        "hold_prob": clean(100 - hike_prob, 1),
        "move_prob": clean(hike_prob, 1),
        "target_range": f"{lower:.2f}%–{upper:.2f}%",
        "methodology_note": "依 30 天期聯邦基金期貨定價推算，非 CME FedWatch 官方數據，僅供參考。",
    }


def build_calendar():
    today = date.today()
    upcoming = [d for d in FOMC_MEETINGS_2026 if datetime.strptime(d, "%Y-%m-%d").date() >= today]
    events = []
    if upcoming:
        events.append({"date": upcoming[0], "desc": "FOMC 會議日"})
        blackout_start = datetime.strptime(upcoming[0], "%Y-%m-%d").date()
        events.append({"date": str(blackout_start), "desc": "FOMC 靜默期前後，官員談話減少"})
    return events


# ---------------------------- optional AI commentary --------------------------

def ai_commentary(payload):
    """Ask Claude for a short, plain-language note per section. Falls back to
    empty strings (template layer in the frontend covers the numbers regardless)
    if no API key is configured."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {}

    prompt = (
        "你是一位撰寫機構每日市場觀察報告的分析師。"
        "根據以下 JSON 數據，為每個區塊寫 1 句（30 字以內）繁體中文重點解讀，"
        "語氣中性、不給投資建議。只輸出 JSON，鍵為 "
        "indices, yields, commodities, cpi, claims, fedwatch，值為字串。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
        text = text.strip().strip("`").removeprefix("json").strip()
        return json.loads(text)
    except Exception as e:
        print(f"AI commentary skipped: {e}", file=sys.stderr)
        return {}


# ---------------------------------- main --------------------------------------

def main():
    indices, vix = build_indices()
    yields, spreads = build_yields()
    commodities = build_commodities()
    cpi = build_cpi()
    claims = build_claims()
    fedwatch = build_fedwatch()
    calendar = build_calendar()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "report_date": date.today().strftime("%Y-%m-%d"),
        "indices": indices,
        "vix": vix,
        "yields": yields,
        "spreads": spreads,
        "commodities": commodities,
        "cpi": cpi,
        "claims": claims,
        "fedwatch": fedwatch,
        "calendar": calendar,
        "sources": [
            {"label": "U.S. Treasury Daily Par Yield Curve", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"},
            {"label": "FRED (CPI / claims / Fed target range)", "url": "https://fred.stlouisfed.org/"},
            {"label": "Yahoo Finance (指數、商品、期貨)", "url": "https://finance.yahoo.com/"},
        ],
        "disclaimer": "本報告為公開市場數據之彙整與觀察，不構成投資建議，不含買賣建議、配置比重或目標價。",
    }

    report["commentary"] = ai_commentary({
        "indices": indices, "yields": yields, "commodities": commodities,
        "cpi": cpi, "claims": claims, "fedwatch": fedwatch,
    })

    os.makedirs("data/history", exist_ok=True)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    with open(f"data/history/{report['report_date']}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    index_path = "data/history/index.json"
    dates = []
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            dates = json.load(f)
    if report["report_date"] not in dates:
        dates.append(report["report_date"])
    dates = sorted(set(dates))
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(dates, f, ensure_ascii=False, indent=1)

    print("Done:", report["report_date"])


if __name__ == "__main__":
    main()
