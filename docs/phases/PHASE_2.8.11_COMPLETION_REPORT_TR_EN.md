# Phase 2.8.11 — Completion Report / Tamamlanma Raporu
Engineering Governance Architecture and Decision Workflow
Standardization / Mühendislik Yönetişim Mimarisi ve Karar İş Akışı
Standardizasyonu

- Status / Durum: Complete (Stages 1–5) / Tamamlandı (Aşama 1–5)
- Date / Tarih: 2026-07-30
- Branch / Dal: `feature/faz-2.8.11-engineering-governance-architecture`
- ADR: `docs/adr/ADR-0014-engineering-governance-architecture.md`

---

## English

### 1. Summary

Phase 2.8.11 was originally briefed as "Engineering Decision Audit &
Approval Workflow." A read-only repository analysis performed before
any code was written found four independent, already-shipped
governance mechanisms (Production Validation, the legacy
`calculation_revisions` workflow in `backend/app.py`, the joint
revision lifecycle, and the Faz 2.8.9 washer resolution decision
workflow) with overlapping responsibility and inconsistent
vocabulary. The scope was revised to a **standardization phase**:
document a canonical model (Stage 1), then implement it as a
standalone, additive package (Stages 2–4), then add one narrowly
scoped, read-only compatibility adapter (Stage 5) — without ever
modifying any of the four existing mechanisms.

### 2. Stage 1 — Architecture standardization

`docs/adr/ADR-0014-engineering-governance-architecture.md` inventories
the four existing mechanisms, compares their status vocabularies, and
defines the canonical model: **three independent lifecycle groups**
— review (`draft -> under_review -> approved|rejected`),
publication/revision (`draft -> active -> superseded|archived`), and
resolution (`open -> resolved|rejected|waived`) — deliberately never
merged into one overloaded status field. It also defines the
canonical field-name set (`submitted_by/at`, `approved_by/at`,
`rejected_by/at`, `reviewed_by/at`, `review_comment`,
`change_reason`, `revision_no`, `supersedes_id`, `superseded_by_id`,
`decision_id`, `idempotency_key`, `created_at`), transition/audit/
idempotency/revision-lineage principles, a compatibility strategy
(nothing existing changes), and a migration strategy (deferred,
unauthorized by this ADR alone). Documentation-only; no code.

### 3. Stage 2 — Contracts and typed models

`backend/governance/`: `enums.py` (`ReviewStatus`, `PublicationStatus`,
`ResolutionStatus`, `LifecycleGroup`, closed fail-closed transition
tables with an import-time exhaustiveness assertion), `models.py`
(`ReviewDecision` / `PublicationDecision` / `ResolutionDecision`, all
`extra="forbid"`, plus ADR-0014's required-field tables and the
`validate_*_decision()` entry points), `transitions.py` (generic,
table-agnostic transition checking shared by all three groups),
`exceptions.py` (`InvalidTransitionError`,
`MissingRequiredFieldError`). Purely additive; no persistence, no
service, no API; nothing existing imports it or is imported by it.

### 4. Stage 3 — Event store and service layer

`events.py`: `GovernanceEvent` (`extra="forbid"`, `lifecycle_group`-
tagged, UTC-ISO-8601 `occurred_at`, optional
`revision_no`/`supersedes_id`/`superseded_by_id` lineage pointers).
`store.py`: abstract `GovernanceEventStore` contract (append-only, no
update/delete) and `FileGovernanceEventStore` — atomic writes (temp
file + `os.fsync` + `os.replace`), `fcntl.flock` with a
`threading.Lock` fallback on platforms without `fcntl` (Windows-
compatible), UTF-8, deterministic `sort_keys=True`/
`ensure_ascii=False` JSON, corruption detection (malformed/truncated/
wrong-shape/failed-validation all raise `GovernanceCorruptionError`),
no default/shipped data path, valid empty-store behavior, zero
reference to the washer resolution ledgers. `service.py`: nine
command functions (`submit_review`, `approve_review`, `reject_review`,
`activate_publication`, `supersede_publication`,
`archive_publication`, `resolve_resolution`, `reject_resolution`,
`waive_resolution`) plus `event_history`/`effective_status`/
`latest_event` read accessors. **Idempotency is resolved before
transition validation** — a legitimate retry of an already-applied
request returns the original event unchanged even after the
aggregate's effective status has since progressed (verified by a
dedicated regression test). `previous_status` is not a parameter on
any command — effective status is always computed server-side from
event history. No wall-clock call anywhere in the module; `event_id`
is optional and injectable for deterministic tests.

### 5. Stage 4 — API and TR/EN workspace

