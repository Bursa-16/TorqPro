# Faz 2.8.21 — Engineering Formula Traceability and Governance Foundation

- **Status:** Delivered (Stage 0-9, tek dallı zincir olarak commit'lendi; henüz main'e merge/push edilmedi)
- **Date:** 2026-08-05
- **Product owner:** İlhan Çekiç
- **Branch:** `feature/faz-2.8.21-engineering-core-traceability`
- **Önceki faz:** Faz 2.8.20 — Washer Resolution Evidence and Controlled Closure, `docs/phases/PHASE_2.8.20_WASHER_RESOLUTION_EVIDENCE_AND_CONTROLLED_CLOSURE.md`

## 0. Numaralandırma notu

Bu iş orijinal talep metninde "Faz 2.8.20" olarak adlandırılmıştı. Baseline doğrulaması (Stage 0) sırasında VERSION dosyasının zaten `2.8.20` olduğu ve bu numaranın Washer Resolution Evidence/Closure fazına ait olarak zaten merge edilip release edildiği tespit edildi. Ürün sahibi onayıyla bu iş **Faz 2.8.21** olarak numaralandırıldı; kapsam ve kurallar değişmedi.

## 1. Kapsam ve kapsam dışı

**Kapsam:** `backend.vdi2230_core.trace`'te zaten kanıtlanmış izlenebilirlik mimarisini (`FormulaTrace` + kapalı `str` Enum + `get_trace()`/`all_traces()`) referans alarak, `backend.engineering_core`'daki (tork, sürtünme, geometri, malzeme, ön yük, joint) canlı formüllere aynı ruhta bir izlenebilirlik/statü katmanı eklemek. Sadece governance ve görünürlük — hiçbir mühendislik formülü yeniden tasarlanmadı.

**Kapsam dışı (bilinçli):** ISO 16224/VDI 2230 kavrama-boyu/FCA C2001/FED-STD hesap motorları; yeni malzeme başarısızlık modelleri; formül-seçim AI'ı; soru bankası otomatik düzeltmesi; geniş frontend modül çıkarımı. Bunlar sadece gelecekteki boşluklar olarak kaydedildi (bkz. §5).

## 2. Formül envanteri — talep edilen ama bulunmayanlar

Stage 2'de istenen envanter listesi şunları da içeriyordu: torsiyonel gerilme, von Mises eşdeğer gerilme, yataklama/temas basıncı, düz çekme gerilmesi (σ=F/A, bağımsız fonksiyon olarak). `backend.engineering_core` içinde bu dört konu için **hiçbir fonksiyon bulunamadı** — bu yüzden bunlara sahte/placeholder trace kaydı açılmadı. `tests/test_faz_2_8_21_engineering_core_traceability.py::TestNoFabricatedEntries` bu boşlukların gelecekte sessizce doldurulmasını (kayıt açılmadan) engelleyen bir yapısal test içeriyor.

## 3. Mimari (final durum)

```
backend/engineering_core/
  trace.py                    (YENİ — 10 canlı formül, vdi2230_core/trace.py mimarisiyle birebir,
                                APPROVED/PROVISIONAL vdi2230_core.trace'ten import edildi)
  __init__.py                 (katkısal — trace modülü __all__'a eklendi)
  torque.py, friction.py,     (DEĞİŞMEDİ — sadece trace.py tarafından tarif ediliyor,
  geometry.py, materials.py,   hiçbiri import/çağrı edilmiyor)
  preload.py, joint.py

backend/calculation_engine/
  formula_validation.py       (katkısal genişletme — _engineering_core_entries() eklendi,
                                FormulaValidationEntry'ye 5 opsiyonel alan eklendi,
                                mevcut vdi2230_core/formula_registry alanları etkilenmedi)

backend/app.py                (katkısal — /api/engineering/check yanıtına formula_governance
                                anahtarı eklendi; preload_n/torque_*/nut_proof_util_pct/
                                internal_thread_sf/external_thread_sf mevcut alanları değişmedi)

frontend/index.html           (küçük, additive — thread-strip-safety result-row'una ve iki
                                eng-card'a "Provisional model" etiketi; yeni i18n key TR+EN)

docs/05_ENGINEERING_FORMULA_SPECIFICATION.md  (Bölüm 22 eklendi)
tests/test_faz_2_8_8_formula_validation.py    (toplam sayılar 7→17'ye güncellendi, kapsam
                                                genişlemesi nedeniyle — formül davranışı değil)
tests/test_faz_2_8_21_engineering_core_traceability.py  (YENİ — 36 governance testi)
```

## 4. Kritik bulgu — `internal_thread_sf`/`external_thread_sf` kullanıcı tarafından hiç görülmüyor (backend yolu üzerinden)

