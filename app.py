"""
Aktien-Scanner (Long): Dow Jones und DAX mit Chart bei Klick auf eine Aktie.
Keine Finanzberatung, keine Prognose. Nur Strukturierung von Signalen.
"""
import io
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

MAERKTE = {
    "Dow Jones": {
        "AAPL": "Apple", "AMGN": "Amgen", "AMZN": "Amazon", "AXP": "American Express",
        "BA": "Boeing", "CAT": "Caterpillar", "CRM": "Salesforce", "CSCO": "Cisco",
        "CVX": "Chevron", "DIS": "Disney", "GOOGL": "Alphabet", "GS": "Goldman Sachs",
        "HD": "Home Depot", "HON": "Honeywell", "IBM": "IBM", "JNJ": "Johnson & Johnson",
        "JPM": "JPMorgan", "KO": "Coca-Cola", "MCD": "McDonald's", "MMM": "3M",
        "MRK": "Merck & Co.", "MSFT": "Microsoft", "NKE": "Nike", "NVDA": "Nvidia",
        "PG": "Procter & Gamble", "SHW": "Sherwin-Williams", "TRV": "Travelers",
        "UNH": "UnitedHealth", "V": "Visa", "WMT": "Walmart",
    },
    "DAX": {
        "ADS.DE": "adidas", "AIR.DE": "Airbus", "ALV.DE": "Allianz", "BAS.DE": "BASF",
        "BAYN.DE": "Bayer", "BEI.DE": "Beiersdorf", "BMW.DE": "BMW", "BNR.DE": "Brenntag",
        "CBK.DE": "Commerzbank", "CON.DE": "Continental", "DB1.DE": "Deutsche Börse",
        "DBK.DE": "Deutsche Bank", "DHL.DE": "DHL Group", "DTE.DE": "Deutsche Telekom",
        "DTG.DE": "Daimler Truck", "ENR.DE": "Siemens Energy", "EOAN.DE": "E.ON",
        "FME.DE": "Fresenius Medical Care", "FRE.DE": "Fresenius", "G1A.DE": "GEA",
        "G24.DE": "Scout24", "HEI.DE": "Heidelberg Materials", "HEN3.DE": "Henkel",
        "HNR1.DE": "Hannover Rück", "HOT.DE": "Hochtief", "IFX.DE": "Infineon",
        "MBG.DE": "Mercedes-Benz", "MRK.DE": "Merck", "MTX.DE": "MTU Aero Engines",
        "MUV2.DE": "Münchener Rück", "QIA.DE": "Qiagen", "RHM.DE": "Rheinmetall",
        "RWE.DE": "RWE", "SAP.DE": "SAP", "SHL.DE": "Siemens Healthineers",
        "SIE.DE": "Siemens", "SY1.DE": "Symrise", "VNA.DE": "Vonovia",
        "VOW3.DE": "Volkswagen Vz.", "ZAL.DE": "Zalando",
    },
}
SIGNALE = ["RSI schneidet MA", "Kerze schneidet EMA20", "EMA5 schneidet EMA20"]
ANZEIGE = ["Name", "Ticker", "Kurs", "Abstand EMA200 %", "Signale"]
TAGE = {"3 Monate": 63, "6 Monate": 126, "1 Jahr": 252}

st.set_page_config(page_title="Aktien-Scanner",
                   page_icon=str(Path(__file__).parent / "icon.png"),
                   layout="centered")


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


def indikatoren(df):
    c = df["Close"].squeeze()
    r = rsi(c)
    return {"c": c, "ema5": c.ewm(span=5, adjust=False).mean(),
            "ema20": c.ewm(span=20, adjust=False).mean(),
            "ema200": c.ewm(span=200, adjust=False).mean(),
            "r": r, "r_ma": r.rolling(14).mean()}


def analyse(ticker, name, lookback):
    df = lade(ticker)
    if df.empty or len(df) < 220:
        return None
    i = indikatoren(df)
    c = i["c"]
    return {
        "Name": name, "Ticker": ticker,
        "Kurs": round(float(c.iloc[-1]), 2),
        "Ueber EMA200": bool(c.iloc[-1] > i["ema200"].iloc[-1]),
        "Abstand EMA200 %": round(float((c.iloc[-1] / i["ema200"].iloc[-1] - 1) * 100), 1),
        "RSI schneidet MA": cross_up(i["r"], i["r_ma"], lookback),
        "Kerze schneidet EMA20": cross_up(c, i["ema20"], lookback),
        "EMA5 schneidet EMA20": cross_up(i["ema5"], i["ema20"], lookback),
        "Volatilitaet 20T %": round(float(c.pct_change().tail(20).std() * 100), 2),
        "RSI": round(float(i["r"].iloc[-1]), 1),
    }


