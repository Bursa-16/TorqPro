# Faz 2.8.8 — Material Intelligence, Engineering Formula Validation ve
Recommendation Engine (TR/EN)

- **Status:** Delivered
- **Date:** 2026-07-28
- **Product owner:** İlhan Çekiç
- **ADR:** `docs/adr/ADR-0012-material-intelligence-formula-validation.md`

## 1. Kapsam ve kapsam dışı

**Kapsam:** mevcut 8 `MaterialRecord` üzerinde deterministik gereksinim
eşleştirme ve karşılaştırma (Material Intelligence); mevcut
`vdi2230_core.trace` ve `formula_registry` kataloglarının salt-okunur
doğrulama raporu (Formula Validation); Faz 2.6.4 readiness-gated
felsefesini birebir izleyen, veri yeterliliğine göre kapılı bir
malzeme önerisi motoru (Recommendation Engine); tüm bunlar için
baştan itibaren TR/EN mesaj çiftleri; JSON+Markdown rapor entegrasyonu.

**Kapsam dışı:** yeni malzeme/katsayı değeri eklemek; `formula_registry`
içine somut formül kaydetmek (ayrı ADR gerektirir); herhangi bir
kaydın önerisini `comparison_only` üzerine çıkarmak; önceki fazların
(2.6.x/2.8.6/2.8.7) İngilizce serbest-metin uyarılarını TR/EN'e
çevirmek (geriye dönük değişiklik yapılmadı — additive-only kural).

## 2. Mevcut veri yeterlilik analizi

`backend/library/data/material_library.json`: 8 kayıt (Steel, Alloy
Steel, Stainless A2, Stainless A4, Titanium, Aluminium, Brass, Cast
Iron). Tümünde `confidence=3`, `validation_status="reference_only"`,
`approval_status="pending"` — tek tip. Hiçbiri sertifikalı
(lot-specific mill certificate) veri değil; hepsi "representative
property set... not a substitute for a material certificate" notuyla
işaretli. Bu, Faz 2.6.4'teki friction-condition veri gerçekliğiyle
birebir aynı yapıdadır (tek tip, üretime hazır olmayan referans veri).

## 3. Readiness seviyeleri (malzeme önerisi)

`data_insufficient` < `comparison_only` < `engineering_recommendation_ready`
< `production_recommendation_ready`.

**8/8 kayıt: `comparison_only`.** Rp0.2/Rm/E/yoğunluk sayısal ve
karşılaştırılabilir olduğundan (bkz. ADR-0012 madde 2), bu düzeyde
kayıtlar bir talebe göre **sayısal marja göre** deterministik olarak
sıralanabilir — ancak sonuç her zaman "mühendislik onayı olmadan
üretimde kullanılamaz" uyarısını taşır ve hiçbir kayıt
`engineering_recommendation_ready`/`production_recommendation_ready`
olarak işaretlenmez. Bu, `test_no_material_reaches_engineering_or_production_ready`
ile doğrudan doğrulanır.

## 4. TR/EN mesaj sözlüğü tasarımı

