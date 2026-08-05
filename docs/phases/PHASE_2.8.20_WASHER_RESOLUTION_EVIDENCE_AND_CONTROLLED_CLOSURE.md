# Faz 2.8.20 — Washer Resolution Evidence & Controlled Closure

- **Status:** Delivered (Stage 1-5, PR #33 ile main'e merge edildi ve `v2.8.20` tag'i oluşturuldu; PR #34 ile dört ek test-bakım commit'i tag sonrasında main'e eklendi)
- **Date:** 2026-08-05
- **Product owner:** İlhan Çekiç
- **Önceki faz:** Faz 2.8.9 — Washer Resolution Decision Workflow (backend), Faz 2.8.19 — Washer Resolution Decision Workflow Integration (frontend), `docs/phases/PHASE_2.8.19_WASHER_RESOLUTION_DECISION_WORKFLOW_INTEGRATION.md`

## 1. Amaç ve Kapsam

**Amaç:** Faz 2.8.9/2.8.19'da inşa edilmiş washer resolution decision workflow'unun üzerine, yapılandırılmış bir kanıt (evidence) izi ve kontrollü, kanıt-tabanlı bir kapanış (closure) mekanizması eklemek — bir resolution kaydının yalnızca yeterli, doğrulanmış kanıtla ve terminal bir kararla kapatılabildiği bir sistem.

**Kapsam — beş bağımsız, additive stage:**

- **Stage 1** — evidence domain modeli (`WasherResolutionEvidence`), immutable, checksummed, persistence/API'siz.
- **Stage 2** — append-only evidence persistence katmanı.
- **Stage 3** — controlled closure service (readiness kuralları, closure domain modeli, closure ledger).
- **Stage 4** — 5 yeni REST endpoint.
- **Stage 5** — additive frontend workflow + JS test harness + kalite kapısı entegrasyonu.

**Kapsam dışı (bilinçli):** Reopen mekanizması (ADR-0013 ile tutarlı — hiçbir katmanda yok); governance sync (ADR-0015 deseni bu faza henüz uygulanmadı); reporting/export; evidence verification transition UI (yalnızca gösterim, değiştirme yok); mevcut 76 washer resolution kaydının gerçekten kanıtlanması/kapatılması (bu fazın işi değil, ayrı bir insan görevi).

## 2. Stage 1-5 Özeti

| Stage | Ana teslim | Anahtar dosyalar |
|---|---|---|
| 1 | `WasherResolutionEvidence` domain modeli — `EvidenceType` (7 değer), `EvidenceVerificationStatus` (unverified/verified/rejected), checksum/normalizasyon, factory | `backend/library/washer_resolution_evidence.py` |
| 2 | Append-only, kilitli, atomik-yazmalı evidence ledger — Faz 2.8.9 decision ledger deseninin birebir kopyası | `backend/library/washer_resolution_evidence_store.py`, `data/washer_resolution_evidence.json` |
| 3 | `WasherResolutionClosure` domain modeli + kendi ledger'ı + `record_resolution_evidence()`/`evaluate_closure_readiness()`/`close_resolution()`/`get_resolution_closure()` orkestrasyonu | `backend/library/washer_resolution_closure.py`, `washer_resolution_closure_store.py`, `washer_resolution_service.py` (additive) |
| 4 | 5 yeni REST endpoint, mevcut modüler router konvansiyonu (Faz 2.8.17) | `backend/api/routes/washer_resolution_closure.py`, `backend/app.py` (additive) |
| 5 | 5 yeni UI kartı (Evidence List/Form, Closure Readiness, Close Form/Result), 62 yeni TR/EN anahtarı, yeni JS harness (128 assertion) | `frontend/index.html`, `tests/js/run_washer_resolution_evidence_closure_tests.js` |

## 3. API Endpoint'leri

| Method | Route | Servis fonksiyonu | Başarı kodu |
|---|---|---|---|
| POST | `/api/library/washers/resolutions/{resolution_id}/evidence` | `record_resolution_evidence(...)` | 200 |
| GET | `/api/library/washers/resolutions/{resolution_id}/evidence` | `resolution_evidence_for(...)` | 200 |
| GET | `/api/library/washers/resolutions/{resolution_id}/closure-readiness` | `evaluate_closure_readiness(...)` | 200 |
| POST | `/api/library/washers/resolutions/{resolution_id}/close` | `close_resolution(...)` | 200 |
| GET | `/api/library/washers/resolutions/{resolution_id}/closure` | `get_resolution_closure(...)` | 200 (kayıt yoksa `{"closure": null}`, 404 değil) |

**Exception mapping:** `ResolutionNotFoundError`→404, `EvidenceIntegrityError`/`ClosureIntegrityError`→422, `ClosureNotReadyError`/`DuplicateClosureError`/`BlockedRecordDecisionError`→409, beklenmeyen hata→500 (loglanır, iç detay sızmaz).

## 4. Closure Readiness Kuralları

`evaluate_closure_readiness(resolution_id)`, `is_ready=True` döndürmesi için **tüm** aşağıdakileri gerektirir:

- Kaynak ledger statüsü `blocked_authoritative_source` **olmamalı**.
- `effective_status`, terminal decision statülerinden (`resolved`/`accepted_as_is`/`rejected`) biri olmalı ve o terminal kararın `decision_id`'si bulunmalı.
- En az **1 adet `verified`** durumdaki evidence kaydı olmalı (`unverified`/`rejected` sayılmaz, ama görünürlük için ayrı listelenir).
- Hiçbir evidence kaydı **bozuk (checksum uyumsuz)** olmamalı — tek bir bozuk kayıt bile, başka yeterli kanıt olsa dahi, `is_ready=False` yapar (sessizce atlanmaz, `corrupted_evidence_ids`'te görünür).
- Bu resolution için **daha önce bir closure kaydı bulunmamalı** (duplicate guard, `resolution_id` bazlı).

`close_resolution()`, yalnızca `verified` evidence'ları closure'a `evidence_ids` olarak yazar; `unverified`/`rejected`/bozuk kayıtlar asla closure kaydına dahil edilmez.

## 5. Frontend Akışı

Mevcut washer resolution detay ekranına additive: Queue → Detail → Decision Form → Decision History kartlarının **ardına**, Evidence List → Evidence Add Form → Closure Readiness → Close Form → Closure Result kartları eklendi. `wrrLoadResolutionDetail()`'ın başarı yoluna üç yeni çağrı (`wrrLoadEvidence`, `wrrLoadClosureReadiness`, `wrrLoadClosure`) eklendi, mevcut çağrılar (detail/decision-form/history) değişmedi. Evidence/close submit'lerinde çift-tıklama koruması (`WRR_EVIDENCE_IN_FLIGHT`/`WRR_CLOSE_IN_FLIGHT`), mevcut `apiRequest()` helper'ı yeniden kullanıldı (yeni fetch wrapper yok). Verification status yalnızca **gösterilir**, bu ekrandan değiştirilemez. Reopen butonu/UI'si hiçbir yerde yok.

## 6. Gerçek Veri Durumu — Otomatik Kapanma YOK

Bu faz, **workflow'u** teslim ediyor, kapanmış kayıtları değil. Release anında:
- `backend/library/data/washer_resolution_evidence.json` — **boş** (`"evidence": []`).
- `backend/library/data/washer_resolution_closure.json` — **boş** (`"closures": []`).
- 76 washer resolution kaydından **hiçbiri** bu faz tarafından otomatik olarak kanıtlanmadı veya kapatılmadı — bu, ayrı, süregelen bir insan görevi.

## 7. Test Sonuçları

| Katman | Sonuç |
|---|---|
| Backend (Stage 1-4, pytest) | Tüm stage testleri geçti (Stage 1: 47, Stage 2: 25, Stage 3: 45+1 güvenlik düzeltmesi, Stage 4: 51) |
| Frontend wrapper (Stage 5, pytest) | 22 passed |
| Evidence & Closure JS harness | 128/128 passed |
| Joint Revision List UX JS harness (Faz 2.8.16, bu fazda dayanıklılık düzeltmesi aldı) | 152/152 passed |
| TR/EN i18n key parity | 6 passed (tüm `wrr.evidence.*`/`wrr.closure.*` anahtarları dahil) |
| Canonical quality gate (`tools/run_quality_gate.py`) | 5/6 kapı PASSED (JavaScript harness'ler dahil, "All 10 JavaScript harnesses passed"); 6. kapı (full pytest) yalnızca aşağıdaki 3 bilinen historical test nedeniyle FAILED |

## 8. Bilinen 3 Historical Test

Aşağıdaki 3 test, Faz 2.8.19'a ait, `HEAD` yerine sabit bir tarihsel commit'e karşı `git diff` alan stage-sınırı testleridir. `backend/` altına eklenen **her** yeni dosya (bu fazın da dahil olduğu) bu testleri tetikler — kök nedeni Faz 2.8.20 Stage 2 kod incelemesinde tespit edilip belgelendi, bu fazda **düzeltilmedi** (kapsam dışı):

- `tests/test_faz_2_8_19_stage2_washer_resolution_queue_frontend.py::test_stage2_touches_no_backend_files`
- `tests/test_faz_2_8_19_stage3_washer_resolution_decision_form.py::test_stage3_touches_no_backend_or_version_files`
- `tests/test_faz_2_8_19_stage4_washer_resolution_decision_history.py::test_stage4_touches_no_backend_or_version_files`

Önerilen kalıcı çözüm (ayrı bir bakım görevi olarak): bu testlerin `HEAD` yerine kendi stage'lerinin bitiş commit'ine sabitlenmesi.

## 9. Release / Tag Durumu

- **`v2.8.20` tag'i mevcut** ve **PR #33'ün merge commit'ini** (`e30e5e1`) gösteriyor.
- PR #33, Faz 2.8.20'nin 5 ana stage'ini (`feature/faz-2.8.20-stage5-closure-frontend` branch'i, Stage 1-5) main'e taşıdı.
- **PR #34**, tag'den **sonra** main'e merge edildi ve dört ek test-bakım commit'i getirdi (`309097c`, `81fd04d`, `a39210e`, `1b87954`) — taşınabilir Stage 5 wrapper çalıştırması, güncellenmiş Stage 5 kapsam beklentileri, dayanıklı Joint Revision i18n extraction, ve son kapsam hizalaması.
- **Bu doküman turu `v2.8.20` tag'ine dokunmuyor** — tag hâlâ `e30e5e1`'i gösteriyor, güncel main HEAD'ini (`5f233dc`) göstermiyor. Tag'in PR #34'ün commit'lerini de kapsayacak şekilde ileri alınıp alınmayacağı (yeni bir `v2.8.20.1`/`v2.8.21` gibi) ayrı, açık bir karar gerektiriyor.

## 10. Sonraki Faz Önerileri

- Bölüm 8'deki 3 historical testin kalıcı düzeltmesi (ayrı, küçük bir bakım fazı).
- Governance sync'in closure'a genişletilmesi (ADR-0015 deseninin evidence/closure'a uygulanması) — bilinçli olarak bu fazın dışında bırakıldı.
- Evidence verification transition UI (verify/reject butonları) — bu fazda yalnızca gösterim vardı, durum değiştirme yoktu.
- Reporting/export entegrasyonu (mevcut washer resolution report modülüne evidence/closure verisinin eklenmesi).
- `v2.8.20` tag'inin PR #34'ün commit'lerini kapsayıp kapsamayacağına dair karar.
