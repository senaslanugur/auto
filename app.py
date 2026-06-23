import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import time

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="Ultra Tarayıcı | BİST & ABD", layout="wide")

# --- STRATEJİ PARAMETRELERİ ---
EMA_FAST = 12
EMA_SLOW = 26
RSI_LEN = 14
ATR_LEN = 14

# --- DİNAMİK VE STATİK HİSSE HAVUZLARI ---
@st.cache_data(ttl=86400) # Günde bir kez yenile (Performans için)
def get_sp500_tickers():
    """S&P 500 şirketlerini Wikipedia'dan dinamik olarak çeker."""
    try:
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        df = table[0]
        tickers = df['Symbol'].tolist()
        # Noktalı sembolleri (BRK.B) Yahoo formatına (BRK-B) çevir
        return [t.replace('.', '-') for t in tickers]
    except Exception:
        return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"] # Hata durumunda yedek liste

# Tam BİST 100 Listesi (2024 Güncel)
BIST_100 = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALFAS", "ARCLK", "ASELS", "ASTOR", "ASUZU", "AYDEM", "BAGFS", "BERA", "BIENY", "BIMAS",
    "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE", "DOHOL", "DOAS", "EGEEN",
    "ECILC", "EKGYO", "ENJSA", "ENKAI", "EREGL", "EUREN", "EUPWR", "FROTO", "GARAN", "GENIL",
    "GESAN", "GUBRF", "GWIND", "HALKB", "HEKTS", "IMASM", "INDES", "IPEKE", "ISCTR", "ISDMR",
    "ISGYO", "ISMEN", "IZENR", "KARSN", "KAYSE", "KCAER", "KCHOL", "KLSER", "KMPUR", "KONTR",
    "KONYA", "KORDS", "KOZAA", "KOZAL", "KRDMD", "KZBGY", "MAVI", "MGROS", "MIATK", "ODAS",
    "OTKAR", "OYAKC", "PENTA", "PETKM", "PGSUS", "PNLSN", "QUAGR", "SAHOL", "SASA", "SISE",
    "SKBNK", "SMRTG", "SOKM", "TATEN", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB",
    "TTKOM", "TRAKYA", "TUKAS", "TUPRS", "ULKER", "VAKBN", "VESBE", "VESTL", "YKBNK", "YYLGD"
]

