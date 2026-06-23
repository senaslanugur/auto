import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="Oto-Tarayıcı & Grafik İstasyonu", layout="wide")

# --- STRATEJİ PARAMETRELERİ ---
EMA_FAST = 12
EMA_SLOW = 26
RSI_LEN = 14
ATR_LEN = 14

# --- OTOMATİK HİSSE HAVUZLARI ---
@st.cache_data(ttl=86400)
def get_us_tickers():
    """S&P 500 şirketlerini otomatik çeker."""
    try:
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        return [t.replace('.', '-') for t in table[0]['Symbol'].tolist()]
    except:
        return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"] # Yedek

@st.cache_data(ttl=86400)
def get_bist_tickers():
    """BİST Tüm hisselerinin özet listesini getirir. 
    (Tamamını çekmek yfinance'i kilitlediği için en hacimli ~150 hisse otomatik tanımlanmıştır)"""
    return [
        "THYAO", "ASELS", "TUPRS", "KCHOL", "AKBNK", "ISCTR", "BIMAS", "EREGL", "SAHOL", "SISE", 
        "YKBNK", "GARAN", "ENKAI", "PETKM", "HEKTS", "KRDMD", "SASA", "FROTO", "TOASO", "PGSUS",
        "DOAS", "MGROS", "ARCLK", "TCELL", "TTKOM", "EKGYO", "KOZAL", "KOZAA", "IPEKE", "ODAS",
        "ASTOR", "ALFAS", "SMRTG", "GESAN", "EUPWR", "CWENE", "AKSA", "VESBE", "VESTL", "AYDEM",
        "GWIND", "ENJSA", "CANTE", "QUAGR", "KCAER", "BRSAN", "MIATK", "KONTR", "YEOTK", "KMPUR"
        # Not: Gerçek bir BİST Tüm csv'niz varsa burada pd.read_csv ile okutabilirsiniz.
    ]

# --- TEKNİK HESAPLAMALAR ---
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

# --- GRAFİK ÇİZİM MOTURU (PLOTLY) ---
def plot_setup(df, ticker, action):
    """Candlestick, EMA ve RSI göstergelerini profesyonelce çizer."""
    # Son 100 mumu alarak grafiği okunaklı tutalım
    df_plot = df.tail(100)
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f"{ticker} Fiyat & EMA", "RSI (14)"),
                        row_width=[0.3, 0.7])

    # 1. Mum Grafiği
    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
                                 low=df_plot['Low'], close=df_plot['Close'], name="Fiyat"), row=1, col=1)
    
    # EMA'lar
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['ema_fast'], line=dict(color='blue', width=1.5), name=f"EMA {EMA_FAST}"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['ema_slow'], line=dict(color='orange', width=1.5), name=f"EMA {EMA_SLOW}"), row=1, col=1)
    
    # 2. RSI Grafiği
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['rsi'], line=dict(color='purple', width=2), name="RSI"), row=2, col=1)
    
    # RSI Referans Çizgileri
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
    fig.add_hline(y=50, line_dash="dash", line_color="gray", row=2, col=1)

    # Sinyal İşaretçisi (Son mumun üzerine/altına ok koy)
    signal_price = df_plot['Close'].iloc[-1]
    signal_date = df_plot.index[-1]
    
    if action == "AL":
        fig.add_annotation(x=signal_date, y=df_plot['Low'].iloc[-1] * 0.98, text="🟢 AL ONAYI", showarrow=True, arrowhead=1, arrowcolor="green", row=1, col=1)
    else:
        fig.add_annotation(x=signal_date, y=df_plot['High'].iloc[-1] * 1.02, text="🔴 SAT ONAYI", showarrow=True, arrowhead=1, arrowcolor="red", row=1, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# --- TOPLU ANALİZ ---
def analyze_auto_batch(market_type):
    valid_setups = []
    
    if market_type == "Türkiye (BİST)":
        tickers = get_bist_tickers()
        formatted_tickers = [f"{t}.IS" for t in tickers]
    else:
        tickers = get_us_tickers()
        formatted_tickers = tickers
        
    st.info(f"Sistem arka planda {len(formatted_tickers)} adet hisseyi otomatik analiz ediyor. Lütfen bekleyin...")
    
    # Veriyi Batch olarak çek
    data = yf.download(" ".join(formatted_tickers), period="6mo", interval="1d", group_by='ticker', progress=False)
    
    progress_bar = st.progress(0)
    
    for i, ticker in enumerate(formatted_tickers):
        try:
            df = data[ticker].dropna() if len(formatted_tickers) > 1 else data.dropna()
            if len(df) < 50: continue
                
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
                    
                    valid_setups.append({
                        "Sembol": ticker.replace('.IS', ''),
                        "Sinyal": action,
                        "Fiyat": round(price, 2),
                        "RSI": round(rsi, 2),
                        "Nedeni": reason,
                        "SL": round(sl, 2),
                        "TP1": round(tp1, 2),
                        "TP2": round(tp2, 2),
                        "Dataframe": df # Grafiği çizmek için df'i kaydediyoruz
                    })
        except:
            pass
        progress_bar.progress((i + 1) / len(formatted_tickers))
        
    return valid_setups

# --- ARAYÜZ ---
st.title("🤖 Tam Otomatik Algoritmik Tarayıcı & Grafik İstasyonu")
st.markdown("Hisse girmeye gerek kalmadan tüm piyasayı tarar, geçerli formasyonları bulur ve grafiklerini otomatik çizer.")
st.markdown("---")

market_selection = st.radio("Taranacak Piyasayı Seçin (Otomatik Havuz):", ["Türkiye (BİST)", "ABD Borsaları (S&P 500)"], horizontal=True)

if st.button("🚀 Piyasayı Otomatik Tara ve Grafikleri Hazırla", type="primary", use_container_width=True):
    start_time = time.time()
    results = analyze_auto_batch(market_selection)
    
    if not results:
        st.warning("Bu piyasada şu an geçerli (Onaylı) bir EMA + RSI formasyonu bulunamadı.")
    else:
        st.success(f"Tarama {round(time.time() - start_time, 1)} saniyede bitti. **{len(results)}** geçerli fırsat bulundu.")
        
        for setup in results:
            st.markdown("---")
            col1, col2 = st.columns([1, 3])
            
            with col1:
                color = "🟢" if setup['Sinyal'] == "AL" else "🔴"
                st.subheader(f"{color} {setup['Sembol']}")
                st.metric("Sinyal Yönü", setup['Sinyal'])
                st.metric("Giriş Fiyatı", setup['Fiyat'])
                st.metric("RSI Değeri", setup['RSI'], delta=setup['Nedeni'], delta_color="normal" if setup['Sinyal'] == "AL" else "inverse")
                
                st.markdown("**Risk Yönetimi:**")
                st.code(f"SL : {setup['SL']}\nTP1: {setup['TP1']}\nTP2: {setup['TP2']}")
                
                # TradingView Butonu Dinamik URL'si
                tv_symbol = f"BIST:{setup['Sembol']}" if market_selection == "Türkiye (BİST)" else f"NASDAQ:{setup['Sembol']}"
                st.link_button("📈 TradingView'da İncele", f"https://www.tradingview.com/chart/?symbol={tv_symbol}", use_container_width=True)

            with col2:
                # Arka planda kaydettiğimiz DataFrame ile anında grafik çiziyoruz
                fig = plot_setup(setup['Dataframe'], setup['Sembol'], setup['Sinyal'])
                st.plotly_chart(fig, use_container_width=True)
