import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="BİST Teknik Analiz ve Sinyal Tarayıcı", layout="wide")

# --- STRATEJİ PARAMETRELERİ ---
EMA_FAST = 12
EMA_SLOW = 26
RSI_LEN = 14
ATR_LEN = 14

def calculate_indicators(df):
    """Pandas ile teknik indikatörleri hesaplar."""
    # EMA Hesaplamaları
    df['ema_fast'] = df['Close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['Close'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    # RSI Hesaplaması
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_LEN).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_LEN).mean()
    loss = loss.replace(0, 0.0001) # Sıfıra bölünme hatasını önle
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR Hesaplaması
    df['tr'] = pd.concat([
        df['High'] - df['Low'], 
        abs(df['High'] - df['Close'].shift()), 
        abs(df['Low'] - df['Close'].shift())
    ], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=ATR_LEN).mean()
    
    return df

def rule_based_validation(action, rsi):
    """
    Eski koddaki LLM promptunu algoritmik kurallara çevirir.
    RSI momentumuna göre sinyalin geçerliliğini kontrol eder.
    """
    if pd.isna(rsi):
        return False, "RSI Hesaplanamadı"
        
    if 45 <= rsi <= 55:
        return False, "RSI Düz (Yatay Piyasa)"
        
    if action == "AL" and rsi > 72:
        return False, "Aşırı Alım Bölgesi"
        
    if action == "SAT" and rsi < 28:
        return False, "Aşırı Satım Bölgesi"
        
    if action == "AL" and rsi > 55:
        return True, "Trend Destekleniyor (AL)"
        
    if action == "SAT" and rsi < 45:
        return True, "Trend Destekleniyor (SAT)"
        
    return False, "Momentum Yetersiz"

def analyze_stock(ticker):
    """Hisse verisini çeker, sinyalleri arar ve risk parametrelerini belirler."""
    # BİST hisseleri için .IS takısını otomatik ekle
    yf_ticker = f"{ticker.upper()}.IS" if not ticker.upper().endswith(".IS") else ticker.upper()
    
    try:
        # Son 6 aylık günlük veriyi çek
        data = yf.download(yf_ticker, period="6mo", interval="1d", progress=False)
        
        if data.empty:
            return None, "Veri bulunamadı. Lütfen hisse kodunu kontrol edin."
            
        # Eğer yfinance multi-index döndürürse düzelt
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
            
        df = calculate_indicators(data)
        
        # Son iki günü alarak kesişim kontrolü
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        bullish_crossover = (previous['ema_fast'] < previous['ema_slow']) and (current['ema_fast'] > current['ema_slow'])
        bearish_crossover = (previous['ema_fast'] > previous['ema_slow']) and (current['ema_fast'] < current['ema_slow'])
        
        action = None
        if bullish_crossover:
            action = "AL"
        elif bearish_crossover:
            action = "SAT"
            
        price = current['Close']
        atr = current['atr']
        rsi = current['rsi']
        ema_f = current['ema_fast']
        ema_s = current['ema_slow']
        
        result = {
            "Tarih": df.index[-1].strftime('%Y-%m-%d'),
            "Fiyat": price,
            "RSI": rsi,
            "EMA_12": ema_f,
            "EMA_26": ema_s,
            "Sinyal": action if action else "SİNYAL YOK",
            "Geçerlilik": "-",
            "Nedeni": "Kesişim Bekleniyor",
            "SL": "-", "TP1": "-", "TP2": "-", "TP3": "-"
        }
        
        # Sinyal varsa validasyon ve risk seviyelerini hesapla
        if action:
            is_valid, reason = rule_based_validation(action, rsi)
            result["Geçerlilik"] = "✅ ONAYLANDI" if is_valid else "❌ REDDEDİLDİ"
            result["Nedeni"] = reason
            
            # Dinamik ATR Hedefleri
            if action == "AL":
                result["SL"] = price - (atr * 1.5)
                result["TP1"] = price + (atr * 1.5)
                result["TP2"] = price + (atr * 3.0)
                result["TP3"] = price + (atr * 4.5)
            else:
                result["SL"] = price + (atr * 1.5)
                result["TP1"] = price - (atr * 1.5)
                result["TP2"] = price - (atr * 3.0)
                result["TP3"] = price - (atr * 4.5)

        return result, df
        
    except Exception as e:
        return None, f"Sistem hatası: {str(e)}"

# --- STREAMLIT ARAYÜZÜ ---
st.title("📊 BİST Algoritmik Tarayıcı")
st.markdown("API bağlantısı olmadan **EMA 12/26 Kesişimi**, **RSI Momentum Filtresi** ve **Dinamik ATR Risk Yönetimi** ile Türkiye borsası hisse analizi.")

st.markdown("---")

col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("Hisse Seçimi")
    ticker_input = st.text_input("BİST Hisse Kodu (Örn: THYAO, ASELS, TUPRS):", value="THYAO")
    analyze_btn = st.button("Analiz Et", type="primary")

if analyze_btn:
    with st.spinner(f'{ticker_input} verileri analiz ediliyor...'):
        analysis_result, df_or_error = analyze_stock(ticker_input)
        
        if analysis_result is None:
            st.error(df_or_error)
        else:
            with col2:
                st.subheader(f"{ticker_input.upper()} - Güncel Durum Raporu")
                
                # Metrik Kartları
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Kapanış Fiyatı", f"₺{analysis_result['Fiyat']:.2f}")
                m2.metric("RSI (14)", f"{analysis_result['RSI']:.2f}")
                m3.metric("EMA 12", f"{analysis_result['EMA_12']:.2f}")
                m4.metric("EMA 26", f"{analysis_result['EMA_26']:.2f}")
                
                st.markdown("### 🎯 İşlem Sinyali ve Risk Yönetimi")
                
                if analysis_result['Sinyal'] == "SİNYAL YOK":
                    st.info("Şu an için güncel bir EMA kesişimi bulunmamaktadır. Mevcut trend devam ediyor.")
                else:
                    # Sinyal onay durumuna göre renk ve kutu belirleme
                    if "ONAYLANDI" in analysis_result['Geçerlilik']:
                        st.success(f"**SİNYAL:** {analysis_result['Sinyal']} | **DURUM:** {analysis_result['Geçerlilik']} ({analysis_result['Nedeni']})")
                        
                        # Stop Loss ve Take Profit Tablosu
                        risk_data = {
                            "Seviye": ["Zarar Durdur (SL)", "Kar Al 1 (TP1)", "Kar Al 2 (TP2)", "Kar Al 3 (TP3)"],
                            "Fiyat (₺)": [
                                f"{analysis_result['SL']:.2f}",
                                f"{analysis_result['TP1']:.2f}",
                                f"{analysis_result['TP2']:.2f}",
                                f"{analysis_result['TP3']:.2f}"
                            ]
                        }
                        st.table(pd.DataFrame(risk_data))
                    else:
                        st.warning(f"**SİNYAL:** {analysis_result['Sinyal']} | **DURUM:** {analysis_result['Geçerlilik']} ({analysis_result['Nedeni']})")
                        st.write("Yapay Zeka kural seti, bu piyasa koşulunda işleme girilmesini riskli buldu.")

            # Geçmiş Veri Önizlemesi
            st.markdown("---")
            st.markdown("### 📈 Son 5 Günlük Teknik Veri Önizlemesi")
            display_df = df_or_error.tail(5)[['Close', 'ema_fast', 'ema_slow', 'rsi', 'atr']].copy()
            display_df.columns = ['Kapanış', 'EMA 12', 'EMA 26', 'RSI', 'ATR']
            st.dataframe(display_df.style.format("{:.2f}"))
