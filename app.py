"""
Aktien-Scanner (Long): Dow Jones, DAX, S&P 500 und Nasdaq-100 mit Chart bei Klick auf eine Aktie.
Keine Finanzberatung, keine Prognose. Nur Strukturierung von Signalen.
"""
import io
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

STATISCH = {
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
WIKI = {
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol", "Security"),
    "Nasdaq-100": ("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker", "Company"),
}
DE_WIKI = {"MDAX": "https://de.wikipedia.org/wiki/MDAX", "SDAX": "https://de.wikipedia.org/wiki/SDAX"}
INDIZES = {"Dow Jones": "^DJI", "DAX": "^GDAXI", "MDAX": "^MDAXI", "SDAX": "^SDAXI",
           "S&P 500": "^GSPC", "Nasdaq-100": "^NDX"}
MARKT_NAMEN = ["Dow Jones", "DAX", "MDAX", "SDAX", "S&P 500", "Nasdaq-100"]
SIGNALE = ["RSI schneidet MA", "Kerze schneidet EMA20", "EMA5 schneidet EMA20"]
ANZEIGE = ["Name", "Ticker", "Kurs", "Abstand EMA200 %", "Signale"]
TAGE = {"3 Monate": 63, "6 Monate": 126, "1 Jahr": 252}
BLOCK = 50  # Aktien pro Download-Paket

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


NAMENSTEILE = {"ag", "se", "kgaa", "sa", "s.a.", "gmbh", "co.", "co", "&", "kg", "n.v.",
               "plc", "holding", "stiftung", "group", "und", "vz.", "vz", "inc."}


def loese_ticker(name):
    """Sucht zum Firmennamen das Xetra-Kürzel (.DE) bei Yahoo."""
    kern = " ".join(w for w in name.split() if w.lower().strip(",.") not in NAMENSTEILE) or name
    erstes = kern.split()[0].lower()
    try:
        treffer = yf.Search(kern, max_results=8, news_count=0).quotes
    except Exception:
        return None
    for q in treffer:
        text = f"{q.get('longname', '')} {q.get('shortname', '')}".lower()
        if str(q.get("symbol", "")).endswith(".DE") and erstes[:5] in text:
            return q["symbol"]
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def index_laden(markt):
    """MDAX/SDAX: Namen von Wikipedia, Kürzel per Yahoo-Suche. Gibt (gefunden, nicht gefunden) zurück."""
    r = requests.get(DE_WIKI[markt], headers={"User-Agent": "Mozilla/5.0 (aktien-scanner)"}, timeout=20)
    r.raise_for_status()
    namen = []
    for t in pd.read_html(io.StringIO(r.text)):
        spalte = next((c for c in ("Name", "Unternehmen") if c in t.columns), None)
        if spalte and 40 <= len(t) <= 90:
            namen = [re.sub(r"\[.*?\]", "", str(n)).strip() for n in t[spalte].dropna()]
            break
    if not namen:
        raise ValueError("Tabelle nicht gefunden")
    gefunden, fehlt = {}, []
    for n in namen:
        sym = loese_ticker(n)
        if sym:
            gefunden[sym] = n
        else:
            fehlt.append(n)
    return gefunden, fehlt


@st.cache_data(ttl=86400, show_spinner=False)
def liste(markt):
    """Ticker -> Name. S&P 500 und Nasdaq-100 werden aktuell von Wikipedia gelesen."""
    if markt in STATISCH:
        return STATISCH[markt]
    if markt in DE_WIKI:
        return index_laden(markt)[0]
    url, sym, nam = WIKI[markt]
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (aktien-scanner)"}, timeout=20)
    r.raise_for_status()
    for t in pd.read_html(io.StringIO(r.text)):
        if sym in t.columns and nam in t.columns:
            t = t[[sym, nam]].dropna()
            return {str(s).strip().replace(".", "-"): str(n).strip()
                    for s, n in zip(t[sym], t[nam])}
    raise ValueError("Tabelle nicht gefunden")


@st.cache_resource(ttl=3600, show_spinner=False)
def lade_block(tickers):
    roh = yf.download(list(tickers), period="2y", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    out = {}
    for t in tickers:
        try:
            d = roh[t] if isinstance(roh.columns, pd.MultiIndex) else roh
            d = d[["Open", "High", "Low", "Close"]].dropna()
        except Exception:
            continue
        if len(d) >= 220:
            out[t] = d
    return out


def bloecke(markt):
    ts = list(liste(markt))
    return [tuple(ts[i:i + BLOCK]) for i in range(0, len(ts), BLOCK)]


def daten(markt):
    d = {}
    for b in bloecke(markt):
        d.update(lade_block(b))
    return d


def indikatoren(df):
    c = df["Close"]
    r = rsi(c)
    return {"c": c, "ema5": c.ewm(span=5, adjust=False).mean(),
            "ema20": c.ewm(span=20, adjust=False).mean(),
            "ema200": c.ewm(span=200, adjust=False).mean(),
            "r": r, "r_ma": r.rolling(14).mean()}


def analyse(ticker, name, df, lookback):
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


@st.cache_data(ttl=3600, show_spinner=False)
def analysiere(markt, lookback):
    d = daten(markt)
    return [analyse(t, n, d[t], lookback) for t, n in liste(markt).items() if t in d]


FIB = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]


def fib_ebenen(d):
    """Fib-Retracement auf Hoch und Tief des Zeitraums. 0 % = Ende, 100 % = Start der Bewegung."""
    hoch, tief = float(d["High"].max()), float(d["Low"].min())
    t_hoch, t_tief = d["High"].idxmax(), d["Low"].idxmin()
    aufw = t_tief < t_hoch
    spanne = hoch - tief
    ebenen = [(r, hoch - r * spanne if aufw else tief + r * spanne) for r in FIB]
    return aufw, ebenen, ((t_tief, t_hoch) if aufw else (t_hoch, t_tief))


def zeige_fib(z, tage, markt):
    d = daten(markt)[z["Ticker"]].tail(tage)
    aufw, ebenen, (start, ende) = fib_ebenen(d)
    kurs = float(d["Close"].iloc[-1])
    tab = pd.DataFrame({"Ebene": [f"{r * 100:.1f} %" for r, _ in ebenen],
                        "Kurs": [round(p, 2) for _, p in ebenen],
                        "Abstand %": [round((p / kurs - 1) * 100, 1) for _, p in ebenen]})
    naechste = min(ebenen, key=lambda e: abs(e[1] - kurs))
    richtung = "Aufwärtsbewegung" if aufw else "Abwärtsbewegung"
    st.caption(f"Fib Retracement auf der {richtung} vom {start:%d.%m.%Y} bis {ende:%d.%m.%Y} "
               f"(Hoch und Tief im gewählten Zeitraum). Nächstgelegene Ebene: {naechste[0] * 100:.1f} %.")
    st.dataframe(tab, hide_index=True, width="stretch")


def zeige_chart(z, tage, markt, fib=True):
    df = daten(markt)[z["Ticker"]]
    i = indikatoren(df)
    d = df.tail(tage)
    x = d.index
    s = lambda k: i[k].reindex(x)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(
        x=x, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
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
    if fib:
        _, ebenen, _ = fib_ebenen(d)
        for r, p in ebenen:
            wichtig = r in (0.382, 0.5, 0.618)
            fig.add_hline(y=p, row=1, col=1,
                          line=dict(dash="dot", width=1.2 if wichtig else 0.8,
                                    color="#d4a017" if wichtig else "#999999"),
                          annotation_text=f"{r * 100:.1f} %", annotation_position="top right",
                          annotation_font_size=10)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])],
                     rangeslider_visible=False, fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    fig.update_layout(height=520, margin=dict(l=4, r=4, t=36, b=4),
                      legend=dict(orientation="h", y=1.07, x=0), dragmode=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


@st.cache_resource(ttl=3600, show_spinner=False)
def lade_indizes():
    roh = yf.download(list(INDIZES.values()), period="2y", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    out = {}
    for name, t in INDIZES.items():
        try:
            c = roh[t]["Close"].dropna()
        except Exception:
            continue
        if len(c) >= 220:
            out[name] = c
    return out


def trend(c):
    """Bullish: Kurs über EMA200 und EMA5 über EMA20. Bearish: beides darunter. Sonst neutral."""
    e5 = c.ewm(span=5, adjust=False).mean().iloc[-1]
    e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
    e200 = c.ewm(span=200, adjust=False).mean().iloc[-1]
    kurs = c.iloc[-1]
    grund = (f"Kurs {'über' if kurs > e200 else 'unter'} EMA200, "
             f"EMA5 {'über' if e5 > e20 else 'unter'} EMA20")
    if kurs > e200 and e5 > e20:
        return ":green[Bullish]", grund
    if kurs < e200 and e5 < e20:
        return ":red[Bearish]", grund
    return ":orange[Neutral]", grund


def zeige_indizes():
    with st.spinner("Lade Indizes ..."):
        idx = lade_indizes()
    if not idx:
        st.warning("Keine Indexdaten geladen. Bitte später erneut versuchen.")
        return
    st.caption("Trend: Bullish = Kurs über EMA200 und EMA5 über EMA20. "
               "Bearish = beides darunter. Sonst Neutral. Beschreibung, keine Prognose.")
    for name, c in idx.items():
        j = c.tail(252)
        wandel = (j.iloc[-1] / j.iloc[0] - 1) * 100
        st.subheader(f"{name} Index")
        st.metric("Stand", f"{j.iloc[-1]:,.0f}".replace(",", "."), f"{wandel:+.1f} % in 12 Monaten")
        label, grund = trend(c)
        st.markdown(f"**Trend: {label}**")
        st.caption(grund + ".")
        ema = c.ewm(span=200, adjust=False).mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=j.index, y=j, name=name, mode="lines",
                                 line=dict(color="#1f77b4", width=2)))
        fig.add_trace(go.Scatter(x=j.index, y=ema.reindex(j.index), name="EMA200", mode="lines",
                                 line=dict(color="#ff7f0e", width=1.4, dash="dot")))
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], fixedrange=True)
        fig.update_yaxes(fixedrange=True)
        fig.update_layout(height=240, margin=dict(l=4, r=4, t=8, b=4), dragmode=False,
                          legend=dict(orientation="h", y=1.18, x=0))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"idx_{name}")


