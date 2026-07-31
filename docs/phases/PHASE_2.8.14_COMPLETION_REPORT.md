# Phase 2.8.14 Completion Report — Joint Revision Governance Bulk Visibility

## 1. Phase title and status

**EN.** Faz 2.8.14 — Joint Revision Governance Bulk Visibility.
**Status: Complete (Stages 1–5), delivered 2026-07-31.**
Branch: `feature/faz-2.8.14-joint-revision-bulk-visibility`. Final
Stage 5 HEAD: `efc2c9e84cd343628831748362a7ce5e42f01b8f`.

**TR.** Faz 2.8.14 — Joint Revision Governance Toplu Görünürlük.
**Durum: Tamamlandı (Stage 1–5), teslim tarihi 2026-07-31.**
Branch: `feature/faz-2.8.14-joint-revision-bulk-visibility`. Nihai
Stage 5 HEAD: `efc2c9e84cd343628831748362a7ce5e42f01b8f`.

## 2. Executive summary

**EN.** Phase 2.8.13 made the single-record `joint_revision`
governance projection reachable through one read-only lookup, but a
caller had to already know a `revision_id` — there was no way to
discover or browse joint revisions from the governance workspace.
Faz 2.8.14 closed that specific, evidence-based gap (identified as a
conditional next-phase recommendation in
`PHASE_2.8.13_COMPLETION_REPORT.md` §16): one new, additive, read-only
source accessor; one new, additive bulk governance adapter function
that reuses 100% of the existing canonical single-record mapping
logic; one new, additive, GET-only API route; and one new, additive
frontend list card with full TR/EN i18n. No existing capability,
schema, endpoint, or engineering data was modified anywhere in this
phase.

**TR.** Faz 2.8.13, tekil `joint_revision` governance projeksiyonunu
tek bir salt-okunur sorguyla erişilebilir hale getirdi, ancak
çağıranın önceden bir `revision_id` bilmesi gerekiyordu — governance
workspace üzerinden joint revision'ları keşfetmenin/taramanın hiçbir
yolu yoktu. Faz 2.8.14 tam olarak bu kanıta dayalı boşluğu kapattı
(`PHASE_2.8.13_COMPLETION_REPORT.md` §16'da koşullu bir sonraki-faz
önerisi olarak belirlenmişti): bir yeni, katmalı, salt-okunur kaynak
erişimcisi; mevcut canonical tekil-kayıt mapping mantığının
%100'ünü yeniden kullanan bir yeni, katmalı toplu governance adaptör
fonksiyonu; bir yeni, katmalı, yalnızca-GET API route'u; ve tam TR/EN
i18n'e sahip bir yeni, katmalı frontend liste kartı. Bu fazda hiçbir
yerde mevcut bir yetenek, şema, endpoint veya mühendislik verisi
değiştirilmedi.

## 3. Repository baseline

**EN.** Pre-phase baseline: branch `main`, commit
`79cd36b0fcf97dac9280874abdd7c25130ecd59e` (merge of Faz 2.8.13),
working tree clean, tag `2.8.13`, full suite 1871/1871, governance
suite 253/253, quality gate 6/6 PASSED. No branch or commit anywhere
in the repository referenced "2.8.14" prior to this phase's own Stage
1.

**TR.** Faz-öncesi taban: branch `main`, commit
`79cd36b0fcf97dac9280874abdd7c25130ecd59e` (Faz 2.8.13'ün merge'i),
working tree temiz, tag `2.8.13`, tam suite 1871/1871, governance
suite 253/253, quality gate 6/6 PASSED. Bu fazın kendi Stage 1'inden
önce depodaki hiçbir branch veya commit "2.8.14"ye referans vermiyordu.

## 4. Original problem

**EN.** A governance workspace user who wanted to see the review
state of joint revisions had to already know each `revision_id` — no
discovery path existed. The existing single-record lookup was useful
only when the ID was already known from elsewhere (a support ticket,
a log line), not for general oversight of joint review activity.

**TR.** Joint revision'ların inceleme durumunu görmek isteyen bir
governance workspace kullanıcısının önceden her `revision_id`'yi
bilmesi gerekiyordu — keşif yolu yoktu. Mevcut tekil-kayıt sorgusu
yalnızca ID başka bir yerden zaten biliniyorsa (bir destek kaydı, bir
log satırı) kullanışlıydı, joint inceleme aktivitesinin genel
gözetimi için değil.

