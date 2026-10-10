"""
Trading-Entscheidungsagent: Dow-Jones-Scanner als Web-App (Long)
Keine Finanzberatung, keine Prognose. Nur Strukturierung von Signalen.
"""
import io

import pandas as pd
import streamlit as st
import yfinance as yf

DOW = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
       "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK",
       "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT"]

SIGNALE = ["RSI schneidet MA", "Kerze schneidet EMA20", "EMA5 schneidet EMA20"]

st.set_page_config(page_title="Dow Scanner", layout="centered")


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def cross_up(a, b, n):
    diff = a - b
    return bool(((diff.shift(1) <= 0) & (diff > 0)).tail(n).any())


@st.cache_data(ttl=3600, show_spinner=False)
def lade(ticker):
    return yf.download(ticker, period="2y", interval="1d",
                       auto_adjust=True, progress=False)


def analyse(ticker, lookback):
    df = lade(ticker)
    if df.empty or len(df) < 220:
        return None
    c = df["Close"].squeeze()
    ema5, ema20, ema200 = (c.ewm(span=s, adjust=False).mean() for s in (5, 20, 200))
    r = rsi(c)
    r_ma = r.rolling(14).mean()
    return {
        "Ticker": ticker,
        "Kurs": round(float(c.iloc[-1]), 2),
        "Ueber EMA200": bool(c.iloc[-1] > ema200.iloc[-1]),
        "Abstand EMA200 %": round(float((c.iloc[-1] / ema200.iloc[-1] - 1) * 100), 1),
        "RSI schneidet MA": cross_up(r, r_ma, lookback),
        "Kerze schneidet EMA20": cross_up(c, ema20, lookback),
        "EMA5 schneidet EMA20": cross_up(ema5, ema20, lookback),
        "Volatilitaet 20T %": round(float(c.pct_change().tail(20).std() * 100), 2),
        "RSI": round(float(r.iloc[-1]), 1),
    }


def bericht(z):
    aktiv = [k for k in SIGNALE if z[k]]
    n = len(aktiv)
    szen = "bullisch" if n >= 2 else "neutral" if n == 1 else "abwartend"
    setup = "Pullback/Trendfortsetzung" if z["Kerze schneidet EMA20"] else "Trend ohne frischen Einstieg"
    return f"""**1. Kontext**
Trend über EMA200 ({z['Abstand EMA200 %']} %), Volatilität {z['Volatilitaet 20T %']} % (20 Tage), RSI {z['RSI']}.
Setup-Idee: {setup}.
Aktive Signale: {', '.join(aktiv) if aktiv else 'keine'}.
Pro: Kurs über EMA200, {n} von 3 Signalen aktiv.
Contra: MA Rush und LIQ Setup sind hier **nicht** geprüft.
Risiko: Stop-Lage und Positionsgröße selbst festlegen.

**2. Wenn-Dann-Regeln**
- Wenn mind. 2 Signale aktiv UND MA Rush bullish UND LIQ Long Break, dann Setup prüfen.
- Wenn der Kurs unter die EMA200 schließt, dann Long-Idee verwerfen.
- Wenn nur 1 Signal aktiv ist, dann beobachten, nicht handeln.

**3. Szenario heute:** {szen}

**4. Reflexionsfragen**
- Wo liegt mein Ausstieg, wenn die Idee falsch ist?
- Passt der Abstand zur EMA200 zu meinem Risiko?
- Bestätigen MA Rush und LIQ Setup im Chart das Bild?
- Stehen Quartalszahlen oder News in den nächsten Tagen an?"""


st.title("Dow Scanner")
st.caption("Long-Setups über EMA200. Keine Finanzberatung, keine Prognose.")

lookback = st.slider("Signal-Zeitraum (letzte Tage)", 1, 10, 3)
min_signale = st.slider("Mindestanzahl Signale", 0, 3, 1)

if st.button("Scan starten", type="primary", width="stretch"):
    rows = []
    balken = st.progress(0.0, text="Lade Kurse ...")
    for i, t in enumerate(DOW, 1):
        z = analyse(t, lookback)
        if z:
            rows.append(z)
        balken.progress(i / len(DOW), text=f"{t} ({i}/{len(DOW)})")
    balken.empty()
    st.session_state["rows"] = rows

rows = st.session_state.get("rows")
if rows:
    tab = pd.DataFrame(rows)
    tab["Signale"] = tab[SIGNALE].sum(axis=1)
    treffer = tab[tab["Ueber EMA200"] & (tab["Signale"] >= min_signale)]
    treffer = treffer.sort_values("Signale", ascending=False)

    st.subheader(f"{len(treffer)} Treffer ({int(tab['Ueber EMA200'].sum())} von {len(tab)} über EMA200)")
    st.dataframe(treffer, hide_index=True, width="stretch")

    buf = io.BytesIO()
    treffer.to_excel(buf, index=False)
    st.download_button("Als Excel speichern", buf.getvalue(), "dow_scan.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")

    for z in treffer.to_dict("records"):
        with st.expander(f"{z['Ticker']}  |  {z['Kurs']}  |  {z['Signale']} Signal(e)"):
            st.markdown(bericht(z))
elif rows is not None:
    st.warning("Keine Daten geladen. Bitte später erneut versuchen.")
