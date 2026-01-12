# Polymarket Copy Trade Bot

## 🎯 Amaç
$10 sermaye ile başlayıp, profesyonel whale trader'ları kopyalayarak binlerce dolara çıkarmak.

## 🚀 Hızlı Başlangıç

```bash
# 1. Sanal ortam oluştur
python -m venv venv
venv\Scripts\activate

# 2. Bağımlılıkları yükle
pip install -r requirements.txt

# 3. .env dosyasını kopyala ve düzenle
copy .env.example .env

# 4. Botu başlat
python -m app.main
```

## 📊 Dashboard
Tarayıcıda aç: `http://localhost:8000`

## 📁 Proje Yapısı
```
copytrade/
├── app/
│   ├── main.py           # FastAPI entry point
│   ├── api/              # API clients (Polymarket, Dune)
│   ├── brain/            # Smart Brain (scorer, ranker, decider)
│   ├── engine/           # Trading engines (paper, real)
│   ├── models/           # Data models
│   └── static/           # Dashboard (HTML/JS/CSS)
├── data/                 # SQLite database
├── requirements.txt
└── .env
```

## 🧠 Özellikler
- **Smart Brain**: Whale'leri puanlar (Heat Map 0-100)
- **Paper Trading**: Sanal $1000 ile test
- **Real Trading**: Gerçek $10 ile işlem
- **Dashboard**: Gerçek zamanlı arayüz