## 5. Approved scope

**EN.** Locked in Stage 1
(`docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`):
one additive, read-only `list_joint_revisions()` source accessor; one
additive `project_joint_revisions_bulk()` governance adapter function;
one additive `GET /api/governance/joint-revisions` API route; one
additive frontend list card with TR/EN i18n. No pagination, no
sorting/search, no write path, no new enum/status, no washer
resolution data changes, no governance registry/validator, no
README/VERSION changes (deferred separately).

**TR.** Stage 1'de kilitlendi
(`docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`):
bir katmalı, salt-okunur `list_joint_revisions()` kaynak erişimcisi;
bir katmalı `project_joint_revisions_bulk()` governance adaptör
fonksiyonu; bir katmalı `GET /api/governance/joint-revisions` API
route'u; TR/EN i18n'e sahip bir katmalı frontend liste kartı.
Pagination yok, sorting/search yok, yazma yolu yok, yeni enum/status
yok, washer resolution veri değişikliği yok, governance registry/
validator yok, README/VERSION değişikliği yok (ayrıca ertelendi).

## 6. Architecture decision

**EN.** The mandated priority order (reuse existing accessor →
compose via adapter → access persistence directly → import private
function → add additive accessor) was evaluated in Stage 1 and
concluded that **Option B was required**: no existing accessor could
list revisions, composition had no source of revision IDs, and direct
persistence access from governance would have discarded exactly the
service-module-boundary property that made the original joint-revision
adapter approvable (per `ADR-0014`'s documented NO-GO precedent for
mechanisms without a service-module boundary). One new, additive,
read-only accessor in `backend/joints/service.py` was therefore added
— the smallest change that preserves the established architecture.

**TR.** Zorunlu öncelik sırası (mevcut erişimciyi yeniden kullan →
adaptör üzerinden composition yap → persistence'a doğrudan eriş →
private fonksiyon import et → katmalı erişimci ekle) Stage 1'de
değerlendirildi ve **Seçenek B'nin gerekli olduğu** sonucuna varıldı:
hiçbir mevcut erişimci revision'ları listeleyemiyordu, composition'ın
bir revision ID kaynağı yoktu, ve governance'tan persistence'a
doğrudan erişim, orijinal joint-revision adaptörünü onaylanabilir
kılan tam olarak aynı servis-modülü-sınırı özelliğini ortadan
kaldırırdı (`ADR-0014`'ün servis-modülü sınırı olmayan mekanizmalar
için dokümante edilmiş NO-GO emsaline göre). Bu nedenle
`backend/joints/service.py`'ye bir yeni, katmalı, salt-okunur
erişimci eklendi — kurulu mimariyi koruyan en küçük değişiklik.

## 7. Stage-by-stage implementation summary

**EN.**

- **Stage 1** (`df6e8058497c29f5a6d95fdfbf13dfd44f80d76e`, docs only):
  scope-lock and integration contract, bilingual EN/TR — architecture
  decision, backend/adapter/API/frontend/i18n contracts, allowed/
  protected files, non-goals, seven-stage plan.
- **Stage 2** (`9640eba0b21b62c194f0e235dd4d607ec1876799`):
  `list_joint_revisions(joint_id=None)` in `backend/joints/service.py`
  and `project_joint_revisions_bulk(joint_id=None)` in
  `backend/governance/adapters/joint_revision.py`, additively exported
  from `backend/governance/adapters/__init__.py`. 22 new backend
  tests.
- **Stage 3** (`076321cf39938617b3575c7d0a020b462b6621aa`):
  `GET /api/governance/joint-revisions` in `backend/governance/api.py`,
  calling `project_joint_revisions_bulk()` exactly once, always `200`
  for a well-formed request, bare JSON array response. 26 new backend
  tests.
- **Stage 4** (`7e2f6b7ff6184501f48f99cbd46acd8dbc73d805`): additive
  "Joint Revision List (read-only)" card inside the existing
  governance workspace, reusing only pre-existing CSS classes and
  helper functions; 11 new `gov.jrlist.*` i18n keys, full TR/EN
  parity; safe `URLSearchParams`-based query construction; 18 new JS
  harness scenarios. One test-harness-only bug (missing
  `URLSearchParams` global in the Node `vm` sandbox) and one brittle
  row-counting assertion were found and fixed during this stage —
  both in the test harness, not in production code.
