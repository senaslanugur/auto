import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =============================================================================
# 1. KONFİGÜRASYONLAR
# =============================================================================
st.set_page_config(page_title="Ultra Otonom Kantitatif Tarayıcı", layout="wide")

MARKET_CONFIGS = {
    "Türkiye (BİST)": {"tv_market": "turkey", "yf_suffix": ".IS", "tv_prefix": "BIST:", "index_ticker": "XU100.IS"},
    "Amerika (ABD)": {"tv_market": "america", "yf_suffix": "", "tv_prefix": "NASDAQ:", "index_ticker": "SPY"}
}

EMA_FAST = 12
EMA_SLOW = 26
RSI_LEN = 14
ATR_LEN = 14

# =============================================================================
# 2. VERİ ÇEKME & PİYASA REJİMİ MOTORU
# =============================================================================
def get_all_market_symbols(mkt_config, limit=500):
    """TradingView tarayıcısından piyasa değerine göre en büyük hisseleri çeker."""
    url = f"https://scanner.tradingview.com/{mkt_config['tv_market']}/scan"
    payload = {
        "filter": [{"left": "type", "operation": "in_range", "right": ["stock"]}],
        "options": {"lang": "en"}, 
        "markets": [mkt_config['tv_market']],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "market_cap_basic"],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, 
        "range": [0, limit] 
    }
    try:
        resp = requests.post(url, json=payload, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code == 200: 
            return [item["d"][0] for item in resp.json().get("data", [])]
    except Exception as e:
        st.error(f"TradingView API Hatası: {e}")
    return []

def check_market_regime(index_ticker):
    """Ana endeksin trendini (Boğa/Ayı) belirler."""
    try:
        df = yf.download(index_ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return True, "Endeks Verisi Alınamadı (Pas Geçildi)"
        
        df['ema20'] = df['Close'].ewm(span=20, adjust=False).mean()
        current_close = float(df['Close'].iloc[-1])
        current_ema = float(df['ema20'].iloc[-1])
        
        if current_close > current_ema:
            return True, f"🟢 BOĞA REJİMİ ({index_ticker} > EMA 20)"
        else:
            return False, f"🔴 AYI REJİMİ ({index_ticker} < EMA 20)"
    except:
        return True, "Bağlantı Hatası (Sistem Açık Tutuldu)"

# =============================================================================
# 3. KANTİTATİF ANALİZ VE ÇOKLU TEYİT
# =============================================================================
def calculate_indicators(df):
    # EMA, RSI ve ATR
    df['ema_fast'] = df['Close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['Close'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_LEN).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_LEN).mean()
    loss = loss.replace(0, 0.0001) 
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    df['tr'] = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=ATR_LEN).mean()
    
    # YENİ: Makro Trend (SMA 200)
    df['sma_200'] = df['Close'].rolling(window=200).mean()
    
    # YENİ: MACD (12, 26, 9)
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # YENİ: Göreceli Hacim (Relative Volume)
    df['vol_avg_10'] = df['Volume'].rolling(window=10).mean()
    
    return df

def rule_based_validation(action, row, is_bull_market):
    """Sertleştirilmiş Kurumsal Çoklu Teyit Algoritması"""
    price, rsi = row['Close'], row['rsi']
    sma200, macd, macd_sig = row['sma_200'], row['macd'], row['macd_signal']
    vol, vol_avg = row['Volume'], row['vol_avg_10']
    
    if pd.isna(sma200): return False, "Yetersiz Veri (<200 Gün)"
    if vol_avg == 0: return False, "Hacim Verisi Yok"

    # 1. Piyasa Rejimi (Endeks onayı yoksa long işlem yasak)
    if action == "AL" and not is_bull_market:
        return False, "Endeks Ayı Piyasasında"
        
    # 2. Yatay Piyasa ve Aşırı Uçlar Filtresi
    if 45 <= rsi <= 55: return False, "Yatay Piyasa (Momentum Yok)"
    if action == "AL" and rsi > 75: return False, "Aşırı Alım Bölgesi"
    if action == "SAT" and rsi < 25: return False, "Aşırı Satım Bölgesi"

    # 3. Yönlü Çoklu Teyit (Trend, Hacim ve MACD)
    vol_ratio = vol / vol_avg
    
    if action == "AL":
        if price < sma200: return False, "Makro Düşüş Trendi (Fiyat < SMA200)"
        if macd < macd_sig: return False, "MACD Onayı Yok"
        if vol_ratio < 1.5: return False, f"Hacim Yetersiz (Oran: {vol_ratio:.1f}x)"
        if rsi <= 55: return False, "RSI Gücü Yetersiz"
        return True, "Güçlü AL (Kesişim + Hacim + MACD)"
        
    else: # SAT
        if price > sma200: return False, "Makro Yükseliş Trendi (Fiyat > SMA200)"
        if macd > macd_sig: return False, "MACD Onayı Yok"
        if vol_ratio < 1.5: return False, f"Hacim Yetersiz (Oran: {vol_ratio:.1f}x)"
        if rsi >= 45: return False, "RSI Düşüş Gücü Yetersiz"
        return True, "Güçlü SAT (Kesişim + Hacim + MACD)"

# =============================================================================
# 4. GÖRSELLEŞTİRME (PLOTLY)
# =============================================================================
def plot_setup(df, ticker, action):
    df_plot = df.tail(120) 
    
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.04, 
                        subplot_titles=(f"{ticker} Fiyat, Ortalamalar & SMA 200", "İşlem Hacmi (10G Ortalama Teyidi)", "RSI (14) Momentum"),
                        row_width=[0.2, 0.2, 0.6])

    # 1. Fiyat ve Ortalamalar
    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name="Fiyat"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['ema_fast'], line=dict(color='#3b82f6', width=1.5), name=f"EMA {EMA_FAST}"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['ema_slow'], line=dict(color='#f59e0b', width=1.5), name=f"EMA {EMA_SLOW}"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['sma_200'], line=dict(color='#e2e8f0', width=2, dash='dash'), name="SMA 200"), row=1, col=1)
    
    # 2. Hacim
    colors = ['#10b981' if row['Close'] >= row['Open'] else '#ef4444' for _, row in df_plot.iterrows()]
    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=colors, name="Hacim"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['vol_avg_10'], line=dict(color='#f472b6', width=1.5), name="10G Ort. Hacim"), row=2, col=1)

    # 3. RSI
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['rsi'], line=dict(color='#8b5cf6', width=2), name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#10b981", row=3, col=1)
    fig.add_hline(y=50, line_dash="dash", line_color="gray", row=3, col=1)

    signal_date = df_plot.index[-1]
    y_pos = df_plot['Low'].iloc[-1] * 0.96 if action == "AL" else df_plot['High'].iloc[-1] * 1.04
    color = "#10b981" if action == "AL" else "#ef4444"
    fig.add_annotation(x=signal_date, y=y_pos, text=f"{'🟢 AL' if action=='AL' else '🔴 SAT'} ONAYI", showarrow=True, arrowhead=1, arrowcolor=color, row=1, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=800, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# =============================================================================
# 5. OTONOM TARAMA MANTILIĞI (CHUNKING MİMARİSİ)
# =============================================================================
def analyze_auto_batch(mkt_key):
    valid_setups = []
    mkt_config = MARKET_CONFIGS[mkt_key]
    
    # 1. Piyasa Rejimi Kontrolü
    st.info(f"Adım 1: {mkt_config['index_ticker']} Makro Endeks Rejimi Analiz Ediliyor...")
    is_bull_market, regime_msg = check_market_regime(mkt_config['index_ticker'])
    
    if is_bull_market:
        st.success(regime_msg)
    else:
        st.warning(regime_msg + " (Sadece SAT sinyallerine veya istisnai AL sinyallerine izin verilecek)")

    # 2. Sembol Havuzu
    st.info("Adım 2: TradingView'dan hisse havuzu çekiliyor...")
    tv_symbols = get_all_market_symbols(mkt_config, limit=500)
    if not tv_symbols: return []
        
    yf_tickers = [f"{s.replace('.', '-')}{mkt_config['yf_suffix']}" for s in tv_symbols]
    total_symbols = len(yf_tickers)
    
    st.info(f"Adım 3: {total_symbols} hissenin 1 YILLIK verisi (SMA 200 için) 100'erli paketler halinde indiriliyor...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Chunking (Paketleme) İşlemi: Yfinance timeout'u önlemek için
    chunk_size = 100
    processed_count = 0
    
    for i in range(0, total_symbols, chunk_size):
        chunk_tickers = yf_tickers[i:i+chunk_size]
        status_text.text(f"Paket indiriliyor: {i} - {i+len(chunk_tickers)} / {total_symbols}...")
        
        # SMA 200 hesaplayabilmek için veriyi 1 yıla çıkardık (period="1y")
        data = yf.download(" ".join(chunk_tickers), period="1y", interval="1d", group_by='ticker', progress=False)
        
        for ticker in chunk_tickers:
            try:
                df = data[ticker].dropna() if len(chunk_tickers) > 1 else data.dropna()
                if len(df) < 200: # SMA 200 için en az 200 gün veri lazım
                    processed_count += 1
                    continue
                    
                df = calculate_indicators(df.copy())
                current, previous = df.iloc[-1], df.iloc[-2]
                
                bullish = (previous['ema_fast'] < previous['ema_slow']) and (current['ema_fast'] > current['ema_slow'])
                bearish = (previous['ema_fast'] > previous['ema_slow']) and (current['ema_fast'] < current['ema_slow'])
                
                action = "AL" if bullish else "SAT" if bearish else None
                
                if action:
                    is_valid, reason = rule_based_validation(action, current, is_bull_market)
                    
                    if is_valid:
                        price, atr = current['Close'], current['atr']
                        sl = price - (atr * 1.5) if action == "AL" else price + (atr * 1.5)
                        tp1 = price + (atr * 1.5) if action == "AL" else price - (atr * 1.5)
                        tp2 = price + (atr * 3.0) if action == "AL" else price - (atr * 3.0)
                        
                        display_symbol = ticker.replace(mkt_config['yf_suffix'], '')
                        valid_setups.append({
                            "Sembol": display_symbol,
                            "Sinyal": action,
                            "Fiyat": round(price, 2),
                            "Hacim Katsayısı": f"{current['Volume'] / current['vol_avg_10']:.1f}x",
                            "Nedeni": reason,
                            "SL": round(sl, 2),
                            "TP1": round(tp1, 2),
                            "TP2": round(tp2, 2),
                            "Dataframe": df,
                            "TV_Link": f"https://www.tradingview.com/chart/?symbol={mkt_config['tv_prefix']}{display_symbol}"
                        })
            except:
                pass
            
            processed_count += 1
            progress_bar.progress(processed_count / total_symbols)

    status_text.empty()
    progress_bar.empty()
    return valid_setups

# =============================================================================
# 6. KULLANICI ARAYÜZÜ (UI)
# =============================================================================
st.title("🛡️ Profesyonel Kantitatif Tarayıcı (Çoklu Teyit Motoru)")
st.markdown("Piyasa rejimini analiz eder, sahte sinyalleri eler ve yalnızca SMA 200, MACD ve Hacim onayı alan kusursuz kesişimleri bulur.")
st.markdown("---")

col_mkt, col_btn = st.columns([2, 1])
with col_mkt:
    selected_market = st.radio("Taranacak Piyasayı Seçin:", list(MARKET_CONFIGS.keys()), horizontal=True)
with col_btn:
    st.write("##")
    start_scan = st.button("🚀 FİLTRELİ TARAMAYI BAŞLAT", type="primary", use_container_width=True)

if start_scan:
    start_time = time.time()
    results = analyze_auto_batch(selected_market)
    
    if not results:
        st.warning("Bu piyasada şu an sistemin katı çoklu onay kurallarını (SMA 200 + MACD + Hacim + RSI) geçen hiçbir hisse bulunamadı. Piyasa şu an işleme girmek için riskli olabilir.")
    else:
        st.success(f"Tarama {round(time.time() - start_time, 1)} saniyede tamamlandı! Kesin Onaylı **{len(results)}** işlem fırsatı bulundu.")
        
        for setup in results:
            st.markdown("---")
            col_info, col_chart = st.columns([1, 2])
            
            with col_info:
                color = "🟢" if setup['Sinyal'] == "AL" else "🔴"
                st.subheader(f"{color} {setup['Sembol']}")
                st.metric("İşlem Yönü", setup['Sinyal'])
                st.metric("Giriş Fiyatı", setup['Fiyat'])
                st.metric("Hacim Şoku (Kurumsal)", setup['Hacim Katsayısı'], delta=setup['Nedeni'], delta_color="normal" if setup['Sinyal'] == "AL" else "inverse")
                
                st.markdown("**Matematiksel Risk (ATR)**")
                st.code(f"Stop Loss (SL): {setup['SL']}\nKar Al (TP1)  : {setup['TP1']}\nKar Al (TP2)  : {setup['TP2']}")
                
                st.link_button("📈 TradingView Grafiği", setup['TV_Link'], use_container_width=True)

            with col_chart:
                fig = plot_setup(setup['Dataframe'], setup['Sembol'], setup['Sinyal'])
                st.plotly_chart(fig, use_container_width=True)