def calculate_indicators(df):
    """Pandas ile teknik indikatörleri hesaplar."""
    df['ema_fast'] = df['Close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['Close'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_LEN).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_LEN).mean()
    loss = loss.replace(0, 0.0001) 
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['tr'] = pd.concat([
        df['High'] - df['Low'], 
        abs(df['High'] - df['Close'].shift()), 
        abs(df['Low'] - df['Close'].shift())
    ], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=ATR_LEN).mean()
    
    return df

def rule_based_validation(action, rsi):
    if pd.isna(rsi): return False, "RSI Hesaplanamadı"
    if 45 <= rsi <= 55: return False, "RSI Düz (Yatay)"
    if action == "AL" and rsi > 72: return False, "Aşırı Alım"
    if action == "SAT" and rsi < 28: return False, "Aşırı Satım"
    if action == "AL" and rsi > 55: return True, "Trend Destekleniyor"
    if action == "SAT" and rsi < 45: return True, "Trend Destekleniyor"
    return False, "Momentum Yetersiz"

def analyze_batch(tickers, market_type):
    """Çoklu hisse verisini tek seferde çeker ve analiz eder."""
    valid_setups = []
    
    # BİST hisseleri için .IS takısını ayarla
    formatted_tickers = []
    for t in tickers:
        t = t.strip().upper()
        if market_type == "BİST 100 (Türkiye)" and not t.endswith(".IS"):
            formatted_tickers.append(f"{t}.IS")
        else:
            formatted_tickers.append(t)
            
    tickers_str = " ".join(formatted_tickers)
    
    try:
        # Toplu indirme (Batch Download) - Çok daha hızlı
        data = yf.download(tickers_str, period="6mo", interval="1d", group_by='ticker', progress=False)
        
        # Eğer sadece 1 hisse varsa yapı farklı döner, bu yüzden listeye çeviriyoruz
        is_single = len(formatted_tickers) == 1
        
        for idx, ticker in enumerate(formatted_tickers):
            try:
                # Hisse verisini ayır
                df = data if is_single else data[ticker]
                df = df.dropna()
                
                if len(df) < 30: # Yeterli veri yoksa atla
                    continue
                    
                df = calculate_indicators(df.copy())
                
                current = df.iloc[-1]
                previous = df.iloc[-2]
                
                bullish_crossover = (previous['ema_fast'] < previous['ema_slow']) and (current['ema_fast'] > current['ema_slow'])
                bearish_crossover = (previous['ema_fast'] > previous['ema_slow']) and (current['ema_fast'] < current['ema_slow'])
                
                action = "AL" if bullish_crossover else "SAT" if bearish_crossover else None
                
                if action:
                    price, atr, rsi = current['Close'], current['atr'], current['rsi']
                    is_valid, reason = rule_based_validation(action, rsi)
                    
                    if is_valid:
                        if action == "AL":
                            sl, tp1, tp2, tp3 = price - (atr * 1.5), price + (atr * 1.5), price + (atr * 3.0), price + (atr * 4.5)
                        else:
                            sl, tp1, tp2, tp3 = price + (atr * 1.5), price - (atr * 1.5), price - (atr * 3.0), price - (atr * 4.5)

                        display_ticker = ticker.replace('.IS', '')
                        valid_setups.append({
                            "Sembol": display_ticker,
                            "Fiyat": round(price, 2),
                            "Sinyal": action,
                            "RSI": round(rsi, 2),
                            "Nedeni": reason,
                            "SL": round(sl, 2),
                            "TP1": round(tp1, 2),
                            "TP2": round(tp2, 2),
                            "TP3": round(tp3, 2)
                        })
            except Exception:
                continue # Hatalı hisseyi atla
                
        return valid_setups
    except Exception as e:
        st.error(f"Veri çekme hatası: {str(e)}")
        return []

# --- STREAMLIT ARAYÜZÜ ---
st.title("⚡ Ultra Pazar Tarayıcı (Screener)")
st.markdown("BİST 100 ve S&P 500 uçtan uca tarama motoru. Batch Processing yöntemi ile limitlere takılmadan yüzlerce hisseyi analiz eder.")
st.markdown("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Tarama Ayarları")
    market_selection = st.radio("Piyasa Seçimi:", ["BİST 100 (Türkiye)", "S&P 500 (ABD)", "Kendi Listem"])
    
    if market_selection == "BİST 100 (Türkiye)":
        ticker_input = st.text_area("Hisse Kodları (Otomatik Dolduruldu)", value=", ".join(BIST_100), height=200)
    elif market_selection == "S&P 500 (ABD)":
        with st.spinner("S&P 500 listesi çekiliyor..."):
            sp500_list = get_sp500_tickers()
        ticker_input = st.text_area("Hisse Kodları (Otomatik Dolduruldu)", value=", ".join(sp500_list), height=200)
    else:
        ticker_input = st.text_area("Hisse Kodlarını Girin (Virgülle ayırın)", value="", height=200)
    
    scan_btn = st.button("🚀 Kapsamlı Taramayı Başlat", type="primary", use_container_width=True)

with col2:
    if scan_btn:
        tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]
        
        if not tickers:
            st.warning("Lütfen taranacak hisse kodlarını girin.")
        else:
            st.info(f"**{len(tickers)}** adet hisse taranıyor. Veriler paket halinde (batch) indiriliyor, lütfen bekleyin...")
            
            start_time = time.time()
            with st.spinner('Matematiksel modeller çalıştırılıyor...'):
                results = analyze_batch(tickers, market_selection)
            end_time = time.time()
            
            if not results:
                st.warning("Bu havuzdaki hiçbir hissede şu an EMA 12/26 kesişimi ve RSI onayı bulunamadı.")
            else:
                st.success(f"Tarama {round(end_time - start_time, 1)} saniyede tamamlandı! **{len(results)}** adet işlem fırsatı bulundu.")
                
                df_results = pd.DataFrame(results)
                st.dataframe(df_results[['Sembol', 'Sinyal', 'Fiyat', 'RSI', 'Nedeni']], use_container_width=True)
                
                st.markdown("### 🎯 ATR Risk Yönetim Paneli")
                
                for setup in results:
                    color = "🟢" if setup['Sinyal'] == "AL" else "🔴"
                    with st.expander(f"{color} {setup['Sembol']} | İşlem Yönü: {setup['Sinyal']} | Fiyat: {setup['Fiyat']}"):
                        risk_data = {
                            "Seviye": ["Zarar Durdur (SL)", "Kar Al 1 (TP1)", "Kar Al 2 (TP2)", "Kar Al 3 (TP3)"],
                            "Hedef Fiyat": [setup['SL'], setup['TP1'], setup['TP2'], setup['TP3']]
                        }
                        st.table(pd.DataFrame(risk_data))
