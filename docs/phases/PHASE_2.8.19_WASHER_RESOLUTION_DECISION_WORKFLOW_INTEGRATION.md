# Faz 2.8.19 — Washer Resolution Decision Workflow Integration

- **Status:** Delivered (Stage 1-5, tek dallı zincir olarak commit'lendi; henüz main'e merge/push edilmedi)
- **Date:** 2026-08-03
- **Product owner:** İlhan Çekiç
- **Önceki faz:** Faz 2.8.9 — Washer Resolution Decision Workflow (backend), `docs/phases/PHASE_2.8.9_WASHER_RESOLUTION_DECISION_WORKFLOW.md`

## 1. Kapsam ve kapsam dışı

**Kapsam:** Faz 2.8.9'da inşa edilmiş ama hiçbir ekrandan çağrılmayan
washer resolution decision backend'ini (`queue`, `{id}`, `decide`,
`{id}/decisions`) uçtan uca bir frontend workflow'una bağlamak — dört
bağımsız, additive stage:

- **Stage 1** — additive `GET /api/library/washers/resolutions/{resolution_id}` detay endpoint'i.
- **Stage 2** — salt-okunur Resolution Queue + Detail frontend.
- **Stage 3** — kullanıcının kendi girdiği veriyi mevcut `POST /decide`'a gönderen karar giriş formu.
- **Stage 4** — salt-okunur Decision History görünümü.
- **Stage 5** — bu kapanış: VERSION/README/CHANGELOG/backlog hizalaması, bu rapor, tam regresyon + quality gate doğrulaması.

**Kapsam dışı (bilinçli):** 71 `open` veya 5 `blocked_authoritative_source`
kaydın gerçekten çözülmesi (gerçek kanıt gerektirir, bu fazın işi
değil — bkz. §5); joints frontend write UI (backlog'da ayrı, tekrar
tekrar ertelenmiş bir madde); decision history için edit/delete/
rollback/replay; bulk decide; AI destekli öneri; `docs/CHANGELOG.md`
içindeki Faz 2.8.14/2.8.16/2.8.17 boşluklarının doldurulması (bu faz
öncesinde tespit edilmiş, ayrı bir görev olarak bırakıldı).

## 2. Mimari (final durum)

```
backend/library/
  washer_resolution.py                (Faz 2.8.5, değişmedi — kaynak ledger, salt-okunur)
  washer_resolution_decisions.py      (Faz 2.8.9, değişmedi — state machine, validator)
  washer_resolution_decisions_store.py(Faz 2.8.9, değişmedi — append-only I/O)
  washer_resolution_service.py        (Faz 2.8.9 + Stage 1 additive — resolution_detail() eklendi)
backend/app.py                        (Faz 2.8.9 + Stage 1 additive — GET /{resolution_id} eklendi;
                                        queue/decide/decisions endpoint'leri değişmedi)
frontend/index.html                   (Stage 2/3/4 additive — Resolution Queue, Detail,
                                        Decision Entry Form, Decision History bölümleri)
backend/library/data/
  washer_resolution_ledger.json       (Faz 2.8.5 kaynak — bu fazda hiç yazılmadı)
  washer_resolution_decisions.json    (Faz 2.8.9 formatı — bu fazda hiç yazılmadı, hâlâ 0 karar)
```

Backend'de bu fazda **tek bir yeni endpoint** eklendi (Stage 1'in
`GET /{resolution_id}`'si); `queue`, `decide`, `decisions` endpoint'leri
Faz 2.8.9'dan olduğu gibi, sözleşmesi hiç değişmeden yeniden kullanıldı.

## 3. Commit zinciri

| Stage | Branch | Commit | Açıklama |
|---|---|---|---|
| — (2.8.18 hizalaması) | `main` | `3e4b4fdd2ed1aa0247b362cddb523a2acc741875` | Bu fazın baseline'ı |
| 1 | `feature/faz-2.8.19-washer-resolution-decision-entry` | `58ca1d487c0f4bdfd7ac0937ed260d5ed98f6732` | Detail endpoint |
| 2 | `feature/faz-2.8.19-stage2-washer-resolution-queue-ui` | `2481b21d240b51f49cd0f5b08b2e8ffdde48f29e` | Queue/Detail frontend |
| 3 | `feature/faz-2.8.19-stage3-washer-resolution-decision-form` | `bdb5d3d3cd72a56e319fb1566aabbe7da3cae3b2` | Karar giriş formu |
| 4 | `feature/faz-2.8.19-stage4-washer-resolution-decision-history` | `3eecfaf7eb2fb6a345ca9c4524055ee14d626202` | Decision history |
| 5 | `feature/faz-2.8.19-stage5-completion-delivery` | (bu commit) | Kapanış/teslimat |

