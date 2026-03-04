import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone

# ══════════════════════════════════════════════
#  CONFIG — MIROIR EXACT DE VOTRE PINESCRIPT
# ══════════════════════════════════════════════
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1478745804167446578/QeTmCPBkKV7exHZNx2aB4SWK3nDSuq1FD12Mt1-rXVFit48nPu8oqleawZuQEv_Gjwar"

EMA_FAST    = 20
EMA_SLOW    = 50
ATR_LEN     = 14
ZONE_MULT   = 0.25
COOLDOWN    = 6       # barres M5
SL_USD      = 1.00
TP_USD      = 2.00

SESSIONS = [
    {"nom": "LONDON",   "debut": 7,  "fin": 10, "dM": 0,  "fM": 0},
    {"nom": "NEW YORK", "debut": 13, "fin": 16, "dM": 30, "fM": 30},
]

# ══════════════════════════════════════════════
#  ÉTAT
# ══════════════════════════════════════════════
last_signal_bar = -999
bar_index       = 0
last_signal_type = None

# ══════════════════════════════════════════════
#  SESSIONS
# ══════════════════════════════════════════════
def in_session():
    now = datetime.now(timezone.utc)
    nm  = now.hour * 60 + now.minute
    for s in SESSIONS:
        debut = s["debut"] * 60 + s["dM"]
        fin   = s["fin"]   * 60 + s["fM"]
        if debut <= nm < fin:
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
#  ENVOI DISCORD
# ══════════════════════════════════════════════
def send_discord(signal, prix, sl, tp, ema20, ema50, session_nom):
    ic     = "🟢" if signal == "BUY" else "🔴"
    color  = 3066993 if signal == "BUY" else 15158332
    now_fr = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    payload = {
        "username": "⚡ EMA FLOW XAU/USD",
        "embeds": [{
            "title": f"{ic} SIGNAL {signal} — XAU/USD M5",
            "color": color,
            "fields": [
                {"name": "💰 Entrée",      "value": f"${prix:.2f}",  "inline": True},
                {"name": "🛑 Stop Loss",   "value": f"${sl:.2f}",    "inline": True},
                {"name": "🎯 Take Profit", "value": f"${tp:.2f}",    "inline": True},
                {"name": "📊 EMA 20",      "value": f"${ema20:.2f}", "inline": True},
                {"name": "📊 EMA 50",      "value": f"${ema50:.2f}", "inline": True},
                {"name": "⚖️ R/R",         "value": f"1:{TP_USD/SL_USD:.1f}", "inline": True},
                {"name": "🕐 Session",     "value": session_nom,     "inline": True},
            ],
            "footer": {"text": f"EMA FLOW LDN+NY · {now_fr}"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }

    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if r.status_code == 204:
            print(f"✅ Discord envoyé : {signal} @ ${prix:.2f}")
        else:
            print(f"⚠️ Discord erreur : {r.status_code}")
    except Exception as e:
        print(f"❌ Discord exception : {e}")

def send_heartbeat():
    """Envoie un message de statut toutes les heures"""
    now_fr = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    sess, nom = in_session()
    statut = f"🟢 Session {nom} active" if sess else "⏳ Hors session"
    payload = {
        "username": "⚡ EMA FLOW XAU/USD",
        "embeds": [{
            "title": "💓 Agent actif — Surveillance en cours",
            "color": 16776960,
            "fields": [
                {"name": "Statut",   "value": statut, "inline": True},
                {"name": "Heure",    "value": now_fr,  "inline": True},
            ],
            "footer": {"text": "EMA FLOW LDN+NY — Serveur 24/7"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print(f"💓 Heartbeat envoyé — {now_fr}")
    except:
        pass

# ══════════════════════════════════════════════
#  ANALYSE PRINCIPALE
# ══════════════════════════════════════════════
def analyser():
    global last_signal_bar, bar_index, last_signal_type

    print(f"\n{'='*50}")
    print(f"⏰ Analyse M5 — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

    # ── 1. Récupérer les données réelles XAU/USD M5 ──
    try:
        df = yf.download("GC=F", period="5d", interval="5m", progress=False, auto_adjust=True)
        if df.empty or len(df) < EMA_SLOW + ATR_LEN + 5:
            print("⚠️ Pas assez de données")
            return
    except Exception as e:
        print(f"❌ Erreur données : {e}")
        return

    # Aplatir les colonnes si MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    open_ = df["Open"]

    bar_index = len(df)

    # ── 2. Indicateurs ──
    ema20 = calc_ema(close, EMA_FAST)
    ema50 = calc_ema(close, EMA_SLOW)
    atr   = calc_atr(high, low, close, ATR_LEN)

    # Dernière bougie complète (avant la bougie en cours)
    i = -2

    e20   = float(ema20.iloc[i])
    e50   = float(ema50.iloc[i])
    at    = float(atr.iloc[i])
    cl    = float(close.iloc[i])
    hi    = float(high.iloc[i])
    lo    = float(low.iloc[i])
    op    = float(open_.iloc[i])

    zone_hi = e20 + at * ZONE_MULT
    zone_lo = e20 - at * ZONE_MULT

    print(f"📈 Prix    : ${cl:.2f}")
    print(f"📊 EMA20   : ${e20:.2f} | EMA50 : ${e50:.2f}")
    print(f"📐 Zone    : ${zone_lo:.2f} — ${zone_hi:.2f}")
    print(f"📉 ATR     : {at:.4f}")

    # ── 3. Conditions ──
    trend_up   = e20 > e50
    trend_down = e20 < e50
    touch_zone = (lo <= zone_hi) and (hi >= zone_lo)
    bull       = cl > op and cl > e20
    bear       = cl < op and cl < e20

    sess, session_nom = in_session()
    can_signal = (bar_index - last_signal_bar) >= COOLDOWN

    print(f"🕐 Session : {'✅ '+session_nom if sess else '❌ Hors session'}")
    print(f"⏳ Cooldown: {'✅ OK' if can_signal else '❌ Attente'}")
    print(f"📈 Tendance: {'▲ HAUSSIÈRE' if trend_up else '▼ BAISSIÈRE' if trend_down else '— Neutre'}")
    print(f"🎯 Zone    : {'✅ Touchée' if touch_zone else '❌ Non touchée'}")
    print(f"🕯️ Bougie  : {'🟢 Haussière' if bull else '🔴 Baissière' if bear else '⬜ Indécise'}")

    # ── 4. Signaux ──
    buy_signal  = sess and can_signal and trend_up   and touch_zone and bull
    sell_signal = sess and can_signal and trend_down and touch_zone and bear

    if buy_signal or sell_signal:
        signal = "BUY" if buy_signal else "SELL"
        sl = cl - SL_USD if signal == "BUY" else cl + SL_USD
        tp = cl + TP_USD if signal == "BUY" else cl - TP_USD

        print(f"\n🚨 SIGNAL {signal} DÉTECTÉ !")
        print(f"   Entrée : ${cl:.2f}")
        print(f"   SL     : ${sl:.2f}")
        print(f"   TP     : ${tp:.2f}")

        last_signal_bar  = bar_index
        last_signal_type = signal

        send_discord(signal, cl, sl, tp, e20, e50, session_nom)
    else:
        print("⏳ Pas de signal cette bougie")

# ══════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════
def main():
    print("⚡ EMA FLOW SERVER — Démarrage")
    print(f"📡 Discord webhook configuré")
    print(f"⏱️  Analyse toutes les 5 minutes")
    print("="*50)

    send_heartbeat()

    heartbeat_counter = 0

    while True:
        try:
            analyser()
        except Exception as e:
            print(f"❌ Erreur analyse : {e}")

        heartbeat_counter += 1

        # Heartbeat toutes les 12 analyses = 1 heure
        if heartbeat_counter >= 12:
            send_heartbeat()
            heartbeat_counter = 0

        # Attendre jusqu'à la prochaine bougie M5
        now = datetime.now(timezone.utc)
        secs_in_bar  = (now.minute % 5) * 60 + now.second
        secs_to_next = 300 - secs_in_bar + 5  # +5s pour laisser la bougie se fermer
        print(f"\n⏰ Prochaine analyse dans {secs_to_next}s")
        time.sleep(secs_to_next)

if __name__ == "__main__":
    main()