`backend/governance/api.py`: 11 additive FastAPI routes mounted under
`/api/governance` onto the existing `backend.app.app` (one `include_router`
line, the only Stage 4-approved coupling point), reusing the existing
`backend.api.dependencies.user` authentication dependency (no new
auth mechanism). `actor` is always derived from the authenticated
user, never accepted in a request body (every command model is
`extra="forbid"`, structurally rejecting an `actor`/`previous_status`
override at the request-validation layer). The event store is
resolved lazily per request from `TORQPRO_GOVERNANCE_EVENT_STORE_PATH`;
an unset/blank value returns a safe 503 with a generic message, never
a filesystem path. Endpoints (see Sec. 11 for the full list) map
1:1 onto the Stage 3 service functions with no duplicated business
logic. The frontend adds a generic, domain-agnostic, bilingual
`page-governance` workspace reusing the existing `apiRequest`
utility, `showPage`/`setLanguage` navigation, and `t()`/`data-i18n`
mechanism, with 53/53 exact TR/EN `gov.*` key parity and existing CSS
classes only (`.card`, `.form-group`, `.fc-field-label`, `.table`,
`.ai-form-grid`) — no new stylesheet code was introduced.

### 6. Stage 5 — Compatibility adapter and final validation

**Adapter decision.** Only **washer resolution** received a Stage 5
adapter. `backend/governance/adapters/washer_resolution.py` reads the
existing Faz 2.8.9 workflow's pure, file-backed accessors
(`get_washer_resolution`, `effective_status`,
`decisions_for_resolution` — none of which require a database
connection parameter) and returns a `CompatibilityProjection`
(`source_system`, `source_record_id`, `source_status`,
`lifecycle_group`, `canonical_status`, `mapping_quality`,
`revision_no`, `actor`, `occurred_at`, `reason`, `metadata`) with a
closed `mapping_quality` vocabulary (`exact`/`partial`/
`unsupported`). Validated against **all 76 real ledger records**:
**71 exact** mappings, **5 explicitly unsupported**
(`blocked_authoritative_source`, per ADR-0014's own decision not to
force that washer-specific escape hatch into the canonical
vocabulary) — zero guessed values. A byte-identical-ledger-before/
after test proves the adapter never writes anything. Production
Validation, the legacy calculation-revision workflow, and joints were
**deliberately not adapted**: all three require a live SQLite
connection parameter to read anything, and wiring that into
`backend/governance/` would mean either importing connection-
management helpers from `backend/app.py` (deepening coupling beyond
"read-only, additive") or duplicating that logic — both violate the
"no new dependency cycle" requirement for a first, narrowly-scoped
adapter. This is a deliberate, documented scope boundary, not an
oversight; extending adapter coverage to those three mechanisms is
explicitly left to a future, separately-scoped phase.

**Technical debt resolved.** The pre-existing async defect in
`tests/js/run_material_intelligence_tests.js` (Faz 2.8.8, documented
since ADR-0013) — 19 test scenarios invoked as unawaited top-level
IIFEs, several returning a discarded Promise, so the harness could
report a "clean" result before those scenarios' assertions had
actually run — was confirmed and fixed: converted to the same awaited
`async function main()` pattern already used by the washer-resolution
and governance-workspace harnesses. The fix touches only this one
test file; no production code was changed. A deliberate-failure proof
was performed (inject a false assertion → exit code 1 with a visible
failure → revert → exit code 0, 40/40 passing) both when the fix was
made and is repeatable at any time. A regression-guard test
(`total > 19`) was added to `tests/test_faz_2_8_8_frontend.py`.

### 7. Final architecture

```
backend/governance/
  __init__.py        Package docstring + compatibility contract + exports
  enums.py            ReviewStatus, PublicationStatus, ResolutionStatus,
                       LifecycleGroup, transition tables            (Stage 2)
  exceptions.py        InvalidTransitionError, MissingRequiredFieldError,
                        GovernanceStoreError, GovernanceCorruptionError,
                        GovernanceIdempotencyConflictError,
                        GovernanceDuplicateDecisionError,
                        GovernanceAggregateNotFoundError    (Stage 2 + 3)
  transitions.py        Generic fail-closed transition checking     (Stage 2)
  models.py             ReviewDecision / PublicationDecision /
                         ResolutionDecision + validators             (Stage 2)
  events.py              GovernanceEvent                             (Stage 3)
  store.py                GovernanceEventStore (abstract),
                           FileGovernanceEventStore                  (Stage 3)
  service.py               9 command functions + 3 read accessors    (Stage 3)
  api.py                    11 FastAPI routes under /api/governance  (Stage 4)
  adapters/
    __init__.py
    washer_resolution.py    Read-only CompatibilityProjection        (Stage 5)
```

Plus: one `include_router` line in `backend/app.py` (Stage 4); the
`page-governance` block, `gov.*` i18n keys, and governance JS
functions in `frontend/index.html` (Stage 4).

### 8. Lifecycle separation

Review, publication, and resolution never share a status field, a
transition table, or a required-field table anywhere in this
package — each has its own enum, its own closed transition graph, its
own Stage 2 decision model, and its own Stage 3 command functions.
`GovernanceEvent.lifecycle_group` tags which group an event belongs
to; a reader must always filter by it before interpreting
`previous_status`/`new_status`.

### 9. Event-store guarantees