Her stage, bir öncekinin ucundan dallandırıldı — doğrusal, tek zincir.
`git merge-base --is-ancestor` ile her stage'in bir öncekini içerdiği
doğrulandı.

## 4. Sözleşme sadakati (contract fidelity)

Hiçbir backend endpoint response şeması değişmedi. Frontend'in
kullandığı alan adları, tahmin edilmeden doğrudan koddan doğrulandı:

- **Queue** (`resolution_queue()`): `resolution_id`, `washer_record_id`,
  `issue_type`, `source_status`, `effective_status`, `decision_count`,
  `is_blocked`, `is_terminal`, `requires_authoritative_source`.
- **Detail** (`resolution_detail()`, Stage 1): yukarıdakiler +
  `reason_code`, `resolution_note`, `evidence_reference`,
  `resolved_standard`, `resolved_by`, `resolved_at`, `confidence_level`.
- **Decide request** (`WasherResolutionDecisionRequest`): `new_status`,
  `resolution_note`, `evidence_reference`, `resolved_by`,
  `idempotency_key`, `confidence_level` (opsiyonel). `decided_at`
  bilinçli olarak yok — backend her zaman kendisi üretir.
- **History** (`WasherResolutionDecision`): `decision_id`,
  `resolution_id`, `previous_status`, `new_status`, `resolution_note`,
  `evidence_reference`, `resolved_by`, `decided_at`, `confidence_level`,
  `integrity_checksum`, `idempotency_key`.

## 5. Gerçek veri durumu — otomatik kapanma YOK

`backend/library/data/washer_resolution_decisions.json`:
**0 karar kaydı** (`"decisions": []`, `metadata.record_count: 0`).
Bu faz boyunca hiçbir test bu gerçek dosyaya yazmadı — tüm karar-gönderme
testleri `tmp_path` ile izole edilmiş sahte ledger'lar üzerinde çalıştı.

`backend/library/data/washer_resolution_ledger.json`: **76 kayıt**,
durum dağılımı Stage 1'den bu yana değişmedi:

| Durum | Sayı |
|---|---|
| `open` | 71 |
| `blocked_authoritative_source` | 5 |
| **Toplam** | **76** |

**Bu fazın teslim ettiği şey bir workflow'dur, çözülmüş kayıtlar
değildir.** 76 kaydın hiçbiri bu faz tarafından otomatik kapatılmadı
veya kapatılamaz — her biri, bu yeni arayüzü kullanan bir insanın
kendi kanıtını girmesini gerektiriyor.

## 6. Test sonuçları (stage bazında, kümülatif)

| Stage | Yeni JS harness | Yeni companion pytest | Tam suite (kümülatif) | Quality gate |
|---|---|---|---|---|
| 1 | — | — (backend testi: 13 yeni) | 2226/2226 | — |
| 2 | 76/76 | 25/25 | 2251/2251 | 6/6 (7 JS harness) |
| 3 | 76/76 | 21/21 | 2272/2272 | 6/6 (8 JS harness) |
| 4 | 63/63 | 19/19 | 2291/2291 | 6/6 (9 JS harness) |
| 5 | — | — | (bu raporun altında doğrulanacak) | (bu raporun altında doğrulanacak) |

Baseline (Faz 2.8.18 sonu): 2213/2213. Faz 2.8.19'un dört stage'i
toplam **78 yeni test** ekledi (13+25+21+19), tam suite'i 2291'e
çıkardı.

## 7. Bilinen belge borcu (bu fazda kapatılmadı)

- `docs/CHANGELOG.md`'de Faz 2.8.14/2.8.16/2.8.17 girdileri hâlâ eksik
  (Faz 2.8.18 hizalaması sırasında tespit edildi, kapsam dışı bırakıldı).
- Bu sandbox'ın `origin` remote'u ile gerçek GitHub `main`'i arasındaki
  senkronizasyon farkı — bkz. teslimat raporu §19.

## 8. Sonraki adım

Bu commit zinciri main'e merge/push edilip `v2.8.19` tag'i açıldığında,
sıradaki gerçek ürün ihtiyacı 76 kaydın fiilen çözülmesidir — ama bu,
bir sonraki "faz" değil, bu fazın açtığı workflow'un doğal, süregelen
kullanımıdır.
