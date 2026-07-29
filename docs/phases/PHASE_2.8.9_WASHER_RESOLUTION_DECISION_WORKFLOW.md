# Faz 2.8.9 — Washer Resolution Decision Workflow (TR/EN)

- **Status:** Delivered
- **Date:** 2026-07-29
- **Product owner:** İlhan Çekiç
- **ADR:** `docs/adr/ADR-0013-washer-resolution-decision-workflow.md`

## 1. Kapsam ve kapsam dışı

**Kapsam:** Faz 2.8.5'in salt-okunur `washer_resolution_ledger.json`
kaydına (76 kayıt: 71 `open`, 5 `blocked_authoritative_source`) hiç
dokunmadan, insan tarafından verilen çözümleme kararlarını
kaydedebilen, denetlenebilir, idempotent bir workflow: append-only
karar ledger'ı, kapalı bir state machine, efektif durum hesaplama
(kaynağı hiç değiştirmeden), additive API, additive rapor genişletmesi
(JSON+Markdown, TR/EN), additive frontend workspace.

**Kapsam dışı:** 71 açık veya 5 bloke kaydın gerçekten çözülmesi
(kanıt gerektirir, bu fazın işi değil); ISO 7093 / ISO 7093-1 standart
kimliği belirsizliğinin çözülmesi (ayrı, yetkilendirilmiş bir ADR
gerektirir); terminal bir kararın yeniden açılması (bu fazda yasak);
`washer_resolution_ledger.json`'ın fiziksel olarak yeniden üretilmesi;
`tests/js/run_material_intelligence_tests.js`'deki önceden var olan
async-harness zayıflığının düzeltilmesi (Faz 2.8.8'e ait, kapsam
dışı — bkz. §7).

## 2. Mimari (final durum)

```
backend/library/
  washer_resolution.py                (Faz 2.8.5, değişmedi — kaynak ledger, salt-okunur)
  washer_resolution_decisions.py      (Stage 1 — domain model, state machine, validator)
  washer_resolution_decisions_store.py(Stage 2/3 — append-only I/O, checksum, idempotency, cross-platform kilit)
  washer_resolution_service.py        (Stage 3 — orkestrasyon: effective_status(), decide_resolution(), resolution_queue())
  washer_report.py                    (Faz 2.8.5 + Stage 4 additive — collect/render, JSON+Markdown TR/EN)
backend/app.py                        (Stage 3/5A — additive endpoint'ler, hiçbir state machine tekrarı yok)
frontend/index.html                   (Stage 5B — page-washerresolution workspace, additive i18n)
backend/library/data/
  washer_resolution_ledger.json       (Faz 2.8.5 kaynak — bu fazda hiç yazılmadı)
  washer_resolution_decisions.json    (Stage 1 — yeni, append-only, üretimde hâlâ 0 karar)
```

## 3. Kaynak ledger'ın değişmezliği (immutable source-ledger principle)

`washer_resolution_ledger.json` bu fazın hiçbir kod yolunda **hiç
yazılmaz**. Testlerde her stage'de bu dosyanın SHA256'ı ve
`wr.count_by_status()` sonucu (71 open / 5 blocked) doğrulanmıştır.
Kararlar tamamen ayrı bir dosyada (`washer_resolution_decisions.json`)
tutulur.

## 4. Append-only karar geçmişi

`washer_resolution_decisions_store.py`:
- `append_decision()` / `record_decision()`: var olan `decision_id`
  asla overwrite edilmez (`DuplicateDecisionIdError`); atomik yazma
  (tempfile + `fsync` + `os.replace`).
- Eşzamanlılık: `fcntl.flock` mevcutsa (POSIX) dosya kilidi, değilse
  (ör. Windows) in-process `threading.Lock` — modül import'u hiçbir
  platformda çökmez.
- Checksum: proje kanonik algoritması (`sha256`,
  `sort_keys=True`, `ensure_ascii=False`) — Türkçe karakter regresyon
  testiyle korunuyor.

## 5. Efektif durum hesaplama

`washer_resolution_service.effective_status(resolution_id)`: bir
`resolution_id` için en son kaydedilen kararın `new_status`'u varsa
onu, yoksa kaynak ledger'ın orijinal `resolution_status`'unu döndürür.
Bu hesaplama tek bir yerde yaşar; rapor (`washer_report.py`) ve API
(`resolution_queue()` üzerinden) bunu tekrar üretmez, sadece çağırır.

## 6. State-transition kuralları

`ALLOWED_TRANSITIONS` (kapalı tablo):
- `open -> {under_review, resolved, accepted_as_is, rejected}`
- `under_review -> {open, resolved, accepted_as_is, rejected}`
- Terminal statüler (`resolved`/`accepted_as_is`/`rejected`): çıkış
  yok (bu fazda reopen yasak).