Append-only (no update/delete method anywhere on the store contract);
atomic writes (temp file + `fsync` + `os.replace`, so a crash mid-
write never leaves a partial file observable); advisory
cross-process locking on POSIX via `fcntl.flock`, with an in-process
`threading.Lock` fallback where `fcntl` is unavailable; UTF-8 and
deterministic (`sort_keys=True`, `ensure_ascii=False`) serialization;
corruption (malformed JSON, wrong shape, a record failing model
validation) is detected and raised as `GovernanceCorruptionError`
rather than silently returning partial/wrong data; no filesystem path
or wrapped-exception text ever appears in a raised error message; no
default/shipped storage path exists anywhere in the package.

### 10. Idempotency behavior

Every command requires an `idempotency_key`. It is checked **before**
effective status is computed or any transition is validated: a
retried request with the same key and an identical normalized
request (same aggregate, lifecycle group, new status, actor, comment/
reason, lineage fields, metadata — excluding `occurred_at`/`event_id`,
which a genuine retry may legitimately resend fresh) returns the
original event unchanged; the same key with a different request
raises `GovernanceIdempotencyConflictError`; a reused `decision_id`
under a different key raises `GovernanceDuplicateDecisionError`.

### 11. API endpoints (11, all implemented and tested)

Read:
- `GET /api/governance/{aggregate_id}/history?aggregate_type=<value>`
- `GET /api/governance/{aggregate_id}/status?aggregate_type=<value>`

Write (each maps 1:1 onto a Stage 3 service function):
- `POST /api/governance/review/{aggregate_id}/submit` → `submit_review`
- `POST /api/governance/review/{aggregate_id}/approve` → `approve_review`
- `POST /api/governance/review/{aggregate_id}/reject` → `reject_review`
- `POST /api/governance/publication/{aggregate_id}/activate` → `activate_publication`
- `POST /api/governance/publication/{aggregate_id}/supersede` → `supersede_publication`
- `POST /api/governance/publication/{aggregate_id}/archive` → `archive_publication`
- `POST /api/governance/resolution/{aggregate_id}/resolve` → `resolve_resolution`
- `POST /api/governance/resolution/{aggregate_id}/reject` → `reject_resolution`
- `POST /api/governance/resolution/{aggregate_id}/waive` → `waive_resolution`

Error mapping: invalid transition / idempotency conflict / duplicate
decision → 409; missing required field / malformed `occurred_at` →
422; unknown aggregate_id+aggregate_type combination → 404;
unconfigured or corrupted store → 503 — every message is generic,
with no filesystem path, traceback, or raw internal exception text.

### 12. Frontend workspace

`page-governance`: aggregate lookup (`aggregate_id`/`aggregate_type`),
a three-card lifecycle status view (review/publication/resolution
shown independently, `null` when untouched, never a guessed value),
an append-only event history table, and a command form covering all
nine actions with `decision_id`/`idempotency_key`/`occurred_at`/
`metadata` inputs and a `superseded_by_id` field shown only for the
supersede action. Renders only backend-supplied values; a malformed
or incomplete API response is treated as an error, never partially
rendered. No lifecycle rule is implemented in JavaScript — the
backend remains authoritative. Explanatory `alert-info` text (all via
`data-i18n`) states plainly that events are append-only, that
effective status is derived from history, that the three lifecycle
groups are independent, and that this Stage 4 workspace is generic
and Stage 5 is what would connect it to a real TorqPro record type.

### 13. Backward-compatibility boundaries

No existing table, JSON ledger, API endpoint, enum, or transition
graph was modified anywhere across Stages 1–5. No data was migrated.
No field was renamed. The Faz 2.8.9 washer resolution workflow is
byte-identical before and after every Stage 5 adapter call (tested
explicitly). No existing mechanism imports `backend.governance`
except the one Stage 4-approved `include_router` line in
`backend/app.py`. No governance module imports an existing mechanism
except the one Stage 5-approved adapter file
(`adapters/washer_resolution.py`), which is read-only and exposes no
mutation, transition, or persistence method — mechanically enforced
by `tests/governance/test_compatibility.py` (11 tests).

### 14. Tests and quality results (final, this stage)

- Governance suite: **155/155 passed**.
- Frontend structural suite (`tests/test_faz_2_8_11_stage4_frontend.py`):
  42/42 passed.
- Full repository suite: **1759/1759 passed**, zero regressions.
- All 6 JavaScript harnesses passed (`run_assembly_intelligence_tests.js`
  44, `run_governance_workspace_tests.js` 58,
  `run_i18n_tests.js` 1097, `run_joint_analysis_tests.js` 45,
  `run_material_intelligence_tests.js` 40 — now genuinely 40 after
  the Stage 5 fix — `run_washer_resolution_report_tests.js` 32).
- `flake8 --max-line-length=100` clean on every Phase 2.8.11-changed
  Python file.
- `python -m compileall` clean.
- `git diff --check` clean.
- No test was deleted, skipped, weakened, or converted to a
  non-asserting test anywhere in this phase.

### 15. Known limitations

- The frontend workspace is generic/administrative — it has no
  awareness of any specific TorqPro record type; connecting it to a
  real washer resolution, calculation revision, or joint revision is
  explicitly Stage-5-and-beyond, follow-up-phase work.
