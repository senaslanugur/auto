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
st.set_page_config(page_title="Tam Otonom Algoritmik Tarayıcı", layout="wide")

MARKET_CONFIGS = {
    "Türkiye (BİST)": {"tv_market": "turkey", "yf_suffix": ".IS", "tv_prefix": "BIST:"},
    "Amerika (ABD)": {"tv_market": "america", "yf_suffix": "", "tv_prefix": "NASDAQ:"} # NASDAQ/NYSE ortak arama için prefix
}

EMA_FAST = 12
EMA_SLOW = 26
RSI_LEN = 14
ATR_LEN = 14

# =============================================================================
# 2. VERİ ÇEKME MOTORU (TRADINGVIEW API)
# =============================================================================
def get_all_market_symbols(mkt_config, limit=600):
    """TradingView tarayıcısından piyasa değerine göre en büyük hisseleri çeker."""
    url = f"https://scanner.tradingview.com/{mkt_config['tv_market']}/scan"
    payload = {
        "filter": [{"left": "type", "operation": "in_range", "right": ["stock"]}],
        "options": {"lang": "en"}, 
        "markets": [mkt_config['tv_market']],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "market_cap_basic"],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, 
        "range": [0, limit] # Hız ve stabilite için ilk 600 hisse
    }
    try:
        resp = requests.post(url, json=payload, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code == 200: 
            return [item["d"][0] for item in resp.json().get("data", [])]
    except Exception as e:
        st.error(f"TradingView API Hatası: {e}")
    return []

# =============================================================================
# 3. KANTİTATİF ANALİZ VE RİSK YÖNETİMİ
# =============================================================================
def calculate_indicators(df):
    df['ema_fast'] = df['Close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['Close'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_LEN).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_LEN).mean()
    loss = loss.replace(0, 0.0001) 
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    df['tr'] = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=ATR_LEN).mean()
    return df

def rule_based_validation(action, rsi):
    if pd.isna(rsi): return False, "Hesaplanamadı"
    if 45 <= rsi <= 55: return False, "Yatay Piyasa"
    if action == "AL" and rsi > 72: return False, "Aşırı Alım"
    if action == "SAT" and rsi < 28: return False, "Aşırı Satım"
    if action == "AL" and rsi > 55: return True, "Trend Onayı"
    if action == "SAT" and rsi < 45: return True, "Trend Onayı"
    return False, "Momentum Yetersiz"

# =============================================================================
# 4. GÖRSELLEŞTİRME (PLOTLY)
# =============================================================================
def plot_setup(df, ticker, action):
    df_plot = df.tail(100) # Son 100 işlem gününü göster
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f"{ticker} Fiyat & EMA Sinyali", "Momentum (RSI 14)"),
                        row_width=[0.3, 0.7])

    # Fiyat Mumları
    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
                                 low=df_plot['Low'], close=df_plot['Close'], name="Fiyat"), row=1, col=1)
    
    # Hareketli Ortalamalar
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['ema_fast'], line=dict(color='#3b82f6', width=1.5), name=f"EMA {EMA_FAST}"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['ema_slow'], line=dict(color='#f59e0b', width=1.5), name=f"EMA {EMA_SLOW}"), row=1, col=1)
    
    # RSI Grafiği
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['rsi'], line=dict(color='#8b5cf6', width=2), name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#10b981", row=2, col=1)
    fig.add_hline(y=50, line_dash="dash", line_color="gray", row=2, col=1)

    # Sinyal Noktası
    signal_date = df_plot.index[-1]
    if action == "AL":
        fig.add_annotation(x=signal_date, y=df_plot['Low'].iloc[-1] * 0.98, text="🟢 AL GİRİŞİ", showarrow=True, arrowhead=1, arrowcolor="#10b981", row=1, col=1)
    else:
        fig.add_annotation(x=signal_date, y=df_plot['High'].iloc[-1] * 1.02, text="🔴 SAT GİRİŞİ", showarrow=True, arrowhead=1, arrowcolor="#ef4444", row=1, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# =============================================================================
# 5. OTONOM TARAMA MANTILIĞI
# =============================================================================
def analyze_auto_batch(mkt_key):
    valid_setups = []
    mkt_config = MARKET_CONFIGS[mkt_key]
    
    st.info("Adım 1: TradingView'dan hisse havuzu çekiliyor...")
    tv_symbols = get_all_market_symbols(mkt_config, limit=600)
    
    if not tv_symbols:
        return []
        
    # Yahoo Finance formatına çevir (Noktaları tire yap, uzantıyı ekle)
    yf_tickers = []
    for s in tv_symbols:
        clean_s = s.replace('.', '-')
        yf_tickers.append(f"{clean_s}{mkt_config['yf_suffix']}")
        
    st.info(f"Adım 2: {len(yf_tickers)} hissenin 6 aylık verisi tek seferde indiriliyor (Toplu İşlem)...")
    
    # Çoklu indirme
    data = yf.download(" ".join(yf_tickers), period="6mo", interval="1d", group_by='ticker', progress=False)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_symbols = len(yf_tickers)
    
    for i, ticker in enumerate(yf_tickers):
        status_text.text(f"Algoritma Çalışıyor: {ticker} ({i+1}/{total_symbols})")
        try:
            # Çoklu indirme yapısına göre dataframe'i seç
            df = data[ticker].dropna() if total_symbols > 1 else data.dropna()
            
            if len(df) < 50: 
                continue
                
            df = calculate_indicators(df.copy())
            current, previous = df.iloc[-1], df.iloc[-2]
            
            bullish = (previous['ema_fast'] < previous['ema_slow']) and (current['ema_fast'] > current['ema_slow'])
            bearish = (previous['ema_fast'] > previous['ema_slow']) and (current['ema_fast'] < current['ema_slow'])
            
            action = "AL" if bullish else "SAT" if bearish else None
            
            if action:
                price, atr, rsi = current['Close'], current['atr'], current['rsi']
                is_valid, reason = rule_based_validation(action, rsi)
                
                if is_valid:
                    sl = price - (atr * 1.5) if action == "AL" else price + (atr * 1.5)
                    tp1 = price + (atr * 1.5) if action == "AL" else price - (atr * 1.5)
                    tp2 = price + (atr * 3.0) if action == "AL" else price - (atr * 3.0)
                    
                    display_symbol = ticker.replace(mkt_config['yf_suffix'], '')
                    
                    valid_setups.append({
                        "Sembol": display_symbol,
                        "Sinyal": action,
                        "Fiyat": round(price, 2),
                        "RSI": round(rsi, 2),
                        "Nedeni": reason,
                        "SL": round(sl, 2),
                        "TP1": round(tp1, 2),
                        "TP2": round(tp2, 2),
                        "Dataframe": df,
                        "TV_Link": f"https://www.tradingview.com/chart/?symbol={mkt_config['tv_prefix']}{display_symbol}"
                    })
        except:
            pass
        progress_bar.progress((i + 1) / total_symbols)
        
    status_text.empty()
    progress_bar.empty()
    return valid_setups

# =============================================================================
# 6. KULLANICI ARAYÜZÜ (UI)
# =============================================================================
st.title("🌐 Otonom Piyasa Tarayıcı & Analiz İstasyonu")
st.markdown("TradingView altyapısını kullanarak tüm piyasayı anlık çeker, EMA 12/26 & RSI koşullarını hesaplar ve interaktif grafikle sunar.")
st.markdown("---")

col_mkt, col_btn = st.columns([2, 1])
with col_mkt:
    selected_market = st.radio("Taranacak Piyasayı Seçin:", list(MARKET_CONFIGS.keys()), horizontal=True)
with col_btn:
    st.write("##")
    start_scan = st.button("🚀 OTONOM TARAMAYI BAŞLAT", type="primary", use_container_width=True)

if start_scan:
    start_time = time.time()
    results = analyze_auto_batch(selected_market)
    
    if not results:
        st.warning("Piyasada şu an EMA kesişimi ve RSI onayı alan bir hisse bulunamadı.")
    else:
        st.success(f"Tarama {round(time.time() - start_time, 1)} saniyede tamamlandı! **{len(results)}** adet işlem fırsatı bulundu.")
        
        for setup in results:
            st.markdown("---")
            col_info, col_chart = st.columns([1, 2])
            
            with col_info:
                color = "🟢" if setup['Sinyal'] == "AL" else "🔴"
                st.subheader(f"{color} {setup['Sembol']}")
                st.metric("İşlem Yönü", setup['Sinyal'])
                st.metric("Giriş Fiyatı", setup['Fiyat'])
                st.metric("RSI Değeri", setup['RSI'], delta=setup['Nedeni'], delta_color="normal" if setup['Sinyal'] == "AL" else "inverse")
                
                st.markdown("**Dinamik ATR Risk Yönetimi:**")
                st.code(f"Stop Loss (SL) : {setup['SL']}\nKar Al 1 (TP1)  : {setup['TP1']}\nKar Al 2 (TP2)  : {setup['TP2']}")
                
                # TradingView Dinamik Link Butonu
                st.link_button("📈 TradingView'da İncele", setup['TV_Link'], use_container_width=True)

            with col_chart:
                # Plotly interaktif grafik render
                fig = plot_setup(setup['Dataframe'], setup['Sembol'], setup['Sinyal'])
                st.plotly_chart(fig, use_container_width=True)