- `blocked_authoritative_source`: çıkış yok; `BlockedRecordDecisionError`
  (409) — 5 bloke kayıt bu workflow ile asla karara bağlanamaz.

Tablo dışı her geçiş `InvalidTransitionError` (fail-closed). Import
zamanında bir assertion, her `WasherResolutionStatus` üyesinin
tabloda/terminal kümesinde/bloke özel durumunda karşılandığını
doğrular.

## 7. Idempotency davranışı

`decide_resolution()`: `idempotency_key` her zaman zorunlu. Aynı key
ile gelen istek, önce state machine kontrolünden **önce** kontrol
edilir:
- Aynı key + aynı içerik (status/not/kanıt/karari-veren/confidence) →
  orijinal karar aynen döner, yeni kayıt oluşmaz (`created=False`).
- Aynı key + farklı içerik (farklı `resolution_id` dahil) →
  `IdempotencyConflictError` (409).

Bu sıralama bilinçli: meşru bir network retry, ilk deneme efektif
durumu zaten ilerletmiş olsa bile state-machine doğrulamasında
sahte bir hatayla karşılaşmamalı.

## 8. Salt-okunur rapor mimarisi

`GET /api/library/washers/resolutions/queue`,
`GET /api/library/washers/resolutions/{id}/decisions`,
`GET /api/library/washers/resolutions/report` — üçü de GET, hiçbiri
karar oluşturamaz/değiştiremez. Rapor endpoint'i Stage 4'ün
`collect_washer_resolution_report()`'unu tek doğruluk kaynağı olarak
kullanır; `app.py` içinde efektif durum hesaplaması **tekrar
üretilmez**.

## 9. JSON ve Markdown rapor formatları

Varsayılan `format=json` — dil bağımsız (durum kodları, serbest metin
değil). `format=markdown` — mevcut Stage 4 TR (`render_washer_resolution_report_markdown`)
ve yeni EN (`render_washer_resolution_report_markdown_en`)
renderer'larını kullanır; `app.py` içinde markdown yeniden üretilmez.

## 10. TR/EN davranışı

Bu fazın eklediği her yeni kullanıcıya-dönük metin (`wrr.*` frontend
anahtarları, rapor bölümleri) baştan itibaren TR/EN çifti olarak
tanımlanır (Faz 2.8.8'de kurulan kural, ADR-0012). 38/38 `wrr.*`
anahtar tam parite doğrulandı. Önceki fazların (2.8.5 öncesi)
serbest-metin İngilizce uyarıları bu fazda geriye dönük çevrilmedi
(additive-only kural, değişmedi).

## 11. Bütünlük/checksum garantileri

Her `WasherResolutionDecision.integrity_checksum` ve raporun
`report_checksum`'ı, proje kanonik algoritmasıyla (checksum alanı
hariç tüm alanlar üzerinden) hesaplanır ve deterministiktir: aynı
girdi kümesi her çalıştırmada byte-seviyesinde aynı JSON/checksum
üretir (testlerle doğrulandı, dahil karar sırası bağımsızlığı).

## 12. Frontend davranışı

`page-washerresolution` workspace: özet kartlar, kaynak/efektif durum
karşılaştırması (kaynağın değişmezliği ve efektif durumun karar
geçmişinden türetildiği açıkça belirtilir), issue-type dağılımı, son
karar özeti (boş durum dahil), bütünlük/checksum paneli.
`wrrIsWellFormed()` guard'ı: rapor yanıtı eksikse hiçbir alan tahmin
edilmez, açık bir hata durumu gösterilir. Dil değişiminde zaten
çekilmiş veri yeniden render edilir (JSON içerik dilden bağımsız
olduğu için yeniden fetch gerekmez).

## 13. Test ve doğrulama özeti (final)

- Faz 2.8.9 testleri: **188/188** (Stage 1: 47, Stage 2: 20, Stage 3:
  32, Stage 4: 26, Stage 5A: 27, Stage 5B: 36)
- Tam pytest suite: **1525/1525** (0 regresyon)
- Node washer-resolution harness: **32/32** (async/await ile
  yeniden yapılandırıldı — bkz. ADR-0013 "Consequences")
- Mevcut i18n harness: **1097/1097**
- Kaynak ledger SHA256: her stage'de değişmeden doğrulandı
  (`1d1776473bf5b843103beb858171f97ee3c4761593fc5e5c5ed9a4e8a0e3c23d`)
- Üretim `washer_resolution_decisions.json`: her stage sonunda 0 karar

## 14. Geriye dönük uyumluluk

Bu faz tamamen additive'dir: hiçbir mevcut endpoint, veri şeması veya
domain kuralı değiştirilmedi. `washer_resolution.py` (Faz 2.8.5) ve
`washer_report.py`'nin mevcut alanları aynen korunmuştur.