- Only one of four existing mechanisms has a compatibility adapter.
- The event store has no multi-process transactional guarantee beyond
  the advisory lock; a true production deployment would need to
  decide on a shared storage backend (this phase deliberately keeps
  `FileGovernanceEventStore`, per the approved Stage 4 scope, with no
  SQLite/ORM/migration added).

### 16. Deferred migration and integration work

- Production Validation, legacy calculation-revision, and joint
  compatibility adapters (blocked on a settled DB-connection-
  injection pattern for `backend/governance/`).
- Any write-path integration wiring the canonical workflow into a
  real TorqPro record's actual approval/publication process.
- Migration of any existing mechanism's data onto the canonical field
  names (ADR-0014 explicitly does not authorize this; a future,
  dedicated migration ADR would be required).

### 17. Technical debt status

- Resolved this phase: the `run_material_intelligence_tests.js` async
  defect (Sec. 6).
- Outstanding, not part of this phase: none newly introduced. The
  event store's single-file/no-database persistence model is a
  scoping decision (Stage 4 rule: "Do not add SQLite, migrations or
  ORM models"), not a defect.

### 18. Rollback guidance

Every Stage 1–5 commit is additive-only with respect to existing
files, with the sole exceptions of the one `include_router` line and
matching import in `backend/app.py` (Stage 4) and the async-harness
fix in `tests/js/run_material_intelligence_tests.js` (Stage 5, test-
file-only). Rolling back is therefore low-risk:
`git revert <stage-5-commit>` (or reset the branch to a prior stage's
commit) removes only `backend/governance/`,
`tests/governance/`/`tests/test_faz_2_8_11_stage4_frontend.py`/
`tests/js/run_governance_workspace_tests.js`, the `page-governance`
frontend block, and the one router-mount line — no existing ledger,
table, or endpoint requires any corrective action, since none was
ever touched.

### 19. Changed-file summary (cumulative, Stages 1–5)

- `docs/adr/ADR-0014-engineering-governance-architecture.md` (new,
  Stage 1; updated Stage 5)
- `docs/phases/PHASE_2.8.11_ENGINEERING_GOVERNANCE_ARCHITECTURE.md`
  (new, Stage 1; updated Stage 5)
- `docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` (new, Stage 5,
  this document)
- `docs/11_PRODUCT_BACKLOG.md`, `docs/314_Roadmap.md`,
  `docs/CHANGELOG.md` (updated each stage)
- `backend/governance/{__init__,enums,exceptions,transitions,models}.py`
  (Stage 2)
- `backend/governance/{events,store,service}.py` (Stage 3)
- `backend/governance/api.py`, one `include_router` addition in
  `backend/app.py`, `frontend/index.html` (Stage 4)
- `backend/governance/adapters/{__init__,washer_resolution}.py`
  (Stage 5)
- `tests/governance/{test_enums,test_models,test_transitions}.py`
  (Stage 2)
- `tests/governance/{test_events,test_store,test_service}.py`,
  `tests/governance/test_compatibility.py` (created Stage 2, extended
  every later stage) (Stage 3)
- `tests/governance/test_api.py`,
  `tests/test_faz_2_8_11_stage4_frontend.py`,
  `tests/js/run_governance_workspace_tests.js` (Stage 4)
- `tests/governance/adapters/test_washer_resolution_adapter.py`,
  `tests/js/run_material_intelligence_tests.js` (fixed),
  `tests/test_faz_2_8_8_frontend.py` (strengthened) (Stage 5)

### 20. Commit chain (Stages 1–5)

```
c1a2705  Faz 2.8.11 Stage 1: Engineering Governance Architecture ADR (docs only)
17a7624  Faz 2.8.11 Stage 2: Shared governance contracts and typed domain models
1839f48  Faz 2.8.11 Stage 3: Append-only governance event store and service layer
50eac26  feat(governance): add bilingual API and workspace                    (Stage 4)
<stage5> feat(governance): add compatibility projection and complete phase 2.8.11
```

### 21. Git/release boundaries

No push, merge, tag, or GitHub release was performed at any point in
this phase. No production database migration occurred. The branch
`feature/faz-2.8.11-engineering-governance-architecture` was not
deleted.

---

## Türkçe

### 1. Özet

Faz 2.8.11, başlangıçta "Mühendislik Karar Denetimi ve Onay İş Akışı"
olarak tanımlanmıştı. Herhangi bir kod yazılmadan önce yapılan salt
okunur bir depo analizi, örtüşen sorumluluklara ve tutarsız kelime
dağarcığına sahip dört bağımsız, zaten üretimde olan yönetişim
mekanizması buldu (Production Validation, `backend/app.py` içindeki
eski `calculation_revisions` iş akışı, birleşim revizyon yaşam
döngüsü ve Faz 2.8.9 pul çözümleme karar iş akışı). Kapsam,
**standardizasyon aşaması**na revize edildi: önce kanonik bir model
belgelendi (Aşama 1), sonra bu model bağımsız, eklemeli bir paket
olarak uygulandı (Aşama 2–4), ardından dar kapsamlı, salt okunur tek
bir uyumluluk adaptörü eklendi (Aşama 5) — dört mevcut mekanizmadan
hiçbiri hiçbir zaman değiştirilmeden.

### 2. Aşama 1 — Mimari standardizasyon

`docs/adr/ADR-0014-engineering-governance-architecture.md`, dört
mevcut mekanizmayı envanterler, durum kelime dağarcıklarını
karşılaştırır ve kanonik modeli tanımlar: **üç bağımsız yaşam döngüsü
grubu** — inceleme (`draft -> under_review -> approved|rejected`),
yayınlama/revizyon (`draft -> active -> superseded|archived`) ve
çözümleme (`open -> resolved|rejected|waived`) — kasıtlı olarak asla
tek bir aşırı yüklenmiş durum alanında birleştirilmez. Ayrıca kanonik
alan adı kümesini (`submitted_by/at`, `approved_by/at`,
`rejected_by/at`, `reviewed_by/at`, `review_comment`,
`change_reason`, `revision_no`, `supersedes_id`, `superseded_by_id`,
`decision_id`, `idempotency_key`, `created_at`), geçiş/denetim/
tekrarsızlık/revizyon-soyağacı ilkelerini, bir uyumluluk stratejisini
(mevcut hiçbir şey değişmez) ve bir göç stratejisini (ertelenmiş, bu
ADR tek başına yetkilendirmez) tanımlar. Yalnızca belgelendirme;
hiçbir kod yok.

### 3. Aşama 2 — Sözleşmeler ve tipli modeller

`backend/governance/`: `enums.py` (`ReviewStatus`,
`PublicationStatus`, `ResolutionStatus`, `LifecycleGroup`, içe
aktarma zamanında bütünlük doğrulaması içeren kapalı, başarısızlıkta-
kapanan geçiş tabloları), `models.py` (`ReviewDecision` /
`PublicationDecision` / `ResolutionDecision`, tümü `extra="forbid"`,
artı ADR-0014'ün zorunlu alan tabloları ve `validate_*_decision()`
giriş noktaları), `transitions.py` (üç grup tarafından paylaşılan,
tabloya bağımlı olmayan genel geçiş kontrolü), `exceptions.py`
(`InvalidTransitionError`, `MissingRequiredFieldError`). Tamamen
eklemeli; kalıcılık yok, servis yok, API yok; mevcut hiçbir şey onu
içe aktarmaz veya onun tarafından içe aktarılmaz.

### 4. Aşama 3 — Olay deposu ve servis katmanı

`events.py`: `GovernanceEvent` (`extra="forbid"`, `lifecycle_group`
etiketli, UTC-ISO-8601 `occurred_at`, isteğe bağlı
`revision_no`/`supersedes_id`/`superseded_by_id` soyağacı
işaretçileri). `store.py`: soyut `GovernanceEventStore` sözleşmesi
(yalnızca ekleme, güncelleme/silme yok) ve `FileGovernanceEventStore`
— atomik yazmalar (geçici dosya + `os.fsync` + `os.replace`),
POSIX'te `fcntl.flock`, `fcntl` bulunmayan platformlarda (Windows
uyumlu) `threading.Lock` yedeği ile, UTF-8, deterministik
(`sort_keys=True`/`ensure_ascii=False`) JSON, bozulma tespiti
(hatalı biçimli/kesilmiş/yanlış şekilli/doğrulaması başarısız olan
her şey `GovernanceCorruptionError` fırlatır), hiçbir varsayılan/
gönderilen veri yolu yok, geçerli boş depo davranışı, pul çözümleme
defterlerine sıfır referans. `service.py`: dokuz komut fonksiyonu
(`submit_review`, `approve_review`, `reject_review`,
`activate_publication`, `supersede_publication`,
`archive_publication`, `resolve_resolution`, `reject_resolution`,
`waive_resolution`) artı `event_history`/`effective_status`/
`latest_event` okuma erişimcileri. **Tekrarsızlık, geçiş doğrulaması
yapılmadan önce çözülür** — aynı anahtara ve normalleştirilmiş
isteğe sahip tekrar bir istek, varlığın efektif durumu o zamandan
beri ilerlemiş olsa bile orijinal olayı değişmeden döndürür (özel
bir regresyon testiyle doğrulanmıştır). Hiçbir komutta
`previous_status` parametresi yoktur — efektif durum her zaman olay
geçmişinden sunucu tarafında hesaplanır. Modülün hiçbir yerinde
duvar saati çağrısı yoktur; `event_id` isteğe bağlıdır ve
deterministik testler için enjekte edilebilir.

