import ccxt
import pandas as pd
import numpy as np
import requests
import time
import json
import os
from datetime import datetime, timezone

# ══════════════════════════════════════════════
#  CONFIG — EMA FLOW XAU/USD
# ══════════════════════════════════════════════
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1478745804167446578/QeTmCPBkKV7exHZNx2aB4SWK3nDSuq1FD12Mt1-rXVFit48nPu8oqleawZuQEv_Gjwar"

EMA_FAST  = 20
EMA_SLOW  = 50
ATR_LEN   = 14
ZONE_MULT = 0.25
COOLDOWN  = 6
SL_USD    = 1.00
TP_USD    = 2.00

SESSIONS = [
    {"nom": "LONDON",   "debut": 7,  "fin": 10},
    {"nom": "NEW YORK", "debut": 13, "fin": 17},
]

last_signal_bar  = -999
bar_index        = 0
last_signal_type = None

# ══════════════════════════════════════════════
#  DONNÉES — KRAKEN XAU/USD TEMPS RÉEL
# ══════════════════════════════════════════════
def get_xauusd_m5():
    exchanges = [
        ("kraken", "XAUT/USD"),
        ("kucoin", "XAU/USDT"),
        ("okx",    "XAU/USDT"),
    ]
    for ex_name, symbol in exchanges:
        try:
            ex   = getattr(ccxt, ex_name)()
            bars = ex.fetch_ohlcv(symbol, "5m", limit=100)
            if not bars or len(bars) < 60:
                continue
            df = pd.DataFrame(bars, columns=["time","Open","High","Low","Close","Volume"])
            df["time"] = pd.to_datetime(df["time"], unit="ms")
            df = df.dropna().reset_index(drop=True)
            print(f"✅ {ex_name} {symbol} : {len(df)} bougies — ${df['Close'].iloc[-1]:.2f}")
            return df
        except Exception as e:
            print(f"⚠️ {ex_name} : {e}")
            continue
    print("❌ Aucune source disponible")
    return None

# ══════════════════════════════════════════════
#  SESSIONS
# ══════════════════════════════════════════════
def in_session():
    now = datetime.now(timezone.utc)
    nm  = now.hour * 60 + now.minute
    for s in SESSIONS:
        if s["debut"] * 60 <= nm < s["fin"] * 60:
            return True, s["nom"]
    return False, None

# ══════════════════════════════════════════════
#  INDICATEURS
# ══════════════════════════════════════════════
def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_atr(high, low, close, period):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ══════════════════════════════════════════════
#  ANALYSE EMA FLOW
# ══════════════════════════════════════════════
def analyser(df):
    global last_signal_bar, bar_index, last_signal_type

    if df is None or len(df) < EMA_SLOW + ATR_LEN + 5:
        print("⚠️ Pas assez de données")
        return

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    open_ = df["Open"]

    bar_index = len(df)
    ema20 = calc_ema(close, EMA_FAST)
    ema50 = calc_ema(close, EMA_SLOW)
    atr   = calc_atr(high, low, close, ATR_LEN)

    i   = -2
    e20 = float(ema20.iloc[i])
    e50 = float(ema50.iloc[i])
    at  = float(atr.iloc[i])
    cl  = float(close.iloc[i])
    hi  = float(high.iloc[i])
    lo  = float(low.iloc[i])
    op  = float(open_.iloc[i])

    if at == 0 or np.isnan(at):
        return

    zone_hi    = e20 + at * ZONE_MULT
    zone_lo    = e20 - at * ZONE_MULT
    trend_up   = e20 > e50
    trend_down = e20 < e50
    touch      = (lo <= zone_hi) and (hi >= zone_lo)
    bull       = cl > op and cl > e20
    bear       = cl < op and cl < e20
    sess, sess_nom = in_session()
    can        = (bar_index - last_signal_bar) >= COOLDOWN

    print(f"📈 ${cl:.2f} | EMA20:{e20:.2f} EMA50:{e50:.2f} | {'▲' if trend_up else '▼'} | Zone:{'✅' if touch else '❌'} | {'✅ '+sess_nom if sess else '❌ Hors session'}")

    buy  = sess and can and trend_up   and touch and bull
    sell = sess and can and trend_down and touch and bear

    if buy or sell:
        signal = "BUY" if buy else "SELL"
        if last_signal_type == signal:
            print(f"⏭️ Doublon {signal} ignoré")
            return
        sl = cl - SL_USD if signal == "BUY" else cl + SL_USD
        tp = cl + TP_USD if signal == "BUY" else cl - TP_USD
        last_signal_bar  = bar_index
        last_signal_type = signal
        print(f"\n🚨 SIGNAL {signal} @ ${cl:.2f}")
        send_discord(signal, cl, sl, tp, e20, e50, at, sess_nom)
    else:
        print("⏳ Pas de signal")