- **Stage 5** (`efc2c9e84cd343628831748362a7ce5e42f01b8f`): full
  coverage-matrix review against the Stage 1 contract (no gap found,
  no new test added), and one mechanical fix to a pre-existing,
  now-stale hardcoded i18n key-count constant in
  `tests/test_faz_2_8_11_stage4_frontend.py` (69 → 80 — the exact,
  unavoidable, mechanical consequence of the 11 new `gov.jrlist.*`
  keys added in Stage 4, independently re-derived from the file
  itself via the test's own extraction logic, not copied from any
  prior estimate).

**TR.** Yukarıdaki İngilizce bölümün karşılığı, aynı commit
hash'leri ve aynı test sayılarıyla: Stage 1 (kontrat), Stage 2
(erişimci + adaptör, 22 yeni test), Stage 3 (API, 26 yeni test),
Stage 4 (frontend + i18n, 18 yeni JS senaryosu, harness'te bulunan
iki hata düzeltildi), Stage 5 (coverage incelemesi — eksik
bulunmadı, i18n sabit düzeltmesi 69→80).

## 8. Changed files

**EN.** `git diff --name-status 79cd36b0..HEAD` — 12 files, 2106
insertions, 11 deletions:

| Category | Files |
|---|---|
| Documentation (new) | `docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md` |
| Source accessor | `backend/joints/service.py` (+34) |
| Governance adapter | `backend/governance/adapters/joint_revision.py` (+49), `backend/governance/adapters/__init__.py` (+2) |
| API | `backend/governance/api.py` (+54/-7 net, one route renamed test aside) |
| Frontend/i18n | `frontend/index.html` (+148) |
| Backend tests | `tests/test_joints_foundation.py` (+111, new), `tests/governance/adapters/test_joint_revision.py` (+83), `tests/governance/test_compatibility.py` (+253 net), `tests/governance/test_joint_revision_bulk_api.py` (new, +331) |
| Frontend/JS tests | `tests/js/run_governance_workspace_tests.js` (+259 net) |
| Regression maintenance | `tests/test_faz_2_8_11_stage4_frontend.py` (2 lines: stale key-count constant 69→80) |

No file outside this table changed anywhere in the phase.

**TR.** Yukarıdaki tablo, `git diff --name-status 79cd36b0..HEAD`
komutunun gerçek çıktısından doğrudan türetilmiştir — 12 dosya, 2106
ekleme, 11 silme. Bu tablo dışında hiçbir dosya fazın hiçbir yerinde
değişmedi.

## 9. Source accessor behaviour

**EN.** `list_joint_revisions(joint_id: int | None = None) -> list`
in `backend/joints/service.py`: read-only (never inserts/updates/
deletes, never commits); optional `joint_id` filter (`None` returns
all revisions across all joints); deterministic ascending `id` order,
mirroring `list_joints()`'s existing convention exactly; parameterized
SQL only (`?` placeholders, no string interpolation); unknown/empty
`joint_id` returns `[]`, never raises; every existing function in the
file is byte-identical.

**TR.** Yukarıdaki İngilizce bölümün karşılığı: salt-okunur, opsiyonel
`joint_id` filtresi, deterministik artan `id` sırası, parametreli SQL,
bilinmeyen/boş için `[]`, mevcut hiçbir fonksiyon değişmedi.

## 10. Governance adapter behaviour

**EN.** `project_joint_revisions_bulk(joint_id: Optional[int] = None) -> list[JointRevisionProjection]`
in `backend/governance/adapters/joint_revision.py`: sources ids via
`list_joint_revisions()` through the existing `_joints_service()`
deferred-import helper (no new import pattern); maps each id through
the existing, canonical `project_joint_revision()` — a deliberate,
documented N+1 pattern that guarantees zero duplication of the
existing `_STATUS_MAP` logic; preserves source ordering; never writes
anywhere; returns `[]` on any internal read failure rather than
raising, mirroring `project_joint_revision()`'s own fail-closed
design.

