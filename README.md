# BİST Algoritmik Sinyal Tarayıcı 📈

Bu proje, Borsa İstanbul (BİST) hisse senetleri için geliştirilmiş, harici bir API anahtarı gerektirmeden çalışan bir teknik analiz ve sinyal tarama aracıdır.

## Özellikler
* **Veri Kaynağı:** `yfinance` (Günlük veriler)
* **İndikatörler:** EMA (12, 26), RSI (14), ATR (14)
* **Algoritma:** EMA Kesişim Stratejisi & RSI Momentum Doğrulaması
* **Risk Yönetimi:** ATR tabanlı dinamik Stop Loss (SL) ve Take Profit (TP1, TP2, TP3) seviyeleri.

## Kurulum ve Çalıştırma
Lokal ortamda çalıştırmak için:
1. Gerekli kütüphaneleri kurun: `pip install -r requirements.txt`
2. Uygulamayı başlatın: `streamlit run app.py`
