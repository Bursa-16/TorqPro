# Phase 2.8.14 Stage 1 — Joint Revision Governance Bulk Visibility: Scope Lock and Integration Contract

- Status: **Stage 1 complete** (scope lock and integration contract
  only). Phase 2.8.14 as a whole is **not** complete — Stages 2–6
  remain (see Section 20, "Stage Plan"). Do not read this document as
  a phase completion report.
- Depends on:
  `docs/adr/ADR-0014-engineering-governance-architecture.md`,
  `docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md`,
  `docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
  `docs/phases/PHASE_2.8.13_COMPLETION_REPORT.md`.
- Baseline: branch `main`, HEAD `79cd36b0fcf97dac9280874abdd7c25130ecd59e`
  at the time this phase's branch
  (`feature/faz-2.8.14-joint-revision-bulk-visibility`) was cut.
  Working tree was clean. Full suite 1871/1871, quality gate 6/6 —
  both reconfirmed before this document was written.

---

## 1. Phase objective / Faz amacı

**EN.** Phase 2.8.13 made the single-record `joint_revision`
governance projection reachable through one read-only lookup
(`GET /api/governance/joint-revision/{revision_id}`), but a caller
must already know a `revision_id` — there is no way to discover or
browse joint revisions from the governance workspace. Phase 2.8.14
closes that specific gap: it adds a read-only, **bulk** view of the
same, already-existing projection, without altering the single-record
lookup, its response shape, or any existing governance capability.

**TR.** Faz 2.8.13, tekil `joint_revision` governance projeksiyonunu
tek bir salt-okunur sorguyla (`GET /api/governance/joint-revision/{revision_id}`)
erişilebilir hale getirdi, ancak çağıranın önceden bir `revision_id`
bilmesi gerekiyor — governance workspace üzerinden joint revision'ları
keşfetmenin/taramanın hiçbir yolu yok. Faz 2.8.14 tam olarak bu
boşluğu kapatır: aynı, zaten var olan projeksiyonun salt-okunur,
**toplu** bir görünümünü ekler; tekil sorguyu, onun response şeklini
veya herhangi bir mevcut governance yeteneğini değiştirmeden.

## 2. Repository baseline / Depo taban durumu

**EN.** Verified by direct inspection immediately before drafting
this contract: branch `main`, HEAD
`79cd36b0fcf97dac9280874abdd7c25130ecd59e`, working tree clean, tag
`2.8.13` present, full pytest suite **1871/1871 passed**, quality gate
(`tools/run_quality_gate.py`) **6/6 PASSED**,
`tests/js/run_governance_workspace_tests.js` **98/98 assertions
passed**. No branch or commit anywhere in the repository (`git log
--all`) references "2.8.14" prior to this document.

**TR.** Bu kontrat yazılmadan hemen önce doğrudan incelemeyle
doğrulandı: branch `main`, HEAD
`79cd36b0fcf97dac9280874abdd7c25130ecd59e`, working tree temiz, `2.8.13`
tag'i mevcut, tam pytest suite **1871/1871 passed**, quality gate
(`tools/run_quality_gate.py`) **6/6 PASSED**,
`tests/js/run_governance_workspace_tests.js` **98/98 assertion
passed**. Depodaki hiçbir branch veya commit (`git log --all`) bu
belgeden önce "2.8.14" ifadesine referans vermiyor.

## 3. Existing joint revision flow / Mevcut joint revision akışı

**EN.** The authoritative source is `backend/joints/service.py`
(no separate `store.py` or `models.py` exists in `backend/joints/` —
persistence is inline SQL against `backend.app.conn()`, and the DDL
lives in `backend/joints/schema.py`). Its only read accessors are
`get_joint(joint_id)`, `list_joints(project_id: int | None = None)`,
and `get_joint_revision(revision_id)`. **There is no
`list_joint_revisions()` accessor of any kind today.** The
`backend/joints` package exposes **no HTTP API at all** — it is
consumed only in-process, by `backend/governance/adapters/joint_revision.py`
(read-only projection, Faz 2.8.12 Stage 4.2) and by
`backend/production_validation/service.py` (which queries the
`joints`/`joint_revisions` tables directly via raw SQL, bypassing
`backend.joints.service` entirely — an existing, pre-2.8.14 pattern
this phase does not touch or endorse).

The governance adapter's single-record function,
`project_joint_revision(revision_id)`, calls
`backend.joints.service.get_joint_revision(revision_id)` through a
deferred, function-body-only import (`_joints_service()`), a mitigation
empirically proven necessary and sufficient in the Faz 2.8.12 Stage
4.1 spike (see `PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md`)
because `backend.joints.service` imports `backend.app` at module
level, and `backend.app` imports `backend.governance.api` at module
level — a real circular-import risk if the adapter imported
`backend.joints.service` at its own module level.

**TR.** Otoritatif kaynak `backend/joints/service.py`'dir (`backend/joints/`
içinde ayrı bir `store.py` veya `models.py` yok — kalıcılık,
`backend.app.conn()` üzerinden satır içi SQL ile yapılıyor, DDL ise
`backend/joints/schema.py`'de). Mevcut tek okuma erişimcileri
`get_joint(joint_id)`, `list_joints(project_id: int | None = None)` ve
`get_joint_revision(revision_id)`'dir. **Bugün hiçbir türde
`list_joint_revisions()` erişimcisi yok.** `backend/joints` paketinin
**hiçbir HTTP API'si yok** — yalnızca in-process olarak,
`backend/governance/adapters/joint_revision.py` (salt-okunur
projeksiyon, Faz 2.8.12 Stage 4.2) ve `backend/production_validation/service.py`
(bu, `joints`/`joint_revisions` tablolarını `backend.joints.service`'i
tamamen atlayarak doğrudan raw SQL ile sorgular — 2.8.14'ten önce var
olan, bu fazın dokunmadığı veya onaylamadığı mevcut bir desen)
tarafından tüketiliyor.

Governance adaptörünün tekil-kayıt fonksiyonu,
`project_joint_revision(revision_id)`, `backend.joints.service.get_joint_revision(revision_id)`'i
gecikmeli, yalnızca fonksiyon-gövdesi içi bir import (`_joints_service()`)
üzerinden çağırır — bu, Faz 2.8.12 Stage 4.1 spike'ında ampirik olarak
gerekli ve yeterli kanıtlanmış bir önlemdir, çünkü
`backend.joints.service` modül seviyesinde `backend.app`'i import
eder, `backend.app` da modül seviyesinde `backend.governance.api`'yi
import eder — adaptör `backend.joints.service`'i kendi modül
seviyesinde import etseydi gerçek bir döngüsel-import riski olurdu.

## 4. User and engineering problem / Kullanıcı ve mühendislik problemi

**EN.** A governance workspace user who wants to see the review state
of joint revisions today must already know each `revision_id` — there
is no discovery path. This makes the existing single-record lookup
useful only when the ID is already known from elsewhere (e.g. a
support ticket, a log line), not for general oversight of joint
review activity. This gap was explicitly named — but left as a
conditional, not a confirmed requirement — in
`PHASE_2.8.13_COMPLETION_REPORT.md` Section 16 ("if real usage of the
joint-revision lookup surfaces a need for bulk/list visibility").
**No repository evidence confirms this usage-driven need has actually
materialized; this phase proceeds on the same assumption the prior
phase's own report flagged as conditional, not on new evidence.**

**TR.** Bugün joint revision'ların inceleme durumunu görmek isteyen
bir governance workspace kullanıcısının önceden her `revision_id`'yi
bilmesi gerekiyor — keşif yolu yok. Bu, mevcut tekil-kayıt sorgusunu
yalnızca ID başka bir yerden zaten biliniyorsa (ör. bir destek
kaydı, bir log satırı) kullanışlı kılıyor, joint inceleme
aktivitesinin genel gözetimi için değil. Bu boşluk,
`PHASE_2.8.13_COMPLETION_REPORT.md` Bölüm 16'da açıkça adlandırıldı —
ama kesin bir gereksinim değil, koşullu olarak bırakıldı ("joint
revision lookup'ın gerçek kullanımı toplu/liste görünürlük ihtiyacı
ortaya çıkarırsa"). **Bu kullanım-güdümlü ihtiyacın gerçekten
oluştuğunu doğrulayan hiçbir depo kanıtı yok; bu faz, yeni bir kanıta
değil, önceki fazın kendi raporunun koşullu diye işaretlediği aynı
varsayıma dayanarak ilerliyor.**

## 5. Architectural decision / Mimari karar

**EN.** The mandated priority order was evaluated in strict sequence:

1. **Reuse an existing public read-only accessor.** None exists —
   `list_joints()` lists joints, not revisions; `get_joint_revision()`
   requires an ID the caller does not have.
2. **Compose over existing services via the governance adapter.**
   Not possible without a source of revision IDs. `list_joints()`
   returns joint IDs, not revision IDs, and a joint's
   `current_revision_id` field (visible on the joint row) reflects
   only the *currently approved* revision, not the full revision
   history (draft/review/rejected revisions are invisible through
   that field). Composition cannot produce a complete, correct list
   without a new accessor.
3. **Access the persistence/store layer directly from governance.**
   Rejected. `backend/joints/` has no separate store module — the
   only way to do this would be raw SQL against
   `joint_revisions` from within `backend/governance/`, exactly the
   pattern `ADR-0014` records as the **documented reason Production
   Validation and the legacy calculation-revision workflow received a
   NO-GO** in Phase 2.8.12 ("the legacy workflow has no separate
   service module to adapt against, only SQL embedded directly in
   `backend/app.py` route handlers"). Joint revisions do have a
   service-module boundary (`backend/joints/service.py`) — bypassing
   it would discard exactly the property that made the joint-revision
   adapter approvable in the first place.
4. **Import a private/internal function.** None exists to import —
   `backend/joints/service.py`'s only helper, `_row()`, is a
   row-to-dict formatter, not a query function; there is no private
   listing function hidden behind the public API.
5. **Add an additive, read-only public accessor.** This is the
   smallest change that preserves the established architecture: it
   keeps governance dependent on `backend/joints/service.py`'s public
   surface (never on its private internals or its table schema
   directly), exactly mirroring how `get_joint_revision()` is already
   consumed.

**Conclusion: Option B is required.** `backend/joints/service.py`
needs one new, additive, read-only public accessor.

**TR.** Zorunlu öncelik sırası sıkı bir sırayla değerlendirildi:

1. **Mevcut bir public salt-okunur erişimciyi yeniden kullan.** Yok —
   `list_joints()` joint'leri listeler, revision'ları değil;
   `get_joint_revision()` çağıranın sahip olmadığı bir ID gerektirir.
2. **Governance adaptörü üzerinden mevcut servisleri composition
   yap.** Bir revision ID kaynağı olmadan mümkün değil. `list_joints()`
   joint ID'leri döndürür, revision ID'leri değil; bir joint'in
   `current_revision_id` alanı (joint satırında görünür) yalnızca *o
   an onaylı* revision'ı yansıtır, tam revision geçmişini değil (draft/
   review/rejected revision'lar bu alan üzerinden görünmez).
   Composition, yeni bir erişimci olmadan eksiksiz ve doğru bir liste
   üretemez.
3. **Persistence/store katmanına governance'tan doğrudan eriş.**
   Reddedildi. `backend/joints/`'in ayrı bir store modülü yok — bunu
   yapmanın tek yolu `backend/governance/` içinden `joint_revisions`
   tablosuna karşı raw SQL olurdu — tam olarak `ADR-0014`'ün, Faz
   2.8.12'de Production Validation ve legacy calculation-revision
   akışının **NO-GO almasının dokümante edilmiş nedeni** olarak
   kaydettiği desen ("legacy akışın adapte edilecek ayrı bir servis
   modülü yok, yalnızca `backend/app.py` route handler'larına gömülü
   SQL var"). Joint revision'ların bir servis-modülü sınırı var
   (`backend/joints/service.py`) — bunu atlamak, joint-revision
   adaptörünü başlangıçta onaylanabilir kılan özelliği tam olarak
   ortadan kaldırırdı.
4. **Private/internal bir fonksiyonu import et.** Import edilecek
   hiçbir şey yok — `backend/joints/service.py`'nin tek yardımcısı
   `_row()`, bir satır-sözlük biçimlendiricisi, bir sorgu fonksiyonu
   değil; public API'nin arkasında saklı bir private listeleme
   fonksiyonu yok.
5. **Katmalı, salt-okunur bir public erişimci ekle.** Bu, kurulu
   mimariyi koruyan en küçük değişikliktir: governance'ı
   `backend/joints/service.py`'nin public yüzeyine bağımlı tutar
   (asla private iç yapısına veya tablo şemasına doğrudan değil),
   `get_joint_revision()`'ın zaten nasıl tüketildiğini birebir
   yansıtır.

**Sonuç: Seçenek B gereklidir.** `backend/joints/service.py`'ye yeni,
katmalı, salt-okunur bir public erişimci gerekiyor.

## 6. Service-layer modification decision / Servis-katmanı değişiklik kararı

**EN.** Exact signature, derived from `list_joints()`'s established
convention (same file, same module):

```python
def list_joint_revisions(joint_id: int | None = None) -> list:
    """Read-only listing of joint revisions, optionally filtered by
    joint_id. Mirrors list_joints()'s filter/ordering convention
    exactly. Returns raw revision rows (same shape as
    get_joint_revision()'s return value) in ascending id order — the
    same deterministic, insertion-order convention list_joints()
    already uses; no new ordering convention is introduced.
    """
    with conn() as c:
        if joint_id is not None:
            rows = c.execute(
                "SELECT * FROM joint_revisions WHERE joint_id=? ORDER BY id", (joint_id,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM joint_revisions ORDER BY id").fetchall()
    return [_row(r) for r in rows]
```

Design decisions, each derived from existing repository convention,
not invented:

- **Return type**: `list[dict]`, same shape as every other accessor
  in this file (reuses `_row()`, adds no new serialization).
- **Filter parameter**: `joint_id: int | None = None`, same optional-
  filter pattern as `list_joints(project_id: int | None = None)`.
- **Ordering**: `ORDER BY id` ascending — identical to `list_joints()`.
  Not `ORDER BY joint_id, revision_no`: introducing a different
  ordering convention for this one accessor, when the sibling
  accessor in the same file uses `ORDER BY id`, would create an
  unexplained inconsistency for no stated benefit. If future usage
  needs revision-number-grouped ordering, that is a separate,
  explicitly-scoped decision.
- **Error behavior**: never raises for an unknown `joint_id` — returns
  an empty list, matching `list_joints(project_id=...)`'s behavior for
  an unknown `project_id` (no existence check is performed there
  either).
- **No new table, index, or migration.** Existing indexes
  (`idx_joint_revisions_joint_id`) already support this query.
- Added to `__all__` in the same file, alongside `list_joints`.

**TR.** `list_joints()`'in kurulu konvansiyonundan (aynı dosya, aynı
modül) türetilen kesin imza yukarıdaki kod bloğunda verilmiştir.

Her biri mevcut depo konvansiyonundan türetilmiş, uydurulmamış tasarım
kararları:

- **Dönüş tipi**: `list[dict]`, bu dosyadaki her diğer erişimciyle
  aynı şekil (`_row()`'u yeniden kullanır, yeni bir serileştirme
  eklemez).
- **Filtre parametresi**: `joint_id: int | None = None`,
  `list_joints(project_id: int | None = None)` ile aynı opsiyonel-
  filtre deseni.
- **Sıralama**: artan `ORDER BY id` — `list_joints()` ile birebir
  aynı. `ORDER BY joint_id, revision_no` değil: aynı dosyadaki kardeş
  erişimci `ORDER BY id` kullanırken bu tek erişimci için farklı bir
  sıralama konvansiyonu getirmek, belirtilmiş bir fayda olmadan
  açıklanmamış bir tutarsızlık yaratırdı. Gelecekte revision-numarası-
  gruplu sıralama ihtiyacı doğarsa, bu ayrı, açıkça kapsamlanmış bir
  karardır.
- **Hata davranışı**: bilinmeyen bir `joint_id` için asla hata
  fırlatmaz — boş liste döner, `list_joints(project_id=...)`'in
  bilinmeyen bir `project_id` için davranışıyla eşleşir (orada da
  varlık kontrolü yapılmıyor).
- **Yeni tablo, index veya migration yok.** Mevcut index'ler
  (`idx_joint_revisions_joint_id`) bu sorguyu zaten destekliyor.
- Aynı dosyada `__all__`'a, `list_joints`'in yanına eklenir.

## 7. Approved data flow / Onaylanan veri akışı

**EN.**

```
Frontend (frontend/index.html, page-governance)
   ↓  GET, apiRequest(), optional ?joint_id= query param
Governance read API (backend/governance/api.py)
   GET /api/governance/joint-revisions
   ↓  one call per revision id, no store dependency
joint_revision governance adapter (backend/governance/adapters/joint_revision.py)
   project_joint_revisions_bulk(joint_id) -> list[JointRevisionProjection]
     internally: list_joint_revisions(joint_id) for ids, then
     project_joint_revision(id) per id — reuses 100% of the existing
     single-record mapping logic, adds none of its own
   ↓  deferred import, function-body only (unchanged mitigation)
authoritative joint revision mechanism (backend/joints/service.py — ONE additive accessor)
   list_joint_revisions(joint_id) -> list[dict]  (NEW)
   get_joint_revision(revision_id) -> dict  (UNCHANGED, reused)
```

The dependency direction is unchanged from Faz 2.8.12/2.8.13:
governance depends on the authoritative mechanism through the
existing adapter pattern; nothing in `backend/joints/` imports
governance.

**TR.** Yukarıdaki diyagram, Faz 2.8.12/2.8.13'ten değişmeyen bağımlılık
yönünü gösterir: governance, mevcut adaptör deseni üzerinden otoritatif
mekanizmaya bağımlıdır; `backend/joints/` içindeki hiçbir şey
governance'ı import etmez.

## 8. Backend contract / Backend sözleşmesi

**EN.** `backend/joints/service.py`: add `list_joint_revisions()`
exactly as specified in Section 6. No existing function's signature,
body, or behavior changes. `__all__` gains one new entry.

**TR.** `backend/joints/service.py`: Bölüm 6'da belirtildiği gibi
tam olarak `list_joint_revisions()` eklenir. Hiçbir mevcut
fonksiyonun imzası, gövdesi veya davranışı değişmez. `__all__`'a bir
yeni giriş eklenir.

## 9. Governance adapter contract / Governance adaptör sözleşmesi

**EN.** `backend/governance/adapters/joint_revision.py`: add
`project_joint_revisions_bulk(joint_id: int | None = None) -> list[JointRevisionProjection]`.
Implementation: call `list_joint_revisions(joint_id)` (via the same
`_joints_service()` deferred-import helper already in the file — no
new import pattern) to obtain revision ids, then call the existing
`project_joint_revision(id)` once per id and collect the results.
This is a deliberate N+1 pattern, not an oversight: it guarantees
zero duplication of the existing, already-tested status-mapping logic
in `_STATUS_MAP`/`_unsupported_or_invalid`, at the cost of one extra
query per revision. Accepted because this phase introduces no
pagination (Section 13) — the result set is the full, currently-small
table content, and premature optimization here would duplicate
tested logic for no measured need. If a future phase adds pagination
or the dataset grows enough to matter, revisit this tradeoff
separately.

No change to `project_joint_revision`, `JointRevisionProjection`,
`ProjectionOutcome`, `_STATUS_MAP`, or any existing export.

**TR.** `backend/governance/adapters/joint_revision.py`:
`project_joint_revisions_bulk(joint_id: int | None = None) -> list[JointRevisionProjection]`
eklenir. Uygulama: revision id'lerini almak için `list_joint_revisions(joint_id)`'i
(dosyada zaten var olan aynı `_joints_service()` gecikmeli-import
yardımcısı üzerinden — yeni bir import deseni yok) çağırır, sonra
her id için mevcut `project_joint_revision(id)`'i bir kez çağırıp
sonuçları toplar. Bu kasıtlı bir N+1 desenidir, gözden kaçma değil:
mevcut, zaten test edilmiş `_STATUS_MAP`/`_unsupported_or_invalid`
durum-haritalama mantığının sıfır tekrarını garanti eder, bedeli
revision başına bir ekstra sorgudur. Kabul edilme nedeni: bu faz
pagination getirmiyor (Bölüm 13) — sonuç kümesi, tablo içeriğinin
tamamı (şu an küçük) ve burada erken optimizasyon, ölçülmüş bir
ihtiyaç olmadan test edilmiş mantığı tekrarlardı. Gelecekte bir faz
pagination eklerse veya veri seti önemli ölçüde büyürse, bu ödünleşim
ayrıca ele alınmalıdır.

`project_joint_revision`, `JointRevisionProjection`,
`ProjectionOutcome`, `_STATUS_MAP` veya herhangi bir mevcut export'ta
değişiklik yok.

## 10. API contract / API sözleşmesi

**EN.**

```http
GET /api/governance/joint-revisions
GET /api/governance/joint-revisions?joint_id={joint_id}
```

- **Query parameters**: `joint_id` (optional, integer). Absent →
  all joint revisions across all joints. Present → only revisions of
  that joint, mirroring `list_joint_revisions(joint_id)`'s filter.
- **Pagination**: none in this phase. Explicit decision, not an
  oversight — see Section 9's tradeoff note. Deferred to a future,
  separately-scoped phase if real dataset size or usage demonstrates
  a need.
- **Default ordering**: ascending `id` — inherited unchanged from
  `list_joint_revisions()` (Section 6); the API adds no ordering
  logic of its own.
- **Empty result**: `200` with a JSON array `[]` — a list endpoint
  with no matching records is not an error, unlike the single-record
  endpoint's `404` for "this specific id does not exist" (these are
  different semantics for different endpoint shapes, both already
  established elsewhere in this codebase: compare `list_joints`-backed
  endpoints' behavior, which is also non-erroring on an empty result).
- **Invalid filter**: `joint_id` is typed as `int` in the route
  signature; a non-integer value produces FastAPI's standard `422`
  validation error — no custom validation logic is added.
- **Response schema**: JSON array of the existing
  `JointRevisionProjection.model_dump(mode="json")` objects, unchanged
  shape, one array item per matched revision. No new field, no
  wrapper object, no envelope (e.g. no `{"items": [...], "total": n}`)
  — kept as a bare array to match the response-shape simplicity of
  `list_joints`-style endpoints elsewhere and to avoid inventing an
  envelope convention this codebase does not otherwise use.
- **HTTP status**: always `200` for a well-formed request (an empty
  array is not an error; each item's own `outcome` field, exactly as
  in the single-record endpoint, communicates per-item projection
  results — `unsupported_status`/`invalid_source_record`/
  `source_unavailable` items are included in the array, not filtered
  out or treated as request errors).
- **Relationship to the single-record endpoint**: fully independent;
  `GET /joint-revision/{revision_id}` is unchanged in every respect
  (URL, schema, status mapping). The new endpoint does not replace,
  redirect to, or share a handler function with it — it composes over
  the same adapter-level projection function per item (Section 9).
- **Mutation**: none. No `POST`/`PUT`/`PATCH`/`DELETE` exists or is
  added for this resource in this phase.

**TR.** Yukarıdaki İngilizce bölümün karşılığı, aynı kararlarla:

- **Query parametreleri**: `joint_id` (opsiyonel, integer). Yoksa →
  tüm joint'lerdeki tüm revision'lar. Varsa → yalnızca o joint'in
  revision'ları, `list_joint_revisions(joint_id)`'in filtresini
  yansıtır.
- **Pagination**: bu fazda yok. Açık bir karar, gözden kaçma değil —
  bkz. Bölüm 9'un ödünleşim notu. Gerçek veri seti boyutu veya
  kullanım bir ihtiyaç gösterirse gelecekte, ayrıca kapsamlanmış bir
  fazda ele alınmalıdır.
- **Varsayılan sıralama**: artan `id` — değişmeden `list_joint_revisions()`'dan
  (Bölüm 6) miras alınır; API kendi sıralama mantığını eklemez.
- **Boş sonuç**: `200` ve boş bir JSON dizisi `[]` — eşleşen kayıt
  olmayan bir liste endpoint'i hata değildir, tekil-kayıt
  endpoint'inin "bu belirli id yok" için verdiği `404`'ten farklı
  olarak (bunlar farklı endpoint şekilleri için farklı semantiklerdir,
  ikisi de bu kod tabanında başka yerde zaten kurulu: `list_joints`
  destekli endpoint'lerin davranışını karşılaştırın, o da boş sonuçta
  hata vermiyor).
- **Geçersiz filtre**: `joint_id` route imzasında `int` tipinde;
  integer olmayan bir değer FastAPI'nin standart `422` doğrulama
  hatasını üretir — özel bir doğrulama mantığı eklenmez.
- **Response şeması**: mevcut `JointRevisionProjection.model_dump(mode="json")`
  nesnelerinin JSON dizisi, değişmeyen şekil, eşleşen her revision
  için bir dizi öğesi. Yeni alan yok, wrapper nesne yok, zarf yok
  (ör. `{"items": [...], "total": n}` yok) — bu kod tabanının başka
  yerde kullanmadığı bir zarf konvansiyonu uydurmamak ve
  `list_joints`-tarzı endpoint'lerin response-şekli sadeliğiyle
  eşleşmek için çıplak bir dizi olarak bırakılır.
- **HTTP status**: iyi biçimlendirilmiş bir istek için her zaman
  `200` (boş dizi hata değildir; her öğenin kendi `outcome` alanı, tam
  olarak tekil-kayıt endpoint'indeki gibi, öğe-bazlı projeksiyon
  sonuçlarını iletir — `unsupported_status`/`invalid_source_record`/
  `source_unavailable` öğeleri diziye dahildir, filtrelenmez veya
  istek hatası olarak ele alınmaz).
- **Tekil-kayıt endpoint'iyle ilişki**: tamamen bağımsız;
  `GET /joint-revision/{revision_id}` her açıdan değişmeden kalır
  (URL, şema, status haritalama). Yeni endpoint onun yerine geçmez,
  ona yönlendirmez veya onunla bir handler fonksiyonu paylaşmaz — öğe
  başına aynı adaptör-seviyesi projeksiyon fonksiyonu üzerinden
  composition yapar (Bölüm 9).
- **Mutation**: yok. Bu kaynak için bu fazda hiçbir
  `POST`/`PUT`/`PATCH`/`DELETE` yok ve eklenmiyor.

## 11. Frontend contract / Frontend sözleşmesi

**EN.** Extend the existing "Joint Revision Projection (read-only)"
card inside `page-governance` (added in Faz 2.8.13 Stage 3) — no new
standalone page, no new sidebar entry. Add a "List all" / optional
joint-id-filtered list view beneath the existing single-ID lookup
input, calling the new endpoint through the existing `apiRequest`
helper, GET only. Each row renders using the same five-outcome
rendering logic already established for the single-record card
(Faz 2.8.13 Stage 3) — no new status-rendering branch is invented;
the existing per-outcome rendering function is reused per list item.
Empty result renders an explicit "no revisions found" state, not a
blank area.

**TR.** `page-governance` içindeki mevcut "Joint Revision Projection
(read-only)" kartını (Faz 2.8.13 Stage 3'te eklendi) genişlet — yeni
bir bağımsız sayfa yok, yeni bir sidebar girişi yok. Mevcut tekil-ID
lookup girdisinin altına bir "Tümünü listele" / opsiyonel joint-id-
filtreli liste görünümü ekle, yeni endpoint'i mevcut `apiRequest`
yardımcısı üzerinden, yalnızca GET olarak çağırarak. Her satır, tekil-
kayıt kartı için zaten kurulu olan aynı beş-durum render mantığını
kullanır (Faz 2.8.13 Stage 3) — yeni bir durum-render dalı
uydurulmaz; mevcut öğe-bazlı render fonksiyonu liste öğesi başına
yeniden kullanılır. Boş sonuç, boş bir alan değil, açık bir "revision
bulunamadı" durumu render eder.

## 12. TR/EN i18n contract / TR/EN i18n sözleşmesi

**EN.** New keys follow the existing `gov.jr.*` namespace established
in Faz 2.8.13 (e.g. `gov.jrlist.*` for list-specific strings: list
button label, empty-state message, optional filter input label). Full
TR/EN parity is mandatory for every new key, verified by the existing
`tests/test_i18n_key_parity.py` mechanism — no new parity-checking
mechanism is introduced.

**TR.** Yeni key'ler, Faz 2.8.13'te kurulan mevcut `gov.jr.*` ad
alanını takip eder (ör. liste-özel string'ler için `gov.jrlist.*`:
listele buton etiketi, boş-durum mesajı, opsiyonel filtre girdi
etiketi). Her yeni key için tam TR/EN parite zorunludur, mevcut
`tests/test_i18n_key_parity.py` mekanizmasıyla doğrulanır — yeni bir
parite-kontrol mekanizması getirilmez.

## 13. Error and empty-state behaviour / Hata ve boş-durum davranışı

**EN.** No exception path exists in the new bulk adapter function
beyond what `project_joint_revision` already handles per item (never
raises — see Section 9's docstring reference). An unknown `joint_id`
filter produces an empty array, `200`, not an error (Section 6, 10).
The frontend renders an explicit empty-state message rather than a
silent blank list.

**TR.** Yeni toplu adaptör fonksiyonunda, `project_joint_revision`'ın
öğe başına zaten ele aldığının (asla hata fırlatmaz — Bölüm 9'un
docstring referansına bakın) ötesinde bir exception yolu yok. Bilinmeyen
bir `joint_id` filtresi boş bir dizi üretir, `200`, hata değil (Bölüm
6, 10). Frontend, sessiz boş bir liste yerine açık bir boş-durum
mesajı render eder.

## 14. Deterministic ordering rules / Deterministik sıralama kuralları

**EN.** Ascending `id` order, inherited unchanged from
`list_joint_revisions()` (Section 6) through the adapter to the API
response — no re-sorting at any layer. Repeated identical requests
against an unchanged database return identical order, matching the
determinism convention already verified for the single-record
endpoint in Faz 2.8.13 Stage 4.

**TR.** Artan `id` sırası, `list_joint_revisions()`'dan (Bölüm 6)
adaptör üzerinden API response'una kadar değişmeden miras alınır — hiçbir
katmanda yeniden sıralama yok. Değişmemiş bir veritabanına karşı
tekrarlanan aynı istekler aynı sırayı döner, Faz 2.8.13 Stage 4'te
tekil-kayıt endpoint'i için zaten doğrulanmış determinizm
konvansiyonuyla eşleşir.

## 15. Allowed files / İzin verilen dosyalar

**EN.** Stage 2–6 (this document authorizes the *plan*, not the code —
each stage still requires its own execution):
`backend/joints/service.py` (one new accessor only),
`backend/governance/adapters/joint_revision.py` (one new function
only), `backend/governance/api.py` (one new route only),
`frontend/index.html` (additive extension of the existing governance
card only), test files under `tests/` and `tests/js/` matching the
existing naming convention for this area, and one new completion-
report document in `docs/phases/`.

**TR.** Stage 2–6 (bu belge *planı* yetkilendirir, kodu değil — her
stage kendi uygulamasını hâlâ gerektirir):
`backend/joints/service.py` (yalnızca bir yeni erişimci),
`backend/governance/adapters/joint_revision.py` (yalnızca bir yeni
fonksiyon), `backend/governance/api.py` (yalnızca bir yeni route),
`frontend/index.html` (mevcut governance kartının yalnızca katmalı
genişletmesi), bu alan için mevcut isimlendirme konvansiyonuna uygun
`tests/` ve `tests/js/` altındaki test dosyaları, ve `docs/phases/`
altında bir yeni completion-report belgesi.

## 16. Protected files / Korunan dosyalar

**EN.** Every file this phase does not explicitly list in Section 15,
with particular emphasis on: `backend/governance/adapters/joint_revision.py`'s
existing `project_joint_revision`, `JointRevisionProjection`,
`ProjectionOutcome`, `_STATUS_MAP`, `_unsupported_or_invalid`
(unchanged, only a new function added alongside);
`backend/governance/api.py`'s existing `governance_joint_revision`
handler and `_JOINT_REVISION_OUTCOME_STATUS` mapping (unchanged, only
a new route added); every other function in
`backend/joints/service.py` (`create_joint`, `get_joint`,
`list_joints`, `archive_joint`, `create_joint_revision`,
`get_joint_revision`, `submit_joint_revision`,
`approve_joint_revision`, `reject_joint_revision`,
`assert_revision_belongs_to_joint` — byte-identical); `backend/joints/schema.py`,
`backend/joints/exceptions.py`, `backend/governance/ownership.py`,
`backend/governance/store.py`, `backend/governance/service.py`,
`backend/governance/events.py`, `backend/governance/transitions.py`,
`backend/production_validation/`, `backend/engineering_core/`,
`backend/vdi2230_core/`, `backend/calculation_engine/`,
`backend/library/` (all byte-identical to this phase's baseline).

**TR.** Bu fazın Bölüm 15'te açıkça listelemediği her dosya, özellikle
şunlar vurgulanarak: `backend/governance/adapters/joint_revision.py`'nin
mevcut `project_joint_revision`, `JointRevisionProjection`,
`ProjectionOutcome`, `_STATUS_MAP`, `_unsupported_or_invalid`'i
(değişmez, yanına yalnızca yeni bir fonksiyon eklenir);
`backend/governance/api.py`'nin mevcut `governance_joint_revision`
handler'ı ve `_JOINT_REVISION_OUTCOME_STATUS` haritalaması
(değişmez, yalnızca yeni bir route eklenir);
`backend/joints/service.py`'deki diğer her fonksiyon (byte-identical);
`backend/joints/schema.py`, `backend/joints/exceptions.py`,
`backend/governance/ownership.py`, `backend/governance/store.py`,
`backend/governance/service.py`, `backend/governance/events.py`,
`backend/governance/transitions.py`, `backend/production_validation/`,
`backend/engineering_core/`, `backend/vdi2230_core/`,
`backend/calculation_engine/`, `backend/library/` (bu fazın tabanına
byte-identical).

## 17. Non-goals / Kapsam dışı

**EN.** Explicitly out of scope for Phase 2.8.14, restated from the
approved analysis:

- Resolving washer resolution's 71 `open` / 5
  `blocked_authoritative_source` records with assumed standard data.
- Producing or estimating ISO 7093 dimensional values.
- A governance projection registry.
- A cross-mechanism consistency validator.
- Joint revision write-synchronization (a washer-resolution-style
  write path for joints).
- Any new governance mutation endpoint.
- Migrating any existing joint revision record.
- Changing any existing public API (single-record endpoint, adapter
  function, or `backend/joints/service.py` function).
- Any refactor beyond the one additive accessor specified in Section 6.
- Pagination of the new list endpoint (Section 10).
- README.md and VERSION currency — deferred to a separate, small
  maintenance PR, per the approved analysis.

**TR.** Faz 2.8.14 için açıkça kapsam dışı, onaylanmış analizden
yeniden ifade edilmiştir:

- Washer resolution'ın 71 `open` / 5 `blocked_authoritative_source`
  kaydını varsayımsal standart verileriyle çözmek.
- ISO 7093 boyutsal değerleri üretmek veya tahmin etmek.
- Governance projection registry.
- Cross-mechanism consistency validator.
- Joint revision write-synchronization (joint'ler için washer-
  resolution-tarzı bir yazma yolu).
- Herhangi bir yeni governance mutation endpoint'i.
- Mevcut herhangi bir joint revision kaydını migrate etmek.
- Mevcut herhangi bir public API'yi değiştirmek (tekil-kayıt
  endpoint'i, adaptör fonksiyonu veya `backend/joints/service.py`
  fonksiyonu).
- Bölüm 6'da belirtilen tek katmalı erişimcinin ötesinde herhangi bir
  refactor.
- Yeni liste endpoint'inin pagination'ı (Bölüm 10).
- README.md ve VERSION güncelliği — onaylanmış analize göre ayrı,
  küçük bir maintenance PR'a ertelenmiştir.

## 18. Security and mutation boundaries / Güvenlik ve mutation sınırları

**EN.** The new route reuses the existing
`backend.api.dependencies.user` dependency (no new auth mechanism, no
new permission model). No new write path is created anywhere in this
phase — the new accessor, adapter function, and route are all
read-only, verified by the same category of AST-based
GET-only/no-write-route guards `tests/governance/test_compatibility.py`
already applies to the single-record endpoint (extended, not
duplicated, to cover the new route).

**TR.** Yeni route, mevcut `backend.api.dependencies.user`
bağımlılığını yeniden kullanır (yeni bir auth mekanizması yok, yeni
bir izin modeli yok). Bu fazda hiçbir yerde yeni bir yazma yolu
oluşturulmaz — yeni erişimci, adaptör fonksiyonu ve route'un hepsi
salt-okunurdur, `tests/governance/test_compatibility.py`'nin tekil-
kayıt endpoint'ine zaten uyguladığı aynı kategori AST-tabanlı GET-only/
no-write-route guard'larıyla doğrulanır (yeni route'u kapsayacak
şekilde genişletilir, tekrarlanmaz).

## 19. Test contract / Test sözleşmesi

**EN.**

- `tests/test_joints_foundation.py` (or a new, clearly-named sibling
  file if the maintainers prefer isolating list-accessor tests):
  unit tests for `list_joint_revisions()` — no filter, `joint_id`
  filter, unknown `joint_id` (empty list), ordering.
- `tests/governance/adapters/test_joint_revision.py`: unit tests for
  `project_joint_revisions_bulk()` — empty database, single joint
  with multiple revisions, multiple joints, mixed-outcome records
  (reusing existing fixture patterns for unsupported/invalid/
  unavailable outcomes from the single-record tests where possible).
- `tests/governance/test_joint_revision_api.py`: new route tests —
  200 with populated array, 200 with empty array, `joint_id` filter,
  invalid `joint_id` → 422, response schema matches
  `JointRevisionProjection` per item.
- `tests/governance/test_compatibility.py`: extend the existing
  route-inventory/GET-only/no-write-route/approved-import-direction
  guards to include the new route, exactly as Faz 2.8.13 Stage 2 did
  for the single-record route.
- `tests/js/run_governance_workspace_tests.js`: new scenarios for the
  list UI (populated, empty, filtered).
- `tests/test_i18n_key_parity.py`: must continue to pass unmodified
  with the new `gov.jrlist.*` keys present in both languages.
- Full suite (`pytest -q`) must remain 100% passing; `tools/run_quality_gate.py`
  must remain 6/6.

**TR.** Yukarıdaki İngilizce bölümün karşılığı, aynı test kapsamıyla:
`list_joint_revisions()` için unit testler, `project_joint_revisions_bulk()`
için unit testler, yeni route testleri (dolu dizi, boş dizi, filtre,
geçersiz filtre), `test_compatibility.py` guard genişletmesi, JS
harness yeni senaryolar, i18n parite testinin değişmeden geçmesi, tam
suite'in %100 geçmesi, quality gate'in 6/6 kalması.

## 20. Stage 2–6 implementation plan / Stage 2–6 uygulama planı

**Stage 2 — Read-only source accessor and governance adapter**
- Kesin kapsam: `backend/joints/service.py`'ye `list_joint_revisions()`
  (Section 6), `backend/governance/adapters/joint_revision.py`'ye
  `project_joint_revisions_bulk()` (Section 9).
- Değiştirilecek: bu iki dosya, artı ilgili unit testler.
- Protected: Section 16'daki tüm dosyalar.
- Acceptance: yeni fonksiyonlar için unit testler yeşil; mevcut tüm
  testler yeşil; `git diff` yalnızca additive.
- Test komutu: `pytest tests/test_joints_foundation.py tests/governance/adapters/test_joint_revision.py -q`
- Completion condition: iki fonksiyon da mevcut, test edilmiş, mevcut
  hiçbir davranış değişmemiş.
- Önerilen commit: `feat(joints,governance): add read-only joint revision bulk listing accessors`

**Stage 3 — Read-only API**
- Kesin kapsam: `backend/governance/api.py`'ye `GET /joint-revisions`
  route'u (Section 10).
- Acceptance: route testleri yeşil, `test_compatibility.py` guard'ları
  genişletildi ve yeşil.
- Test komutu: `pytest tests/governance -q`
- Önerilen commit: `feat(governance): expose joint revision bulk listing API`

**Stage 4 — Frontend and TR/EN i18n**
- Kesin kapsam: Section 11, 12.
- Test komutu: `node tests/js/run_governance_workspace_tests.js`,
  `pytest tests/test_i18n_key_parity.py -q`
- Önerilen commit: `feat(governance): add joint revision bulk list view to workspace`

**Stage 5 — Backend, frontend and architecture tests**
- Kesin kapsam: eksik kalan test kapsamının tamamlanması, edge-case'ler
  (boş DB, çok joint/çok revision, karışık outcome).
- Test komutu: tam suite + JS harness.
- Önerilen commit: `test(governance): complete joint revision bulk listing coverage`

**Stage 6 — Full regression, quality gate, completion report, release preparation**
- Kesin kapsam: `tools/run_quality_gate.py`, clean-clone doğrulama,
  completion report (2.8.13 formatında), patch+bundle+SHA256SUMS.
- Test komutu: `pytest -q`, `tools/run_quality_gate.py`,
  tüm JS harness'ler.
- Önerilen commit: `docs: finalize phase 2.8.14 completion package`

## 21. Acceptance criteria / Kabul kriterleri

**EN.** Phase 2.8.14 is complete only when: the new accessor, adapter
function, and route exist exactly as specified above; every file in
Section 16 is byte-identical to this phase's baseline; the full
pytest suite and quality gate pass at 100%; the new JS scenarios pass;
TR/EN parity holds for every new key; an independent clean-clone
reproduction confirms identical results; a completion report matching
the 2.8.13 format is delivered with patch, bundle, and SHA256SUMS.

**TR.** Faz 2.8.14 yalnızca şu durumda tamamlanmış sayılır: yeni
erişimci, adaptör fonksiyonu ve route yukarıda belirtildiği gibi tam
olarak mevcut; Bölüm 16'daki her dosya bu fazın tabanına byte-identical;
tam pytest suite ve quality gate %100 geçiyor; yeni JS senaryoları
geçiyor; her yeni key için TR/EN parite sağlanıyor; bağımsız bir
clean-clone tekrarı aynı sonuçları doğruluyor; 2.8.13 formatına uygun
bir completion report, patch, bundle ve SHA256SUMS ile teslim ediliyor.

## 22. Rollback and compatibility expectations / Geri alma ve uyumluluk beklentileri

**EN.** Every change in this phase is purely additive: reverting the
phase's commits removes only new functions/routes/UI elements and
restores no previously-working behavior, because nothing existing is
modified. The single-record endpoint, its schema, and every existing
governance/joints function remain usable throughout and after this
phase with no behavior change. No database migration is introduced,
so rollback requires no data migration either.

**TR.** Bu fazdaki her değişiklik saf katmalıdır: fazın commit'lerini
geri almak yalnızca yeni fonksiyonları/route'ları/UI öğelerini
kaldırır ve daha önce çalışan hiçbir davranışı geri getirmez, çünkü
mevcut hiçbir şey değiştirilmemiştir. Tekil-kayıt endpoint'i, şeması
ve her mevcut governance/joints fonksiyonu bu faz boyunca ve sonrasında
davranış değişikliği olmadan kullanılabilir kalır. Hiçbir veritabanı
migration'ı getirilmez, bu yüzden geri alma bir veri migration'ı da
gerektirmez.

---

*End of Stage 1 contract. Coding begins only with explicit, separate
approval for Stage 2.*

*Stage 1 kontratının sonu. Kodlama, yalnızca Stage 2 için açık, ayrı
bir onayla başlar.*