### 5. Aşama 4 — API ve TR/EN çalışma alanı

`backend/governance/api.py`: mevcut `backend.app.app` üzerine
`/api/governance` altında monte edilmiş 11 eklemeli FastAPI rotası
(tek bir `include_router` satırı, tek onaylı Aşama 4 bağlantı
noktası), mevcut `backend.api.dependencies.user` kimlik doğrulama
bağımlılığını yeniden kullanarak (yeni bir kimlik doğrulama
mekanizması yok). `actor` her zaman kimliği doğrulanmış kullanıcıdan
türetilir, asla bir istek gövdesinde kabul edilmez (her komut modeli
`extra="forbid"`dir, istek doğrulama katmanında bir `actor`/
`previous_status` geçersiz kılmasını yapısal olarak reddeder). Olay
deposu, her istek başına `TORQPRO_GOVERNANCE_EVENT_STORE_PATH`'ten
tembelce çözülür; ayarlanmamış/boş bir değer, asla bir dosya sistemi
yolu değil, genel bir mesajla güvenli bir 503 döndürür. Uç noktalar
(tam liste için Bölüm 11'e bakın) hiçbir iş mantığı tekrarı olmadan
Aşama 3 servis fonksiyonlarıyla 1:1 eşleşir. Ön yüz, mevcut
`apiRequest` yardımcı programını, `showPage`/`setLanguage`
navigasyonunu ve `t()`/`data-i18n` mekanizmasını yeniden kullanan,
53/53 tam TR/EN `gov.*` anahtar eşliği ve yalnızca mevcut CSS
sınıflarıyla (`.card`, `.form-group`, `.fc-field-label`, `.table`,
`.ai-form-grid`) genel, alan bağımsız, iki dilli bir
`page-governance` çalışma alanı ekler — yeni bir stil sayfası kodu
tanıtılmadı.

### 6. Aşama 5 — Uyumluluk adaptörü ve nihai doğrulama

**Adaptör kararı.** Yalnızca **pul çözümleme** bir Aşama 5 adaptörü
aldı. `backend/governance/adapters/washer_resolution.py`, mevcut Faz
2.8.9 iş akışının saf, dosya tabanlı erişimcilerini
(`get_washer_resolution`, `effective_status`,
`decisions_for_resolution` — hiçbiri bir veritabanı bağlantı
parametresi gerektirmez) okur ve kapalı bir `mapping_quality`
kelime dağarcığına (`exact`/`partial`/`unsupported`) sahip bir
`CompatibilityProjection` (`source_system`, `source_record_id`,
`source_status`, `lifecycle_group`, `canonical_status`,
`mapping_quality`, `revision_no`, `actor`, `occurred_at`, `reason`,
`metadata`) döndürür. **Tüm 76 gerçek defter kaydına** karşı
doğrulandı: **71 tam eşleşme**, **5 açıkça desteklenmeyen**
(`blocked_authoritative_source`, ADR-0014'ün bu pul-özgü kaçış
yolunu kanonik kelime dağarcığına zorlamama kararına göre) — sıfır
tahmin edilen değer. Öncesi/sonrası bayt-eşleşen defter testi,
adaptörün hiçbir şey yazmadığını kanıtlar. Production Validation,
eski hesap revizyonu iş akışı ve birleşimler **kasıtlı olarak
uyarlanmadı**: üçü de herhangi bir şey okumak için canlı bir SQLite
bağlantı parametresi gerektirir ve bunu `backend/governance/`'a
bağlamak ya `backend/app.py`'den bağlantı yönetimi yardımcılarını
içe aktarmak (bağlantıyı "salt okunur, eklemeli"nin ötesine
derinleştirmek) ya da bu mantığı çoğaltmak anlamına gelir — her ikisi
de ilk, dar kapsamlı bir adaptör için "yeni bağımlılık döngüsü yok"
gereksinimini ihlal eder. Bu, bir gözden kaçırma değil, kasıtlı,
belgelenmiş bir kapsam sınırıdır; adaptör kapsamını bu üç mekanizmaya
genişletmek açıkça gelecekteki, ayrı kapsamlı bir aşamaya
bırakılmıştır.

**Çözülen teknik borç.** `tests/js/run_material_intelligence_tests.js`
(Faz 2.8.8, ADR-0013'ten beri belgelenmiş) içindeki önceden var olan
asenkron kusur — beklenmeyen üst düzey IIFE'ler olarak çağrılan 19
test senaryosu, birkaçı atılan bir Promise döndürüyordu, bu nedenle
test aracı bu senaryoların doğrulamaları gerçekten çalışmadan önce
"temiz" bir sonuç bildirebiliyordu — doğrulandı ve düzeltildi: zaten
pul çözümleme ve yönetişim çalışma alanı test araçları tarafından
kullanılan aynı beklenen `async function main()` düzenine
dönüştürüldü. Düzeltme yalnızca bu bir test dosyasına dokunur; hiçbir
üretim kodu değiştirilmedi. Kasıtlı bir başarısızlık kanıtı yapıldı
(yanlış bir doğrulama enjekte et → görünür bir hatayla çıkış kodu 1 →
geri al → çıkış kodu 0, 40/40 geçti) hem düzeltme yapıldığında hem de
istenildiğinde tekrarlanabilir. `tests/test_faz_2_8_8_frontend.py`'ye
bir regresyon koruma testi (`total > 19`) eklendi.

### 7. Nihai mimari

Bölüm 7 (İngilizce) ile aynı dizin ağacı — bkz. yukarıdaki İngilizce
bölüm; teknik içerik dilden bağımsızdır.

### 8. Yaşam döngüsü ayrımı

İnceleme, yayınlama ve çözümleme bu paketin hiçbir yerinde bir durum
alanını, bir geçiş tablosunu veya bir zorunlu alan tablosunu asla
paylaşmaz — her birinin kendi enum'u, kendi kapalı geçiş grafiği,
kendi Aşama 2 karar modeli ve kendi Aşama 3 komut fonksiyonları
vardır. `GovernanceEvent.lifecycle_group`, bir olayın hangi gruba
ait olduğunu etiketler; bir okuyucu `previous_status`/`new_status`'ı
yorumlamadan önce her zaman buna göre filtrelemelidir.

### 9. Olay deposu garantileri

Yalnızca ekleme (depo sözleşmesinde hiçbir yerde güncelleme/silme
yöntemi yok); atomik yazmalar (geçici dosya + `fsync` + `os.replace`,
böylece yazma sırasında bir çökme asla gözlemlenebilir kısmi bir
dosya bırakmaz); `fcntl` kullanılamadığında işlem içi
`threading.Lock` yedeğiyle POSIX üzerinde `fcntl.flock` aracılığıyla
tavsiye niteliğinde süreçler arası kilitleme; UTF-8 ve deterministik
(`sort_keys=True`, `ensure_ascii=False`) serileştirme; bozulma
(hatalı biçimli JSON, yanlış şekil, model doğrulamasında başarısız
olan bir kayıt) tespit edilir ve kısmi/yanlış veri sessizce
döndürülmek yerine `GovernanceCorruptionError` olarak fırlatılır;
fırlatılan bir hata mesajında asla bir dosya sistemi yolu veya
sarmalanmış istisna metni görünmez; pakette hiçbir yerde varsayılan/
gönderilen bir depolama yolu yoktur.

### 10. Tekrarsızlık davranışı

Her komut bir `idempotency_key` gerektirir. Efektif durum
hesaplanmadan veya herhangi bir geçiş doğrulanmadan **önce**
kontrol edilir: aynı anahtara ve özdeş normalleştirilmiş bir isteğe
sahip (aynı varlık, yaşam döngüsü grubu, yeni durum, aktör, yorum/
neden, soyağacı alanları, meta veri — gerçek bir tekrarın meşru
olarak yeniden gönderebileceği `occurred_at`/`event_id` hariç)
tekrarlanan bir istek orijinal olayı değişmeden döndürür; farklı bir
istekle aynı anahtar `GovernanceIdempotencyConflictError` fırlatır;
farklı bir anahtar altında yeniden kullanılan bir `decision_id`
`GovernanceDuplicateDecisionError` fırlatır.

### 11. API uç noktaları (11, tümü uygulandı ve test edildi)

Okuma:
- `GET /api/governance/{aggregate_id}/history?aggregate_type=<değer>`
- `GET /api/governance/{aggregate_id}/status?aggregate_type=<değer>`

Yazma (her biri bir Aşama 3 servis fonksiyonuyla 1:1 eşleşir):
- `POST /api/governance/review/{aggregate_id}/submit` → `submit_review`
- `POST /api/governance/review/{aggregate_id}/approve` → `approve_review`
- `POST /api/governance/review/{aggregate_id}/reject` → `reject_review`
- `POST /api/governance/publication/{aggregate_id}/activate` → `activate_publication`
- `POST /api/governance/publication/{aggregate_id}/supersede` → `supersede_publication`
- `POST /api/governance/publication/{aggregate_id}/archive` → `archive_publication`
- `POST /api/governance/resolution/{aggregate_id}/resolve` → `resolve_resolution`
- `POST /api/governance/resolution/{aggregate_id}/reject` → `reject_resolution`
- `POST /api/governance/resolution/{aggregate_id}/waive` → `waive_resolution`

Hata eşlemesi: geçersiz geçiş / tekrarsızlık çakışması / yinelenen
karar → 409; eksik zorunlu alan / hatalı biçimli `occurred_at` → 422;
bilinmeyen aggregate_id+aggregate_type kombinasyonu → 404;
yapılandırılmamış veya bozulmuş depo → 503 — her mesaj geneldir,
dosya sistemi yolu, yığın izleme veya ham dahili istisna metni
içermez.

### 12. Ön yüz çalışma alanı

`page-governance`: varlık sorgulama (`aggregate_id`/`aggregate_type`),
üç kartlı bir yaşam döngüsü durumu görünümü (inceleme/yayınlama/
çözümleme bağımsız olarak gösterilir, dokunulmadığında `null`, asla
tahmin edilen bir değer değil), yalnızca ekleme yapılan bir olay
geçmişi tablosu ve `decision_id`/`idempotency_key`/`occurred_at`/
`metadata` girişleri ile dokuz eylemin tümünü kapsayan, yalnızca
yerini alma eylemi için gösterilen bir `superseded_by_id` alanına
sahip bir komut formu. Yalnızca arka uç tarafından sağlanan
değerleri işler; hatalı biçimli veya eksik bir API yanıtı bir hata
olarak ele alınır, asla kısmen işlenmez. JavaScript'te hiçbir yaşam
döngüsü kuralı uygulanmaz — arka uç yetkili kalır. Açıklayıcı
`alert-info` metni (tümü `data-i18n` aracılığıyla), olayların
yalnızca eklendiğini, efektif durumun geçmişten türetildiğini, üç
yaşam döngüsü grubunun bağımsız olduğunu ve bu Aşama 4 çalışma
alanının genel olduğunu ve Aşama 5'in onu gerçek bir TorqPro kayıt
türüne bağlayacak şey olduğunu açıkça belirtir.

### 13. Geriye dönük uyumluluk sınırları

Aşama 1–5 boyunca hiçbir yerde hiçbir mevcut tablo, JSON defteri,
API uç noktası, enum veya geçiş grafiği değiştirilmedi. Hiçbir veri
göç ettirilmedi. Hiçbir alan yeniden adlandırılmadı. Faz 2.8.9 pul
çözümleme iş akışı, her Aşama 5 adaptör çağrısından önce ve sonra
bayt-bayt aynıdır (açıkça test edilmiştir). `backend/app.py`
içindeki tek Aşama 4 onaylı `include_router` satırı dışında hiçbir
mevcut mekanizma `backend.governance`'ı içe aktarmaz. Salt okunur
olan ve hiçbir değiştirme, geçiş veya kalıcılık yöntemi açığa
çıkarmayan tek Aşama 5 onaylı adaptör dosyası
(`adapters/washer_resolution.py`) dışında hiçbir yönetişim modülü
mevcut bir mekanizmayı içe aktarmaz — bu,
`tests/governance/test_compatibility.py` (11 test) tarafından
mekanik olarak zorunlu kılınır.

### 14. Testler ve kalite sonuçları (bu aşama için nihai)

- Yönetişim paketi: **155/155 geçti**.
- Ön yüz yapısal paketi
  (`tests/test_faz_2_8_11_stage4_frontend.py`): 42/42 geçti.
- Tam depo paketi: **1759/1759 geçti**, sıfır gerileme.
- 6 JavaScript test aracının tümü geçti.
- Değiştirilen her Faz 2.8.11 Python dosyasında
  `flake8 --max-line-length=100` temiz.
- `python -m compileall` temiz.
- `git diff --check` temiz.
- Bu aşamada hiçbir yerde hiçbir test silinmedi, atlanmadı,
  zayıflatılmadı veya doğrulama yapmayan bir teste dönüştürülmedi.

### 15. Bilinen sınırlamalar

- Ön yüz çalışma alanı genel/yönetimseldir — herhangi bir belirli
  TorqPro kayıt türü hakkında bilgisi yoktur; onu gerçek bir pul
  çözümlemesine, hesap revizyonuna veya birleşim revizyonuna bağlamak
  açıkça Aşama 5 ve sonrası, takip aşaması işidir.
- Dört mevcut mekanizmadan yalnızca birinin bir uyumluluk adaptörü
  vardır.
- Olay deposunun, tavsiye niteliğindeki kilidin ötesinde çoklu işlem
  işlemsel garantisi yoktur.

### 16. Ertelenen göç ve entegrasyon işi

- Production Validation, eski hesap revizyonu ve birleşim uyumluluk
  adaptörleri (`backend/governance/` için yerleşik bir veritabanı
  bağlantısı enjeksiyon düzenine bağlı).
- Kanonik iş akışını gerçek bir TorqPro kaydının gerçek onay/
  yayınlama sürecine bağlayan herhangi bir yazma yolu entegrasyonu.
- Herhangi bir mevcut mekanizmanın verisinin kanonik alan adlarına
  göç ettirilmesi (ADR-0014 bunu açıkça yetkilendirmez).

### 17. Teknik borç durumu

- Bu aşamada çözüldü: `run_material_intelligence_tests.js` asenkron
  kusuru (Bölüm 6).
- Bekleyen, bu aşamanın parçası değil: yeni tanıtılan hiçbir şey yok.

### 18. Geri alma rehberi

Aşama 1–5'teki her taahhüt, mevcut dosyalara göre yalnızca
eklemelidir; tek istisnalar `backend/app.py`'deki tek
`include_router` satırı ve eşleşen içe aktarma (Aşama 4) ve
`tests/js/run_material_intelligence_tests.js`'deki asenkron test
aracı düzeltmesidir (Aşama 5, yalnızca test dosyası). Bu nedenle geri
alma düşük risklidir: `git revert <aşama-5-taahhüdü>` yalnızca
`backend/governance/`'ı, ilgili testleri, `page-governance` ön yüz
bloğunu ve tek yönlendirici-montaj satırını kaldırır — hiçbir mevcut
defter, tablo veya uç nokta düzeltici bir eylem gerektirmez, çünkü
hiçbiri asla dokunulmadı.

### 19. Değişen dosya özeti ve 20. Taahhüt zinciri

Bölüm 19–20 (İngilizce) ile aynı — bkz. yukarıdaki İngilizce bölüm;
dosya listeleri ve taahhüt hash'leri dilden bağımsızdır.

### 21. Git/yayın sınırları

Bu aşamanın hiçbir noktasında push, merge, tag veya GitHub release
işlemi yapılmadı. Hiçbir üretim veritabanı göçü gerçekleşmedi.
`feature/faz-2.8.11-engineering-governance-architecture` dalı
silinmedi.