# ══════════════════════════════════════════════
#  DISCORD
# ══════════════════════════════════════════════
def send_discord(signal, prix, sl, tp, ema20, ema50, atr, session):
    ic, color = ("🟢", 3066993) if signal == "BUY" else ("🔴", 15158332)
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    payload = {
        "username": "⚡ EMA FLOW XAU/USD",
        "embeds": [{"title": f"{ic} SIGNAL {signal} — XAU/USD M5",
            "color": color,
            "fields": [
                {"name": "💰 Entrée",      "value": f"${prix:.2f}",  "inline": True},
                {"name": "🛑 Stop Loss",   "value": f"${sl:.2f}",    "inline": True},
                {"name": "🎯 Take Profit", "value": f"${tp:.2f}",    "inline": True},
                {"name": "📊 EMA 20",      "value": f"${ema20:.2f}", "inline": True},
                {"name": "📊 EMA 50",      "value": f"${ema50:.2f}", "inline": True},
                {"name": "📉 ATR",         "value": f"{atr:.4f}",    "inline": True},
                {"name": "⚖️ R/R",         "value": f"1:{TP_USD/SL_USD:.1f}", "inline": True},
                {"name": "🕐 Session",     "value": session,          "inline": True},
            ],
            "footer": {"text": f"EMA FLOW · Kraken · {now}"},
            "timestamp": datetime.now(timezone.utc).isoformat()}]}
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print("✅ Discord envoyé" if r.status_code == 204 else f"⚠️ {r.status_code}")
    except Exception as e:
        print(f"❌ Discord : {e}")

def send_heartbeat():
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    sess, nom = in_session()
    payload = {
        "username": "⚡ EMA FLOW XAU/USD",
        "embeds": [{"title": "💓 EMA FLOW — Serveur actif 24/7",
            "color": 16776960,
            "fields": [
                {"name": "Statut", "value": f"🟢 Session {nom}" if sess else "⏳ Hors session", "inline": True},
                {"name": "Heure",  "value": now, "inline": True},
                {"name": "Source", "value": "✅ Kraken — Prix réels", "inline": True},
            ],
            "footer": {"text": "EMA FLOW — Railway 24/7"}}]}
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print(f"💓 Heartbeat — {now}")
    except: pass

# ══════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════
def main():
    print("⚡ EMA FLOW BOT — Kraken XAU/USD temps réel")
    print("=" * 50)
    send_heartbeat()
    heartbeat_counter = 0

    while True:
        print(f"\n{'='*50}\n⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        df = get_xauusd_m5()
        analyser(df)
        heartbeat_counter += 1
        if heartbeat_counter >= 12:
            send_heartbeat()
            heartbeat_counter = 0
        now = datetime.now(timezone.utc)
        secs_to_next = 300 - (now.minute % 5) * 60 - now.second + 5
        print(f"⏰ Prochaine analyse dans {secs_to_next}s")
        time.sleep(secs_to_next)

if __name__ == "__main__":
    main()
