import ccxt
import pandas as pd
import requests
import time
from datetime import datetime, timezone

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1478745804167446578/QeTmCPBkKV7exHZNx2aB4SWK3nDSuq1FD12Mt1-rXVFit48nPu8oqleawZuQEv_Gjwar"

EMA_FAST = 20
EMA_SLOW = 50
SL_USD   = 1.50
TP_USD   = 3.50

last_signal_type = None
last_signal_bar  = -999
bar_index        = 0

def get_data():
    try:
        ex   = ccxt.kraken()
        bars = ex.fetch_ohlcv("XAUT/USD", "5m", limit=100)
        df   = pd.DataFrame(bars, columns=["time","Open","High","Low","Close","Volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df.dropna().reset_index(drop=True)
    except Exception as e:
        print(f"❌ {e}")
        return None

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def analyser(df):
    global last_signal_type, last_signal_bar, bar_index
    if df is None or len(df) < 60:
        return
    close    = df["Close"]
    ema_fast = calc_ema(close, EMA_FAST)
    ema_slow = calc_ema(close, EMA_SLOW)
    bar_index = len(df)
    cl_curr  = float(close.iloc[-2])
    cl_prev  = float(close.iloc[-3])
    ef_curr  = float(ema_fast.iloc[-2])
    ef_prev  = float(ema_fast.iloc[-3])
    es_curr  = float(ema_slow.iloc[-2])
    bull     = ef_curr > es_curr
    bear     = ef_curr < es_curr
    crossover  = (cl_prev < ef_prev) and (cl_curr > ef_curr)
    crossunder = (cl_prev > ef_prev) and (cl_curr < ef_curr)
    buy  = bull and crossover
    sell = bear and crossunder
    print(f"${cl_curr:.2f} | EMA20:{ef_curr:.2f} | EMA50:{es_curr:.2f} | {'▲' if bull else '▼'} | Cross↑:{crossover} Cross↓:{crossunder}")
    if buy or sell:
        signal = "BUY" if buy else "SELL"
        if last_signal_type == signal and (bar_index - last_signal_bar) < 3:
            return
        sl = cl_curr - SL_USD if signal == "BUY" else cl_curr + SL_USD
        tp = cl_curr + TP_USD if signal == "BUY" else cl_curr - TP_USD
        last_signal_type = signal
        last_signal_bar  = bar_index
        print(f"🚨 {signal} @ ${cl_curr:.2f}")
        send_discord(signal, cl_curr, sl, tp, ef_curr, es_curr)
    else:
        print("⏳ Pas de signal")

def send_discord(signal, prix, sl, tp, ema20, ema50):
    ic, color = ("🟢", 3066993) if signal == "BUY" else ("🔴", 15158332)
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    payload = {"username": "⚡ SNIPER XAUUSD M5", "embeds": [{"title": f"{ic} SIGNAL {signal} — XAUUSD M5", "color": color, "fields": [{"name": "💰 Entrée", "value": f"${prix:.2f}", "inline": True}, {"name": "🛑 SL", "value": f"${sl:.2f}", "inline": True}, {"name": "🎯 TP", "value": f"${tp:.2f}", "inline": True}, {"name": "📊 EMA20", "value": f"${ema20:.2f}", "inline": True}, {"name": "📊 EMA50", "value": f"${ema50:.2f}", "inline": True}, {"name": "⚖️ R/R", "value": f"1:{TP_USD/SL_USD:.1f}", "inline": True}], "footer": {"text": f"SNIPER · Kraken · {now}"}, "timestamp": datetime.now(timezone.utc).isoformat()}]}
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print("✅ Discord" if r.status_code == 204 else f"⚠️ {r.status_code}")
    except Exception as e:
        print(f"❌ {e}")

def send_heartbeat():
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    payload = {"username": "⚡ SNIPER XAUUSD M5", "embeds": [{"title": "💓 Serveur actif 24/7", "color": 16776960, "fields": [{"name": "Heure", "value": now, "inline": True}], "footer": {"text": "Railway 24/7"}}]}
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print(f"💓 {now}")
    except: pass

def main():
    print("⚡ SNIPER XAUUSD M5 — EMA Cross")
    send_heartbeat()
    hb = 0
    while True:
        print(f"\n⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        analyser(get_data())
        hb += 1
        if hb >= 12:
            send_heartbeat()
            hb = 0
        now = datetime.now(timezone.utc)
        secs = 300 - (now.minute % 5) * 60 - now.second + 5
        time.sleep(secs)

if __name__ == "__main__":
    main()
