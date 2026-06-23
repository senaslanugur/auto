import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import time

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="Global Algoritmik Tarayıcı", layout="wide", page_icon="📈")

# --- STRATEJİ PARAMETRELERİ ---
EMA_FAST = 12
EMA_SLOW = 26
RSI_LEN = 14
ATR_LEN = 14

# --- VARSAYILAN HİSSE LİSTELERİ ---
BIST_30 = [
    "THYAO", "ASELS", "TUPRS", "KCHOL", "AKBNK", "ISCTR", "BIMAS", "EREGL", 
    "SAHOL", "SISE", "YKBNK", "GARAN", "ENKAI", "PETKM", "HEKTS", "KRDMD"
] # Hızı artırmak için özet bir liste, kullanıcı arayüzden ekleme yapabilir.

US_TECH = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AMD", "INTC"
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
    """RSI momentumuna göre sinyalin geçerliliğini kontrol eder."""
    if pd.isna(rsi): return False, "RSI Hesaplanamadı"
    if 45 <= rsi <= 55: return False, "RSI Düz (Yatay)"
    if action == "AL" and rsi > 72: return False, "Aşırı Alım"
    if action == "SAT" and rsi < 28: return False, "Aşırı Satım"
    if action == "AL" and rsi > 55: return True, "Trend Destekleniyor"
    if action == "SAT" and rsi < 45: return True, "Trend Destekleniyor"
    return False, "Momentum Yetersiz"

def analyze_stock(ticker, market_type):
    """Tek bir hisse senedini analiz eder ve sinyal varsa döndürür."""
    # BİST seçildiyse .IS takısını ekle
    yf_ticker = f"{ticker.upper()}.IS" if market_type == "Türkiye (BİST)" and not ticker.upper().endswith(".IS") else ticker.upper()
    
    try:
        data = yf.download(yf_ticker, period="6mo", interval="1d", progress=False)
        if data.empty: return None
            
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
            
        df = calculate_indicators(data)
        
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        bullish_crossover = (previous['ema_fast'] < previous['ema_slow']) and (current['ema_fast'] > current['ema_slow'])
        bearish_crossover = (previous['ema_fast'] > previous['ema_slow']) and (current['ema_fast'] < current['ema_slow'])
        
        action = "AL" if bullish_crossover else "SAT" if bearish_crossover else None
        
        if not action: return None # Sinyal yoksa pas geç
            
        price, atr, rsi = current['Close'], current['atr'], current['rsi']
        is_valid, reason = rule_based_validation(action, rsi)
        
        if not is_valid: return None # Validasyondan geçemezse pas geç
        
        # Sinyal geçerliyse risk seviyelerini hesapla
        if action == "AL":
            sl, tp1, tp2, tp3 = price - (atr * 1.5), price + (atr * 1.5), price + (atr * 3.0), price + (atr * 4.5)
        else:
            sl, tp1, tp2, tp3 = price + (atr * 1.5), price - (atr * 1.5), price - (atr * 3.0), price - (atr * 4.5)

        return {
            "Sembol": ticker.upper(),
            "Fiyat": price,
            "Sinyal": action,
            "RSI": round(rsi, 2),
            "Nedeni": reason,
            "SL": round(sl, 2),
            "TP1": round(tp1, 2),
            "TP2": round(tp2, 2),
            "TP3": round(tp3, 2)
        }
        
    except Exception:
        return None

# --- STREAMLIT ARAYÜZÜ ---
st.title("🌐 Global Kesişim Tarayıcı (Screener)")
st.markdown("Seçilen piyasadaki hisseleri otomatik olarak tarar, **EMA 12/26** ve **RSI (14)** koşullarını sağlayanları listeler ve ATR bazlı risk hedeflerini hesaplar.")
st.markdown("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Tarama Ayarları")
    market_selection = st.radio("Piyasa Seçimi:", ["Türkiye (BİST)", "ABD Borsaları"])
    
    # Varsayılan listeyi piyasaya göre belirle
    default_list = ", ".join(BIST_30) if market_selection == "Türkiye (BİST)" else ", ".join(US_TECH)
    
    st.markdown("**Taranacak Hisseler (Virgülle ayırın):**")
    ticker_input = st.text_area("Hisse Kodları", value=default_list, height=150)
    
    scan_btn = st.button("🚀 Taramayı Başlat", type="primary", use_container_width=True)

with col2:
    if scan_btn:
        tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]
        total_tickers = len(tickers)
        
        if total_tickers == 0:
            st.warning("Lütfen en az bir hisse kodu girin.")
        else:
            st.subheader(f"Tarama Sonuçları ({market_selection})")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            valid_setups = []
            
            # Tarama Döngüsü
            for i, ticker in enumerate(tickers):
                status_text.text(f"Taranıyor: {ticker} ({i+1}/{total_tickers})")
                
                result = analyze_stock(ticker, market_selection)
                if result:
                    valid_setups.append(result)
                    
                # İlerleme çubuğunu güncelle
                progress_bar.progress((i + 1) / total_tickers)
                time.sleep(0.1) # API'ye aşırı yüklenmemek için küçük bir bekleme
                
            status_text.text("Tarama Tamamlandı!")
            
            # Sonuçları Göster
            if not valid_setups:
                st.info("Bu listedeki hisselerde şu an geçerli bir kesişim sinyali bulunamadı.")
            else:
                st.success(f"**{len(valid_setups)}** adet geçerli işlem fırsatı bulundu!")
                
                # Özet Tablo
                df_results = pd.DataFrame(valid_setups)
                st.dataframe(df_results[['Sembol', 'Sinyal', 'Fiyat', 'RSI', 'Nedeni']], use_container_width=True)
                
                st.markdown("### 🎯 Dinamik Risk Yönetimi (ATR Hedefleri)")
                
                # Her geçerli sinyal için detaylı ATR hedeflerini genişletilebilir kutularda göster
                for setup in valid_setups:
                    color = "🟢" if setup['Sinyal'] == "AL" else "🔴"
                    with st.expander(f"{color} {setup['Sembol']} - {setup['Sinyal']} Sinyali (Giriş: {setup['Fiyat']})"):
                        risk_data = {
                            "Seviye": ["Zarar Durdur (SL)", "Kar Al 1 (TP1)", "Kar Al 2 (TP2)", "Kar Al 3 (TP3)"],
                            "Fiyat": [setup['SL'], setup['TP1'], setup['TP2'], setup['TP3']]
                        }
                        st.table(pd.DataFrame(risk_data))