def zeige_chart(z, tage):
    df = lade(z["Ticker"])
    i = indikatoren(df)
    d = df.tail(tage)
    x = d.index
    s = lambda k: i[k].reindex(x)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(
        x=x, open=d["Open"].squeeze(), high=d["High"].squeeze(),
        low=d["Low"].squeeze(), close=d["Close"].squeeze(),
        name="Kurs", showlegend=False), row=1, col=1)
    for k, name, farbe in (("ema5", "EMA5", "#7f7f7f"), ("ema20", "EMA20", "#1f77b4"),
                           ("ema200", "EMA200", "#ff7f0e")):
        fig.add_trace(go.Scatter(x=x, y=s(k), name=name, mode="lines",
                                 line=dict(color=farbe, width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=s("r"), name="RSI", mode="lines",
                             line=dict(color="#9467bd", width=1.6)), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=s("r_ma"), name="RSI-MA", mode="lines",
                             line=dict(color="#7f7f7f", width=1.4)), row=2, col=1)
    for lvl in (30, 70):
        fig.add_hline(y=lvl, line=dict(dash="dot", width=1, color="#999999"), row=2, col=1)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])],
                     rangeslider_visible=False, fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    fig.update_layout(height=520, margin=dict(l=4, r=4, t=36, b=4),
                      legend=dict(orientation="h", y=1.07, x=0), dragmode=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


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


st.title("Aktien-Scanner")
st.caption("Long-Setups über EMA200. Keine Finanzberatung, keine Prognose.")

lookback = st.slider("Signal-Zeitraum (letzte Tage)", 1, 10, 3)
min_signale = st.slider("Mindestanzahl Signale", 0, 3, 1)

spalte1, spalte2 = st.columns(2)
gewaehlt = None
if spalte1.button("Dow Jones scannen", type="primary", width="stretch"):
    gewaehlt = "Dow Jones"
if spalte2.button("DAX scannen", type="primary", width="stretch"):
    gewaehlt = "DAX"

if gewaehlt:
    balken = st.progress(0.0, text="Lade Kurse ...")
    werte = MAERKTE[gewaehlt]
    for n, t in enumerate(werte, 1):
        lade(t)
        balken.progress(n / len(werte), text=f"{t} ({n}/{len(werte)})")
    balken.empty()
    st.session_state["markt"] = gewaehlt
    st.session_state["scan_nr"] = st.session_state.get("scan_nr", 0) + 1

markt = st.session_state.get("markt")
if markt:
    werte = MAERKTE[markt]
    rows = [z for t, n in werte.items() if (z := analyse(t, n, lookback))]
    if not rows:
        st.warning("Keine Daten geladen. Bitte später erneut versuchen.")
        st.stop()
    fehlt = [t for t in werte if t not in {z["Ticker"] for z in rows}]
    tab = pd.DataFrame(rows)
    tab["Signale"] = tab[SIGNALE].sum(axis=1)
    treffer = tab[tab["Ueber EMA200"] & (tab["Signale"] >= min_signale)]
    treffer = treffer.sort_values(["Signale", "Abstand EMA200 %"],
                                  ascending=[False, False]).reset_index(drop=True)

    st.subheader(f"{markt}: {len(treffer)} Treffer "
                 f"({int(tab['Ueber EMA200'].sum())} von {len(tab)} über EMA200)")
    if fehlt:
        st.caption("Keine Daten für: " + ", ".join(fehlt))
    if treffer.empty:
        st.info("Keine Treffer. Setze die Mindestanzahl Signale herunter.")
        st.stop()

    st.caption("Tippe auf eine Zeile, um den Chart zu sehen.")
    ereignis = st.dataframe(treffer[ANZEIGE], hide_index=True, width="stretch",
                            on_select="rerun", selection_mode="single-row",
                            key=f"tab_{markt}_{st.session_state.get('scan_nr', 0)}")

    buf = io.BytesIO()
    treffer.to_excel(buf, index=False)
    st.download_button("Als Excel speichern", buf.getvalue(), f"{markt}_scan.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")

    zeilen = ereignis.selection.rows
    if zeilen:
        z = treffer.iloc[zeilen[0]].to_dict()
        st.subheader(f"{z['Name']} ({z['Ticker']})")
        zeitraum = st.radio("Zeitraum", list(TAGE), index=1, horizontal=True)
        zeige_chart(z, TAGE[zeitraum])
        st.markdown(bericht(z))