@st.cache_resource(ttl=3600, show_spinner=False)
def lade_vix():
    roh = yf.download(["^VIX"], period="2y", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    try:
        return roh["^VIX"]["Close"].dropna()
    except Exception:
        return None


def zeige_vix():
    with st.spinner("Lade VIX ..."):
        c = lade_vix()
    if c is None or len(c) < 30:
        st.warning("Keine VIX-Daten geladen. Bitte später erneut versuchen.")
        return
    j = c.tail(252)
    v = float(c.iloc[-1])
    wandel = (j.iloc[-1] / j.iloc[0] - 1) * 100
    niveau = "niedrig" if v < 15 else "mittel" if v < 25 else "hoch"
    fmt = lambda x: f"{float(x):.2f}".replace(".", ",")
    st.subheader("VIX")
    st.caption("Angstbarometer zum S&P 500. Steigt bei Unsicherheit. Kein Trendsignal.")
    st.metric("Stand", fmt(v), f"{wandel:+.1f} % in 12 Monaten")
    st.markdown(f"**Volatilität: {niveau}**")
    st.caption("Unter 15 niedrig, 15 bis 25 mittel, über 25 hoch.")
    links, rechts = st.columns(2)
    links.metric("Tief (12 Monate)", fmt(j.min()))
    rechts.metric("Hoch (12 Monate)", fmt(j.max()))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=j.index, y=j, name="VIX", mode="lines",
                             line=dict(color="#9467bd", width=2)))
    for lvl in (15, 25):
        fig.add_hline(y=lvl, line=dict(dash="dot", width=1, color="#999999"))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    fig.update_layout(height=300, margin=dict(l=4, r=4, t=8, b=4), dragmode=False, showlegend=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="vix_chart")


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