**TR.** Yukarıdaki İngilizce bölümün karşılığı: id'ler
`list_joint_revisions()` üzerinden `_joints_service()` yardımcısıyla
alınıyor; her id mevcut canonical `project_joint_revision()`'dan
geçiriliyor (kasıtlı N+1, mapping tekrarı sıfır); kaynak sırası
korunuyor; hiçbir yere yazmıyor; iç hata durumunda `[]` dönüyor,
hata fırlatmıyor.

## 11. API contract

**EN.** `GET /api/governance/joint-revisions` (optional
`?joint_id=<int>`): calls `project_joint_revisions_bulk()` exactly
once; always `200` for a well-formed request (empty result is `[]`,
not `404` — a list endpoint's empty result is not an error, unlike
the single-record endpoint's "this specific id does not exist");
non-integer `joint_id` produces FastAPI's standard `422`; response is
a bare JSON array of `JointRevisionProjection.model_dump(mode="json")`
objects — no wrapper, no pagination metadata; GET-only (verified:
`POST` → `405`, no `PUT`/`PATCH`/`DELETE` route exists); no direct
`backend.joints.service` or SQL access from the handler; the existing
singular `GET /joint-revision/{revision_id}` route, and the generic
`/{aggregate_id}/history` and `/{aggregate_id}/status` routes, are
unaffected (verified both by route-path distinctness and by
regression tests).

**TR.** Yukarıdaki İngilizce bölümün karşılığı: opsiyonel
`joint_id`, her zaman `200` (boş `[]`, `404` değil), geçersiz tip
`422`, çıplak JSON array, GET-only, mevcut route'lar etkilenmedi.

## 12. Frontend behaviour

**EN.** An additive "Joint Revision List (read-only)" card inside the
existing `page-governance` workspace (no new page). Optional joint-ID
filter input (empty → lists all); "List" button calls
`govLoadJointRevisions()`, which builds the query string via
`URLSearchParams` only (never string concatenation), issues a `GET`
with no request body, and never re-sorts, paginates, or client-side
filters the response — rendering exactly one table row per API item,
in the exact order received. Loading, empty (`[]` → translated
empty-state, not an error), and error (translated generic message, no
internal detail) states are all handled. All API values are rendered
through the existing `govEsc()` helper.

**TR.** Mevcut `page-governance` workspace'i içinde katmalı bir
"Joint Revision List (read-only)" kartı (yeni sayfa yok). Opsiyonel
joint-ID filtre girdisi; "Listele" butonu `govLoadJointRevisions()`'ı
çağırır, query string'i yalnızca `URLSearchParams` ile oluşturur, body
içermeyen bir `GET` gönderir, response'u asla yeniden sıralamaz,
paginate etmez veya client-side filtrelemez — API'den gelen her öğe
için, alınan sırayla, tam olarak bir tablo satırı render eder.
Loading, empty ve error durumlarının hepsi ele alınmıştır. Tüm API
değerleri mevcut `govEsc()` yardımcısı üzerinden render edilir.

## 13. TR/EN i18n

**EN.** 11 new keys under `gov.jrlist.*` (section title/description,
filter label/placeholder, load button, empty state, invalid-input
message, generic error, result-count prefix, two column labels), full
TR/EN parity verified independently three ways:
`tests/test_i18n_key_parity.py` (6/6), the JS harness's own
`gov.jrlist.*`-scoped parity check, and
`tests/test_faz_2_8_11_stage4_frontend.py`'s exact-count check
(80/80, corrected in Stage 5).

**TR.** `gov.jrlist.*` altında 11 yeni key, TR/EN parite üç bağımsız
yolla doğrulandı: `tests/test_i18n_key_parity.py` (6/6), JS
harness'in kendi `gov.jrlist.*`-kapsamlı parite kontrolü, ve
`tests/test_faz_2_8_11_stage4_frontend.py`'nin exact-count kontrolü
(80/80, Stage 5'te düzeltildi).

## 14. Security and mutation boundaries

**EN.** No new write path exists anywhere in this phase. The new
route reuses the existing `user` auth dependency (verified:
unauthenticated request → `401`). No governance event is ever
appended by the new code path (verified by test with a real event
store). AST-based compatibility guards confirm the new adapter
function and route handler contain no mutation/persistence method
calls, no raw SQL, and no second status-mapping table.

**TR.** Bu fazda hiçbir yerde yeni bir yazma yolu yok. Yeni route
mevcut `user` auth bağımlılığını yeniden kullanır (doğrulandı:
kimliksiz istek → `401`). Yeni kod yolu hiçbir zaman bir governance
event eklemez (gerçek bir event store ile test edildi). AST tabanlı
compatibility guard'ları, yeni adaptör fonksiyonunun ve route
handler'ının hiçbir mutation/persistence çağrısı, raw SQL veya ikinci
bir status-mapping tablosu içermediğini doğrular.

## 15. Deterministic ordering

**EN.** Ascending revision `id` order is established once in
`list_joint_revisions()` and never re-sorted at any later layer
(adapter, API, or frontend) — verified end-to-end by a dedicated
backend test, an API test, and a JS harness scenario using an
intentionally out-of-order fixture (ids 3, 1, 2) to prove rendering
order matches source order, not a re-sort.

**TR.** Artan revision `id` sırası yalnızca `list_joint_revisions()`'da
kurulur ve sonraki hiçbir katmanda (adaptör, API veya frontend)
yeniden sıralanmaz — uçtan uca bir backend testi, bir API testi ve
kasıtlı olarak sırasız bir fixture (id 3, 1, 2) kullanan bir JS
harness senaryosuyla doğrulandı.

## 16. Error and empty-state behaviour

**EN.** Source-layer failures never raise past the adapter (fail-
closed to `[]`, verified with a simulated internal exception carrying
a fake file path — the path never appears in the HTTP response).
Empty results at every layer (source, adapter, API, frontend) are
treated as a legitimate, non-error outcome, never conflated with an
actual failure.

**TR.** Kaynak-katmanı hataları adaptörün ötesine hiçbir zaman
sızmaz (fail-closed olarak `[]`, sahte bir dosya yolu taşıyan simüle
edilmiş bir iç exception ile doğrulandı — yol HTTP response'unda hiç
görünmüyor). Her katmandaki (kaynak, adaptör, API, frontend) boş
sonuçlar meşru, hata-olmayan bir çıktı olarak ele alınır, gerçek bir
hatayla asla karıştırılmaz.

## 17. Test coverage matrix

**EN.** See Stage 5's own coverage matrix (reproduced verbatim, no
gap found, no new test added in Stage 5):

- **Source accessor**: all-records listing, optional filter, `id ASC`,
  empty list, read-only, parameterized SQL, existing-accessor
  regression — `tests/test_joints_foundation.py`.
- **Governance adapter**: reuses public accessor, reuses canonical
  mapping, no new status map, preserves ordering, empty list, no
  mutation, deferred-import safety —
  `tests/governance/adapters/test_joint_revision.py`,
  `tests/governance/test_compatibility.py`.
- **API**: exact route, optional integer filter, empty `200 []`, raw
  array, GET-only, no route conflict, no direct service/SQL access, no
  detail leakage, existing-route regression —
  `tests/governance/test_joint_revision_bulk_api.py`,
  `tests/governance/test_compatibility.py`.
- **Frontend**: additive card, optional filter, GET-only/no body,
  `URLSearchParams`, invalid-input no-fetch, loading/empty/error
  states, backend order preserved, one row per item, safe escaping,
  existing CSS classes, existing functions intact, TR/EN parity —
  `tests/js/run_governance_workspace_tests.js`.

**TR.** Stage 5'in kendi coverage matrisi (aynen yeniden üretildi,
eksik bulunmadı, Stage 5'te yeni test eklenmedi) — yukarıdaki
İngilizce tablo, aynı dosya referanslarıyla.

## 18. Regression results

**EN.**

```
Full suite:            1919/1919 passed
Governance suite:      292/292 passed
JS governance harness: 160/160 passed
TR/EN key parity:      6/6 passed
```

All reconfirmed by direct execution immediately before writing this
report (not carried over from an earlier stage's report).

**TR.** Yukarıdaki sayılar, bu rapor yazılmadan hemen önce doğrudan
komut çalıştırılarak yeniden doğrulandı (önceki bir stage raporundan
kopyalanmadı).

## 19. Quality gate results

**EN.** `tools/run_quality_gate.py` → **6/6 PASSED**: git diff
--check, Python compile validation, JSON validity (27 files), TR/EN
key parity, 5 JavaScript harnesses, full pytest suite. Reconfirmed by
direct execution before this report.

**TR.** `tools/run_quality_gate.py` → **6/6 PASSED**, bu rapordan
hemen önce doğrudan çalıştırılarak yeniden doğrulandı.

## 20. Protected-file integrity

**EN.** `backend/app.py`, `frontend/index.html`'s pre-Stage-4 sections,
`backend/governance/ownership.py`, `backend/governance/store.py`,
`backend/governance/service.py`, `backend/governance/events.py`,
`backend/governance/transitions.py`, `backend/joints/schema.py`,
`backend/joints/exceptions.py`, and every function in
`backend/joints/service.py` other than the one new
`list_joint_revisions()` — all verified byte-identical to the
pre-phase baseline via SHA256/`git diff` comparison at every stage
boundary throughout the phase. `backend/library/data/` — including
`washer_resolution_ledger.json` — is untouched
(`git diff --name-only 79cd36b0..HEAD -- backend/library/data` is
empty; SHA256 confirmed identical). README.md and VERSION were not
touched in this phase.

**TR.** Yukarıdaki dosyaların tümü, faz boyunca her stage sınırında
SHA256/`git diff` karşılaştırmasıyla faz-öncesi tabana byte-identical
olarak doğrulandı. `backend/library/data/` — `washer_resolution_ledger.json`
dahil — dokunulmadı. README.md ve VERSION bu fazda dokunulmadı.

## 21. Non-goals

**EN.** Explicitly out of scope, none of which were attempted:
resolving washer resolution's open/blocked records with assumed
standard data; a governance projection registry; a cross-mechanism
consistency validator; joint revision write-synchronization; any new
governance mutation endpoint; pagination, sorting, search, or export
on the new list endpoint; README/VERSION currency (deferred
separately); any new ADR.

**TR.** Açıkça kapsam dışı, hiçbiri denenmedi: washer resolution'ın
açık/bloklu kayıtlarını varsayımsal standart verileriyle çözmek;
governance projection registry; cross-mechanism consistency
validator; joint revision write-synchronization; herhangi bir yeni
governance mutation endpoint'i; yeni liste endpoint'inde pagination,
sorting, search veya export; README/VERSION güncelliği (ayrıca
ertelendi); herhangi bir yeni ADR.

## 22. Known limitations

**EN.** The new endpoint has no pagination — acceptable at the
current, small dataset size per the Stage 1 contract's explicit
tradeoff, but would need revisiting if the dataset grows substantially
or a future phase adds it deliberately. The bulk adapter's N+1 query
pattern (one query per revision beyond the initial listing query) is
a deliberate, documented tradeoff for the same reason. Neither is a
defect; both are explicit, evidence-based scope decisions recorded in
Stage 1.

**TR.** Yeni endpoint'in pagination'ı yok — Stage 1 kontratının açık
ödünleşimine göre mevcut, küçük veri seti boyutunda kabul edilebilir,
ancak veri seti önemli ölçüde büyürse veya gelecekte bir faz bunu
bilinçli olarak eklerse yeniden ele alınmalı. Toplu adaptörün N+1
sorgu deseni aynı nedenle kasıtlı, dokümante edilmiş bir ödünleşimdir.
İkisi de bir kusur değil; ikisi de Stage 1'de kaydedilmiş, açık,
kanıta dayalı kapsam kararlarıdır.

## 23. Backward compatibility

**EN.** Every change in this phase is purely additive. Reverting the
phase's commits removes only new functions/routes/UI elements and
restores no previously-working behavior, because nothing existing was
modified. The existing single-record endpoint, its schema, and every
existing governance/joints function remain usable throughout and
after this phase with no behavior change. No database migration was
introduced.

**TR.** Bu fazdaki her değişiklik saf katmalıdır. Fazın commit'lerini
geri almak yalnızca yeni fonksiyonları/route'ları/UI öğelerini
kaldırır, çünkü mevcut hiçbir şey değiştirilmedi. Hiçbir veritabanı
migration'ı getirilmedi.

## 24. Operational/release readiness

**EN.** Full suite green (1919/1919), quality gate green (6/6),
working tree clean, all protected files verified byte-identical, no
engineering data changed. The branch is ready for review and merge
pending human approval; this report does not itself constitute merge
authorization.

**TR.** Tam suite yeşil (1919/1919), quality gate yeşil (6/6),
working tree temiz, tüm korunan dosyalar byte-identical doğrulandı,
mühendislik verisi değişmedi. Branch, insan onayı beklenerek review
ve merge için hazır; bu rapor kendi başına merge yetkilendirmesi
oluşturmaz.

## 25. Commit history

**EN.**

```
df6e8058497c29f5a6d95fdfbf13dfd44f80d76e  docs: lock Phase 2.8.14 joint revision bulk visibility scope
9640eba0b21b62c194f0e235dd4d607ec1876799  feat(governance): add joint revision bulk projection source
076321cf39938617b3575c7d0a020b462b6621aa  feat(governance): expose joint revision bulk read API
7e2f6b7ff6184501f48f99cbd46acd8dbc73d805  feat(frontend): add joint revision governance list
efc2c9e84cd343628831748362a7ce5e42f01b8f  test(governance): complete joint revision list regression coverage
```

Each hash independently re-verified against `git log` immediately
before writing this report, not copied from any prior stage's report
without verification.

**TR.** Yukarıdaki commit zinciri, bu rapor yazılmadan hemen önce
`git log` ile bağımsız olarak yeniden doğrulandı.

## 26. Final acceptance criteria

**EN.** Per the Stage 1 contract's §21: the new accessor, adapter
function, and route exist exactly as specified; every protected file
is byte-identical; the full suite and quality gate pass at 100%; the
new JS scenarios pass; TR/EN parity holds; a completion report
matching this format is delivered. **All criteria met.**

**TR.** Stage 1 kontratının §21'ine göre: yeni erişimci, adaptör
fonksiyonu ve route tam olarak belirtildiği gibi mevcut; her korunan
dosya byte-identical; tam suite ve quality gate %100 geçiyor; yeni JS
senaryoları geçiyor; TR/EN parite sağlanıyor; bu formata uygun bir
completion report teslim ediliyor. **Tüm kriterler karşılandı.**

## 27. Next-phase recommendations

**EN.**

- **Candidate A — README/VERSION maintenance.** `README.md` still
  shows a stale version/phase table (last verified at Faz 2.8.14
  Stage 1's own repository analysis) and `VERSION` is stale. Small,
  independent, risk-free maintenance task, no precondition.
- **Candidate B — Joint revision list UX refinements** (pagination,
  sorting, search, export). **Not implemented in this phase.** Should
  only be considered if real usage demonstrates an actual need — no
  such evidence exists yet.
- **Candidate C — Governance projection registry / cross-mechanism
  consistency validator.** Still premature: no second or third
  write-integrated mechanism has emerged since this was deferred in
  Faz 2.8.12 Stage 4. Should only be revisited if that precondition
  changes.

None of these is scoped or approved by this report; each requires its
own future analysis and Stage 1 contract if pursued.

**TR.**

- **Aday A — README/VERSION bakımı.** `README.md` hâlâ bayat bir
  sürüm/faz tablosu gösteriyor, `VERSION` bayat. Küçük, bağımsız,
  risksiz bakım işi, ön koşulu yok.
- **Aday B — Joint revision liste UX iyileştirmeleri** (pagination,
  sorting, search, export). **Bu fazda uygulanmadı.** Yalnızca gerçek
  kullanım gerçek bir ihtiyaç gösterirse değerlendirilmeli — şu an
  böyle bir kanıt yok.
- **Aday C — Governance projection registry / cross-mechanism
  consistency validator.** Hâlâ prematüre: Faz 2.8.12 Stage 4'te
  ertelendiğinden beri ikinci veya üçüncü bir yazma-entegre mekanizma
  ortaya çıkmadı. Yalnızca bu ön koşul değişirse yeniden ele
  alınmalı.

Bunların hiçbiri bu rapor tarafından kapsamlanmış veya onaylanmış
değildir; her biri izlenirse kendi gelecekteki analizini ve Stage 1
kontratını gerektirir.