Stage 4 öncesi zorunlu kontrol (İlhan'ın onay mesajındaki 1. madde) sırasında doğrulandı: **`/api/engineering/check` endpoint'i `frontend/index.html` içinde hiçbir yerden çağrılmıyor.** Kullanıcının gördüğü "Hızlı Hesap" ekranındaki `sfInt`/`sfExt` değerleri, `hesapla()` fonksiyonunun tamamen bağımsız, client-side JavaScript yeniden implementasyonundan geliyor — backend'in `evaluate_joint()`'ine hiç dokunmuyor.

Bu bulgu iki karara yol açtı:
- **API tarafı (`formula_governance` anahtarı):** düşük risk (frontend'de sıfır bilinen tüketici), API tüketicileri (curl/Postman/entegrasyonlar/testler) için hâlâ değerli — eklendi.
- **Frontend tarafı (Stage 5 asıl hedefi):** governance bilgisini gerçekten kullanıcıya ulaştırmak için etiket, `hesapla()`'nın render ettiği HTML'e **doğrudan** eklendi (bir API çağrısı üzerinden değil) — bu, "büyük yeniden tasarım yapma" kısıtına en uygun, en küçük müdahale.

## 5. Formula registry sonuçları

- **Registry'ye eklenen canlı formül sayısı: 10** (`ENGCORE_TIGHTENING_TORQUE`, `ENGCORE_THREAD_FRICTION_ANGLE`, `ENGCORE_PITCH_DIAMETER`, `ENGCORE_MINOR_DIAMETER`, `ENGCORE_HELIX_ANGLE`, `ENGCORE_THREAD_SHEAR_AREA`, `ENGCORE_SHEAR_STRENGTH_FROM_RM`, `ENGCORE_PRELOAD_FROM_YIELD`, `ENGCORE_PROOF_LOAD_UTILIZATION`, `ENGCORE_JOINT_CHECK`)
- **Durum dağılımı (engineering_core.trace, 10 kayıt):** APPROVED **0**, PROVISIONAL **9**, EXPERIMENTAL **0**, DEPRECATED **0**, UNVERIFIED **1** (`ENGCORE_SHEAR_STRENGTH_FROM_RM` — 0,58 katsayısının kökeni kodda belgelenmemiş, sadece olası bir eşleşme)
- **Toplam (`/api/engineering/formula-validation` aggregation, vdi2230_core + engineering_core + formula_registry):** total_count **17**, approved_count **2** (değişmedi — hâlâ sadece Φ/F_S), provisional_count **14**, other_status_count **1**
- **Kodda bulunmadığı için kayıt açılmayan formüller:** torsiyonel gerilme, von Mises eşdeğer gerilme, yataklama/temas basıncı, bağımsız σ=F/A fonksiyonu (§2)

## 6. `internal_thread_sf` / `external_thread_sf` governance detayı

`/api/engineering/check` yanıtındaki `formula_governance.internal_thread_sf` / `.external_thread_sf`:

```json
{
  "model_id": "ENGCORE_THREAD_SHEAR_AREA",
  "status": "PROVISIONAL",
  "source_level": "L4_PARTIAL_ALIGNMENT",
  "confidence": "LOW",
  "diameter_basis": "d2 (pitch diameter)",   // external için "d3 (minor diameter)"
  "coefficient": 0.5,
  "limitations": [...],
  "prohibited_claims": ["ISO 16224 compliant", "VDI 2230 compliant", "FCA C2001 compliant", "ASME validated", "production approval without independent engineering validation"]
}
```

Frontend'de aynı iki değerin yanına (`hızlı hesap` ekranı, result-row + iki eng-card) **"Provisional model" / "Geçici model (Provisional)"** etiketi eklendi — mevcut i18n mekanizması (`t('hizli.model_status_provisional')`) kullanılarak.

## 7. API etkisi

Tamamen additive: `/api/engineering/check` yanıtına yeni `formula_governance` anahtarı eklendi, mevcut 7 anahtar (`preload_n`, `torque_min_nm`, `torque_nom_nm`, `torque_max_nm`, `nut_proof_util_pct`, `internal_thread_sf`, `external_thread_sf`) ve opsiyonel `friction_readiness` anahtarı değişmedi. `/api/engineering/formula-validation`'daki mevcut 7 alan (`formula_id`, `symbol`, `unit`, `source`, `classification`, `validation_status`, `catalog`) korunup 5 yeni opsiyonel alan eklendi (vdi2230_core/formula_registry kayıtlarında bu yeni alanlar boş/None).

## 8. Sayısal regresyon kanıtı

Aynı payload, Faz 2.8.21 öncesi (`main`, commit `bc0d73f`) ve sonrası (bu branch) `evaluate_joint()` çıktısı bit-bit aynı:

```
preload_n            = 39150.0
torque_min_nm         = 59.29284065733501
torque_nom_nm         = 69.3125332345851
torque_max_nm         = 79.34244629911926
nut_proof_util_pct   = 81.32530120481928
internal_thread_sf   = 1.050193699745855
external_thread_sf   = 1.8988367774714041
```

`tests/test_faz_2_8_21_engineering_core_traceability.py::TestNumericalRegressionBaseline` bu değerleri LEGACY_REGRESSION_ONLY golden fixture olarak kilitliyor (soru bankasından değil, bu fazdan önceki gerçek koddan alındı).

## 9. Zorunlu ifadeler (Faz 2.8.21 politikası, bkz. docs/05 §22.2)

- Test geçmesi fiziksel doğruluk kanıtı değildir — kodun kendi tutarlılığını kanıtlar.
- Frontend/backend eşleşmesi standart uyumluluğu kanıtlamaz — sadece iki implementasyonun birbirine uyduğunu kanıtlar.
- Soru bankası golden engineering source değildir — hiçbir status/source_level değeri bu fazda soru bankası sonuçlarıyla gerekçelendirilmedi.
- Diş sıyrılma modeli (`ENGCORE_THREAD_SHEAR_AREA`) PROVISIONAL kalmaya devam ediyor, confidence LOW.

## 10. Kalan mühendislik-doğrulama boşlukları (bilinçli, gelecek fazlara bırakıldı)

ISO 16224/VDI 2230/FCA C2001/FED-STD hesap motorları yok; torsiyonel gerilme, von Mises, yataklama basıncı fonksiyonları yok; frontend'in kendi bağımsız JS hesap motoru (thread-shear dahil) ile backend arasında paylaşılan bir parity testi yok (Faz 2.8.20 öncesi rapordan taşınan risk, bu fazda kapatılmadı — sadece PROVISIONAL etiketiyle görünür kılındı).