gewaehlt = None
kopf = st.columns(2)
if kopf[0].button("Index", type="primary", width="stretch", key="btn_Index"):
    gewaehlt = "Index"
if kopf[1].button("VIX", type="primary", width="stretch", key="btn_VIX"):
    gewaehlt = "VIX"
plaetze = st.columns(2) + st.columns(2) + st.columns(2)
for platz, name in zip(plaetze, MARKT_NAMEN):
    if platz.button(f"{name} scannen", type="primary", width="stretch", key=f"btn_{name}"):
        gewaehlt = name

if gewaehlt in ("Index", "VIX"):
    st.session_state["markt"] = gewaehlt
elif gewaehlt:
    try:
        with st.spinner("Lade Aktienliste ... (beim ersten MDAX- oder SDAX-Scan dauert das etwa eine Minute)"):
            pakete = bloecke(gewaehlt)
    except Exception:
        st.error("Die Aktienliste konnte nicht geladen werden. Bitte später erneut versuchen.")
        st.stop()
    balken = st.progress(0.0, text="Lade Kurse ...")
    for n, b in enumerate(pakete, 1):
        lade_block(b)
        balken.progress(n / len(pakete), text=f"Lade Kurse ... ({n}/{len(pakete)})")
    balken.empty()
    st.session_state["markt"] = gewaehlt
    st.session_state["scan_nr"] = st.session_state.get("scan_nr", 0) + 1

