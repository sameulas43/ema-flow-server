import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1478745804167446578/QeTmCPBkKV7exHZNx2aB4SWK3nDSuq1FD12Mt1-rXVFit48nPu8oqleawZuQEv_Gjwar"
ALPHA_KEY       = "EO7D68RIHHT4ZKTF"

EMA_FAST  = 20
EMA_SLOW  = 50
ATR_LEN   = 14
ZONE_MULT = 0.25
COOLDOWN  = 6
SL_USD    = 1.00
TP_USD    = 2.00

SESSIONS = [
    {"nom": "LONDON",   "debut": 7,  "fin": 10, "dM": 0,  "fM": 0},
    {"nom": "NEW YORK", "debut": 13, "fin": 16, "dM": 30, "fM": 30},
]

last_signal_bar  = -999
bar_index        = 0
last_signal_type = None

def get_xauusd_m5():
    url = (f"https://www.alphavantage.co/query"
           f"?function=FX_INTRADAY"
           f"&from_symbol=XAU&to_symbol=USD"
           f"&interval=5min&outputsize=compact"
           f"&apikey={ALPHA_KEY}")
    try:
        r    = requests.get(url, timeout=15)
        data = r.json()
        key  = "Time Series FX (5min)"
        if key not in data:
            print(f"⚠️ Alpha Vantage : {data.get('Note', data.get('Information', list(data.keys())))}")
            return None
        rows = []
        for ts, v in data[key].items():
            rows.append({"time": pd.Timestamp(ts),
                         "Open":  float(v["1. open"]),
                         "High":  float(v["2. high"]),
                         "Low":   float(v["3. low"]),
                         "Close": float(v["4. close"])})
        df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
        print(f"✅ {len(df)} bougies M5 — dernier prix : ${float(df['Close'].iloc[-1]):.2f}")
        return df
    except Exception as e:
        print(f"❌ Alpha Vantage : {e}")
        return None

def in_session():
    now = datetime.now(timezone.utc)
    nm  = now.hour * 60 + now.minute
    for s in SESSIONS:
        if s["debut"]*60+s["dM"] <= nm < s["fin"]*60+s["fM"]:
            return True, s["nom"]
    return False, None

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_atr(high, low, close, period):
    tr = pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(period).mean()

def analyser(df):
    global last_signal_bar, bar_index, last_signal_type
    if df is None or len(df) < EMA_SLOW + ATR_LEN + 5:
        print("⚠️ Pas assez de données"); return

    close, high, low, open_ = df["Close"], df["High"], df["Low"], df["Open"]
    bar_index = len(df)
    ema20 = calc_ema(close, EMA_FAST)
    ema50 = calc_ema(close, EMA_SLOW)
    atr   = calc_atr(high, low, close, ATR_LEN)
    i     = -2
    e20, e50 = float(ema20.iloc[i]), float(ema50.iloc[i])
    at       = float(atr.iloc[i])
    cl, hi, lo, op = float(close.iloc[i]), float(high.iloc[i]), float(low.iloc[i]), float(open_.iloc[i])

    if at == 0 or np.isnan(at): return

    zone_hi, zone_lo = e20 + at*ZONE_MULT, e20 - at*ZONE_MULT
    trend_up   = e20 > e50
    trend_down = e20 < e50
    touch      = (lo <= zone_hi) and (hi >= zone_lo)
    bull       = cl > op and cl > e20
    bear       = cl < op and cl < e20
    sess, sess_nom = in_session()
    can        = (bar_index - last_signal_bar) >= COOLDOWN

    print(f"📈 Prix : ${cl:.2f} | EMA20: ${e20:.2f} | EMA50: ${e50:.2f}")
    print(f"🕐 {'✅ '+sess_nom if sess else '❌ Hors session'} | {'▲ HAUSSIÈRE' if trend_up else '▼ BAISSIÈRE'} | Zone: {'✅' if touch else '❌'}")

    buy  = sess and can and trend_up   and touch and bull
    sell = sess and can and trend_down and touch and bear

    if buy or sell:
        signal = "BUY" if buy else "SELL"
        if last_signal_type == signal:
            print(f"⏭️ Doublon {signal} ignoré"); return
        sl = cl - SL_USD if signal == "BUY" else cl + SL_USD
        tp = cl + TP_USD if signal == "BUY" else cl - TP_USD
        last_signal_bar, last_signal_type = bar_index, signal
        print(f"\n🚨 SIGNAL {signal} @ ${cl:.2f}")
        send_discord(signal, cl, sl, tp, e20, e50, at, sess_nom)
    else:
        print("⏳ Pas de signal")

def send_discord(signal, prix, sl, tp, ema20, ema50, atr, session):
    ic, color = ("🟢", 3066993) if signal == "BUY" else ("🔴", 15158332)
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    payload = {"username": "⚡ EMA FLOW XAU/USD", "embeds": [{"title": f"{ic} SIGNAL {signal} — XAU/USD M5", "color": color,
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
        "footer": {"text": f"EMA FLOW LDN+NY · Alpha Vantage · {now}"},
        "timestamp": datetime.now(timezone.utc).isoformat()}]}
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print("✅ Discord envoyé" if r.status_code == 204 else f"⚠️ Discord {r.status_code}")
    except Exception as e:
        print(f"❌ Discord : {e}")

def send_heartbeat():
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    sess, nom = in_session()
    payload = {"username": "⚡ EMA FLOW XAU/USD", "embeds": [{"title": "💓 EMA FLOW — Serveur actif 24/7", "color": 16776960,
        "fields": [
            {"name": "Statut", "value": f"🟢 Session {nom}" if sess else "⏳ Hors session", "inline": True},
            {"name": "Heure",  "value": now, "inline": True},
            {"name": "Source", "value": "✅ Alpha Vantage — Prix réels", "inline": True},
        ],
        "footer": {"text": "EMA FLOW LDN+NY — Railway Server"}}]}
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print(f"💓 Heartbeat — {now}")
    except: pass

def main():
    print("⚡ EMA FLOW BOT — Alpha Vantage")
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
