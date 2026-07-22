# TorqPro_24

Cıvatalı bağlantı mühendisliği ve sıkma güvencesi platformu (FastAPI + SQLite + tek sayfa PWA).
Mevcut hesap kabiliyeti bir **mühendislik ön değerlendirmesidir**; onaylı VDI 2230 çözücüsü değildir.
****
## Current Development Status

- ✅ Phase 2.4.1A — Thread Engineering Database
- ✅ Phase 2.4.1B — Bolt & Nut Engineering Database
- ✅ Phase 2.4.1C — Washer & Joint Hardware Engineering Database
- ✅ Phase 2.4.2 — Library Runtime Reliability / Schema Completion
- ✅ Phase 2.5A — Production Validation Foundation (joint prerequisite +
  measurement data model; process capability math not yet implemented)
  
## Kurulum ve çalıştırma

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export TORQPRO_SECRET_KEY="<en az 32 karakter rastgele anahtar>"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Windows hızlı başlatma: `TorqPro_24_Baslat.bat` · Varsayılan giriş: `Protype Lab / A1234` (ilk girişten sonra değiştirin).

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

Testler `TORQPRO_DB_PATH` üzerinden geçici, izole bir veritabanı kullanır (`tests/conftest.py`).

## Ortam değişkenleri

| Değişken | Amaç |
|---|---|
| `TORQPRO_SECRET_KEY` | JWT imzalama anahtarı (üretimde zorunlu, ≥32 karakter) |
| `TORQPRO_DB_PATH` | SQLite dosya yolu (varsayılan: depo kökünde `torqpro.db`) |

## Dokümantasyon

Kaynak-of-truth `docs/` klasörüdür. Okuma sırası: `docs/README.md` → `docs/12_CLAUDE_CONTEXT.md` → SDS dokümanları (00–15) → ADR'ler.
Kod ile dokümantasyon çeliştiğinde uygulama durdurulur ve ADR/değişiklik talebi açılır.

## Sürüm

Uygulama sürümü tek kaynaktan yönetilir: `backend/app.py` içindeki `APP_VERSION`.