markt = st.session_state.get("markt")
if markt == "Index":
    zeige_indizes()
    markt = None
elif markt == "VIX":
    zeige_vix()
    markt = None
if markt:
    rows = analysiere(markt, lookback)
    if not rows:
        st.warning("Keine Daten geladen. Bitte später erneut versuchen.")
        st.stop()
    gefunden = {z["Ticker"] for z in rows}
    fehlt = [t for t in liste(markt) if t not in gefunden]
    tab = pd.DataFrame(rows)
    tab["Signale"] = tab[SIGNALE].sum(axis=1)
    treffer = tab[tab["Ueber EMA200"] & (tab["Signale"] >= min_signale)]
    treffer = treffer.sort_values(["Signale", "Abstand EMA200 %"],
                                  ascending=[False, False]).reset_index(drop=True)

    st.subheader(f"{markt}: {len(treffer)} Treffer "
                 f"({int(tab['Ueber EMA200'].sum())} von {len(tab)} über EMA200)")
    if fehlt:
        st.caption(f"Keine Daten für {len(fehlt)} Werte, zum Beispiel: " + ", ".join(fehlt[:8]))
    if markt in DE_WIKI and index_laden(markt)[1]:
        ohne = index_laden(markt)[1]
        st.caption(f"Kein Yahoo-Kürzel gefunden für {len(ohne)} Werte, zum Beispiel: " + ", ".join(ohne[:6]))
    if treffer.empty:
        st.info("Keine Treffer. Setze die Mindestanzahl Signale herunter.")
        st.stop()

    st.caption("Tippe auf eine Zeile, um den Chart zu sehen.")
    ereignis = st.dataframe(treffer[ANZEIGE], hide_index=True, width="stretch",
                            on_select="rerun", selection_mode="single-row",
                            key=f"tab_{markt}_{st.session_state.get('scan_nr', 0)}")

    buf = io.BytesIO()
    treffer.to_excel(buf, index=False)
    dateiname = markt.replace("&", "u").replace(" ", "_") + "_scan.xlsx"
    st.download_button("Als Excel speichern", buf.getvalue(), dateiname,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")

    zeilen = ereignis.selection.rows
    if zeilen:
        z = treffer.iloc[zeilen[0]].to_dict()
        st.subheader(f"{z['Name']} ({z['Ticker']})")
        zeitraum = st.radio("Zeitraum", list(TAGE), index=1, horizontal=True)
        fib = st.checkbox("Fib Retracement anzeigen", value=True)
        zeige_chart(z, TAGE[zeitraum], markt, fib)
        if fib:
            zeige_fib(z, TAGE[zeitraum], markt)
        st.markdown(bericht(z))