Her yeni uyarı/rapor mesajı `(code, tr, en)` üçlüsü olarak
`material_intelligence.py` / `formula_validation.py` içinde tek
yerde tanımlanır. API'ler ve rapor üretimi bir `lang` parametresi
alır (`"tr"` varsayılan, `"en"` kabul edilir); `Accept-Language`'dan
asla çıkarım yapılmaz. Bu, Faz 2.6.8'in frontend'de belgelenen bilinen
kısıtını ("backend warnings [have] no stable keys the frontend can
translate... out of scope") bu fazın kendi çıktısı için çözer; eski
fazların çıktısı değiştirilmez.

## 5. Formula Validation kapsamı

`formula_validation.py`, `vdi2230_core.trace.all_traces()` (7 kayıt: 2
APPROVED — `Phi`, `F_S` — 5 PROVISIONAL) ve
`formula_registry.all_formulas()` (0 kayıt, değişmedi) üzerinde
salt-okunur bir kapsam/durum raporu üretir: toplam sayı, APPROVED/
PROVISIONAL dağılımı, kaynak referansları, ve "production-ready"
formül oranı. Hiçbir formülün `validation_status`'u değiştirilmez.

## 6. API

- `GET /api/library/materials` — 8 kaydın TR/EN etiketli listesi.
- `GET /api/library/materials/{id}` — tek kayıt detay.
- `POST /api/engineering/material-recommendation` — gereksinim
  (`min_rp02_mpa`, `min_rm_mpa`, `min_elastic_modulus_mpa`,
  `material_family` filtresi) + `lang`; readiness-gated
  `MaterialRecommendationResult` döner. Yalnızca `MaterialRecord`'da
  gerçekten var olan sayısal alanlar kullanılır — sıcaklık/korozyon
  sınıfı gibi kayıtta bulunmayan alanlar için filtre eklenmedi (veri
  uydurma yasağı, `docs/12_CLAUDE_CONTEXT.md` SS4).
- `GET /api/engineering/formula-validation?lang=tr|en` — formül
  kapsam/durum raporu.

Mevcut hiçbir endpoint değiştirilmedi.

## 7. Test ve doğrulama

`tests/test_faz_2_8_8_material_intelligence.py`,
`tests/test_faz_2_8_8_formula_validation.py`,
`tests/test_faz_2_8_8_frontend.py` — domain mantığı, readiness kapısı,
API sözleşmesi, TR/EN parite kontrolü, rapor determinizmi ve frontend
çeviri anahtarı varlığını kapsar. Tam pytest, flake8
(`--max-line-length=100`, değişen dosyalarla sınırlı), `compileall`,
`git diff --check` bu fazın kalite kapısıdır.

**Doğrulanmış sonuçlar (2026-07-29, dağıtım öncesi son çalıştırma):**

- Faz 2.8.8'e özel backend testleri: **81/81 geçti**
  (`test_faz_2_8_8_material_intelligence.py`: 42,
  `test_faz_2_8_8_formula_validation.py`: 16,
  `test_faz_2_8_8_frontend.py`: 23 — bu üçüncüsü, Node/vm tabanlı
  `tests/js/run_material_intelligence_tests.js` harness'ini alt
  süreç olarak da çalıştırır).
- `tests/js/run_material_intelligence_tests.js`: **28/28 assertion
  geçti** (bağımlılıksız Node `vm` harness'i, `frontend/index.html`
  içindeki gerçek kodu çalıştırır).
- Tam pytest paketi (regresyon dahil): **1337/1337 geçti** (1256
  temel + 81 yeni; sıfır regresyon).
- flake8 (`--max-line-length=100`): tamamen yeni dosyalar
  (`material_intelligence.py`, `formula_validation.py`,
  `material_intelligence_report.py`, 3 test dosyası) **tamamen
  temiz**; `backend/app.py`'a eklenen satırlar temiz (dosyanın geri
  kalanındaki uyarılar bu fazdan önce var olan, değiştirilmemiş
  kod satırlarına ait).
- `compileall`, `git diff --check`: temiz.
- JSON geçerliliği: 4 yeni API endpoint'inin + rapor snapshot'ının
  çıktısı ayrıştırılıp yeniden serileştirilerek doğrulandı.
- Determinizm: `list_materials`, `match_materials`,
  `compare_materials`, `recommend_materials` (4 gereksinim
  varyantı × 2 dil), `build_formula_validation_report` (2 dil) ve
  tam rapor snapshot'ı + Markdown render'ı — hepsi tekrarlı
  çağrılarda bayt bazında birebir aynı çıktı üretiyor.
- TR/EN çeviri anahtarı paritesi: `mi.*` önekli **29 EN / 29 TR**
  anahtar birebir eşleşiyor; üç anahtarda (`mi.field.min_rp02_mpa`,
  `mi.field.min_rm_mpa`, `mi.col.id`) başlangıçta İngilizce ile
  birebir aynı olan TR metni gerçek çeviriyle düzeltildi (bkz.
  `frontend/index.html` I18N sözlüğü).
- Geriye dönük uyumluluk: sıfır regresyon; `backend/app.py`'daki tüm
  değişiklikler yeni import + 4 yeni route eklenmesinden ibaret,
  mevcut hiçbir endpoint/davranış değiştirilmedi.
