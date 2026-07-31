# Phase 2.8.13 Stage 1 — Governance Workspace Completion: Scope Lock and Integration Contract

- Status: **Stage 1 complete** (scope lock and integration contract
  only). Phase 2.8.13 as a whole is **not** complete — Stages 2–5
  remain (see Section 12, "Stage Plan"). Do not read this document as
  a phase completion report.
- Depends on:
  `docs/adr/ADR-0014-engineering-governance-architecture.md`,
  `docs/adr/ADR-0015-washer-resolution-governance-integration.md`,
  `docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md`,
  `docs/phases/PHASE_2.8.12_COMPLETION_REPORT.md`.
- Baseline: branch `main`, HEAD `cb20e69` at the time this phase's
  branch (`feature/faz-2.8.13-governance-workspace-completion`) was
  cut. Working tree was clean. Governance suite 233/233, full suite
  1851/1851, quality gate 6/6 — all reconfirmed before this document
  was written.

---

## 1. Purpose / Amaç

**EN.** `backend/governance/adapters/joint_revision.py` was delivered
complete, tested, and mechanically import-safety-verified in Phase
2.8.12 Stage 4.2, but it has no production consumer: no API route
calls `project_joint_revision`, and no frontend page renders its
output. Phase 2.8.13 closes exactly this visibility gap — it makes
the *existing* read-only projection reachable through one new
read-only API route and a small, additive extension of the existing
generic governance frontend workspace. It defines no new governance
capability, no new projection logic, and no new source of truth.

**TR.** `backend/governance/adapters/joint_revision.py` Faz 2.8.12
Stage 4.2'de tam, test edilmiş ve mekanik olarak import-güvenliği
doğrulanmış şekilde teslim edildi, ancak hiçbir üretim tüketicisi
yok: `project_joint_revision`'ı çağıran bir API rotası yok, çıktısını
gösteren bir frontend sayfası yok. Faz 2.8.13 tam olarak bu görünürlük
boşluğunu kapatır — *mevcut* salt-okunur projeksiyonu, yeni bir
salt-okunur API rotası ve mevcut genel governance frontend çalışma
alanının küçük, katmalı bir genişletmesi üzerinden erişilebilir hale
getirir. Yeni bir governance yeteneği, yeni bir projeksiyon mantığı
veya yeni bir doğruluk kaynağı tanımlamaz.

## 2. Current Gap / Mevcut Boşluk

**EN.** Confirmed by repository inspection (this phase's approved
Stage 1 analysis, and re-verified while drafting this document):

- `backend/governance/adapters/joint_revision.py` already exists
  (Faz 2.8.12 Stage 4.2) and exports `project_joint_revision`,
  `JointRevisionProjection`, `ProjectionOutcome`, `SOURCE_SYSTEM`.
- It is tested: `tests/governance/adapters/test_joint_revision.py`,
  plus the import-order/circular-dependency assertions in
  `tests/governance/test_compatibility.py`.
- `git grep` for `joint_revision` across `backend/api`, `backend/app.py`,
  and `frontend/` returns **zero** results — no production API route
  or frontend code references it.
- The generic governance frontend workspace (`page-governance` in
  `frontend/index.html`) only knows the domain-agnostic
  `aggregate_id` / `aggregate_type` history/status query pattern; it
  has no joint-revision-specific input or rendering.
- This phase closes **only** this visibility gap: one new read-only
  route, one additive frontend extension. It does not add a second
  projection, a second adapter, or any new field to the existing
  `JointRevisionProjection` model.

**TR.** Depo incelemesiyle doğrulandı (bu fazın onaylanmış Stage 1
analizi ve bu belge yazılırken yeniden doğrulandı):

- `backend/governance/adapters/joint_revision.py` zaten mevcut (Faz
  2.8.12 Stage 4.2) ve `project_joint_revision`,
  `JointRevisionProjection`, `ProjectionOutcome`, `SOURCE_SYSTEM`
  sembollerini dışa aktarıyor.
- Test edilmiş durumda:
  `tests/governance/adapters/test_joint_revision.py`, artı
  `tests/governance/test_compatibility.py`'deki import-sırası/döngüsel-
  bağımlılık doğrulamaları.
- `backend/api`, `backend/app.py` ve `frontend/` içinde
  `joint_revision` için `git grep` **sıfır** sonuç veriyor — hiçbir
  üretim API rotası veya frontend kodu ona referans vermiyor.
- Genel governance frontend çalışma alanı (`frontend/index.html`
  içindeki `page-governance`) yalnızca alan-bağımsız `aggregate_id` /
  `aggregate_type` history/status sorgu desenini biliyor; joint
  revision'a özgü bir girdi veya render yok.
- Bu faz **yalnızca** bu görünürlük boşluğunu kapatır: bir yeni
  salt-okunur rota, bir katmalı frontend genişlemesi. İkinci bir
  projeksiyon, ikinci bir adaptör veya mevcut
  `JointRevisionProjection` modeline yeni bir alan eklemez.

## 3. Authority and Ownership / Yetki ve Sahiplik

**EN.**

- The joint revision engineering mechanism (`backend.joints.service`,
  the `joint_revisions` SQLite table) remains the sole authoritative
  source for joint revision review status. This phase does not change
  that.
- Governance is a **read-only consumer** of joint revision data via
  the existing `project_joint_revision` function. This phase adds
  transport (API + UI) around that existing call, not new read logic.
- Governance must not update joint revision status. No route
  introduced by this phase may call anything in `backend.joints.*`
  other than the existing read path already used by
  `project_joint_revision`.
- Governance must not persist events for this projection. No
  `GovernanceEvent` is constructed, no call into
  `backend.governance.service`'s write functions, and no write to
  `backend.governance.store` occurs anywhere in this phase's scope.
- Governance must not create an alternative joint revision lifecycle.
  The only status vocabulary surfaced is the one
  `joint_revision.py`'s existing `_STATUS_MAP` already produces
  (`ReviewStatus`); no new status value, transition, or lifecycle
  group is introduced.
- The adapter (`backend/governance/adapters/joint_revision.py`)
  itself is a **protected file** for this phase (Section 10) — it
  already exposes no mutation method, and this phase does not change
  that fact by editing it.

**TR.**

- Joint revision mühendislik mekanizması (`backend.joints.service`,
  `joint_revisions` SQLite tablosu) joint revision inceleme durumu
  için tek yetkili kaynak olmaya devam eder. Bu faz bunu değiştirmez.
- Governance, mevcut `project_joint_revision` fonksiyonu üzerinden
  joint revision verisinin **salt-okunur tüketicisidir**. Bu faz bu
  mevcut çağrının etrafına taşıma (API + UI) ekler, yeni bir okuma
  mantığı değil.
- Governance joint revision durumunu güncelleyemez. Bu fazın
  eklediği hiçbir rota, `project_joint_revision`'ın zaten kullandığı
  mevcut okuma yolu dışında `backend.joints.*` içindeki hiçbir şeyi
  çağıramaz.
- Governance bu projeksiyon için olay kalıcılaştıramaz. Bu fazın
  kapsamında hiçbir yerde `GovernanceEvent` oluşturulmaz,
  `backend.governance.service`'in yazma fonksiyonlarına çağrı
  yapılmaz ve `backend.governance.store`'a yazma gerçekleşmez.
- Governance alternatif bir joint revision yaşam döngüsü
  oluşturamaz. Yüzeye çıkarılan tek durum sözlüğü,
  `joint_revision.py`'nin mevcut `_STATUS_MAP`'inin zaten ürettiği
  sözlüktür (`ReviewStatus`); yeni bir durum değeri, geçiş veya
  yaşam döngüsü grubu tanıtılmaz.
- Adaptörün kendisi
  (`backend/governance/adapters/joint_revision.py`) bu faz için
  **korunan dosyadır** (Bölüm 10) — zaten hiçbir mutasyon metodu
  sunmuyor ve bu faz onu düzenleyerek bu gerçeği değiştirmez.

## 4. Approved Dependency Direction / Onaylı Bağımlılık Yönü

```text
Frontend
   ↓
Governance read API  (backend/governance/api.py, new GET route)
   ↓
joint_revision governance adapter  (backend/governance/adapters/joint_revision.py — unchanged)
   ↓
authoritative joint revision mechanism  (backend/joints/service.py, joint_revisions table)
```

**EN.** Reverse imports — anything in `backend/joints/` importing
from `backend/governance/`, or from this phase's new API route —
are explicitly prohibited. The existing deferred-import pattern in
`joint_revision.py` (`backend.joints.service` imported only inside
`_joints_service()`, never at module level) is the proven mitigation
for the one real circular-import risk already documented in Phase
2.8.12 Stage 4.1/4.2; this phase's new route must call
`project_joint_revision()` exactly as the adapter already expects and
must not reintroduce a module-level import of `backend.joints.*`
anywhere in `backend/governance/`.

**TR.** Ters importlar — `backend/joints/` içindeki herhangi bir
şeyin `backend/governance/`'dan veya bu fazın yeni API rotasından
import etmesi — açıkça yasaktır. `joint_revision.py`'deki mevcut
gecikmeli-import deseni (`backend.joints.service` yalnızca
`_joints_service()` içinde, asla modül seviyesinde import edilir)
Faz 2.8.12 Stage 4.1/4.2'de zaten belgelenen tek gerçek döngüsel-
import riski için kanıtlanmış çözümdür; bu fazın yeni rotası
`project_joint_revision()`'ı adaptörün zaten beklediği şekilde
çağırmalı ve `backend/governance/` içinde hiçbir yerde
`backend.joints.*`'ın modül seviyesinde bir importunu yeniden
tanıtmamalıdır.

## 5. Approved API Contract / Onaylı API Sözleşmesi

**EN.** Exactly one new route, read-only:

```http
GET /api/governance/joint-revision/{revision_id}
```

- **Path parameter:** `revision_id` (integer — matches
  `project_joint_revision(revision_id: int)`'s existing signature;
  no additional path or query parameters are added, since the
  adapter's signature takes only this one argument).
- **Authentication:** reuses the existing `backend.api.dependencies.user`
  dependency, exactly as every other governance route already does —
  no new authentication mechanism.
- **Response model:** the existing `JointRevisionProjection` fields,
  serialized as JSON — `source_system`, `joint_revision_id`,
  `source_status`, `lifecycle_group`, `canonical_status`, `outcome`,
  `safe_reason`. No field is added, renamed, or removed relative to
  the adapter's existing model.
- **Successful response (`outcome == "supported"`):** HTTP 200, body
  is `JointRevisionProjection.model_dump(mode="json")` — includes
  populated `source_status`, `lifecycle_group`, `canonical_status`.
- **Not-found behavior (`outcome == "not_found"`):** the adapter
  itself never raises for a missing record — it returns a
  `JointRevisionProjection` with `outcome="not_found"`. The route
  maps this to HTTP **404**, body containing the projection's
  `safe_reason` — mirrors the existing `_require_known_aggregate`
  404 pattern already used by `/{aggregate_id}/history` and
  `/{aggregate_id}/status`.
- **Unsupported/unprojectable-state behavior:** the adapter already
  supports two such outcomes and both must be distinguished, not
  collapsed into one generic error:
  - `outcome == "unsupported_status"` — a well-formed but
    unrecognized source status. Maps to HTTP **200** with the
    projection body as-is (`canonical_status` is `null`); this is a
    normal, expected result, not a failure — a client must be able to
    tell "record exists, status not yet in governance's closed
    vocabulary" apart from "record does not exist."
  - `outcome == "invalid_source_record"` — a malformed source record
    (missing/non-string status). Maps to HTTP **200** with the
    projection body as-is, same reasoning: this is data the adapter
    already classified safely, not a server error.
- **Internal-error behavior (`outcome == "source_unavailable"`):**
  returned by the adapter when the joints module fails to import or
  the underlying read raises any exception other than
  `JointRevisionNotFoundError`. Maps to HTTP **200** with the
  projection body as-is (the adapter has already reduced this to a
  safe, generic `safe_reason` — "Joint revision source data could not
  be read." / "Joint revision source module is unavailable." — never
  a raw exception, filesystem path, or traceback). The route
  performs no additional exception handling beyond calling the
  adapter, because `project_joint_revision` already never raises.
- **No path leakage, no traceback leakage:** the route must not wrap
  `project_joint_revision` in a `try/except` that could echo an
  exception's `str()`, a stack trace, or any filesystem path into the
  response — this is unnecessary because the adapter itself never
  raises, and adding such a handler would risk reintroducing exactly
  the leakage the adapter was built to prevent.
- **No write side effect, no governance event creation, no mutation
  of authoritative source data:** the route body is a single call to
  `project_joint_revision(revision_id)` and a status-code/serialization
  mapping of its result — no call into `backend.governance.service`,
  `backend.governance.store`, or any `backend.joints.*` function other
  than the one `project_joint_revision` already performs internally.
- **Explicitly not defined:** no `POST`, `PUT`, `PATCH`, or `DELETE`
  route for joint revisions. No query parameters.

**TR.** Tam olarak bir yeni rota, salt-okunur:

```http
GET /api/governance/joint-revision/{revision_id}
```

- **Yol parametresi:** `revision_id` (tamsayı —
  `project_joint_revision(revision_id: int)`'in mevcut imzasıyla
  eşleşir; adaptörün imzası yalnızca bu tek argümanı aldığı için ek
  yol veya sorgu parametresi eklenmez).
- **Kimlik doğrulama:** mevcut `backend.api.dependencies.user`
  bağımlılığını, diğer tüm governance rotalarının zaten yaptığı gibi
  yeniden kullanır — yeni bir kimlik doğrulama mekanizması yok.
- **Yanıt modeli:** mevcut `JointRevisionProjection` alanları, JSON
  olarak serileştirilmiş — `source_system`, `joint_revision_id`,
  `source_status`, `lifecycle_group`, `canonical_status`, `outcome`,
  `safe_reason`. Adaptörün mevcut modeline göre hiçbir alan
  eklenmez, yeniden adlandırılmaz veya kaldırılmaz.
- **Başarılı yanıt (`outcome == "supported"`):** HTTP 200, gövde
  `JointRevisionProjection.model_dump(mode="json")` — doldurulmuş
  `source_status`, `lifecycle_group`, `canonical_status` içerir.
- **Bulunamadı davranışı (`outcome == "not_found"`):** adaptörün
  kendisi eksik bir kayıt için asla hata fırlatmaz — `outcome="not_found"`
  ile bir `JointRevisionProjection` döndürür. Rota bunu HTTP
  **404**'e eşler, gövde projeksiyonun `safe_reason`'ını içerir —
  `/{aggregate_id}/history` ve `/{aggregate_id}/status`'ün zaten
  kullandığı mevcut `_require_known_aggregate` 404 desenini yansıtır.
- **Desteklenmeyen/projekte edilemeyen durum davranışı:** adaptör
  zaten iki böyle sonucu destekliyor ve ikisi de tek bir genel hataya
  indirgenmeden ayırt edilmelidir:
  - `outcome == "unsupported_status"` — iyi biçimlendirilmiş ama
    tanınmayan bir kaynak durumu. HTTP **200**'e, projeksiyon
    gövdesiyle olduğu gibi eşlenir (`canonical_status` `null`'dur);
    bu normal, beklenen bir sonuçtur, bir hata değil — bir istemci
    "kayıt var, durum henüz governance'ın kapalı sözlüğünde değil"
    ile "kayıt yok" arasındaki farkı ayırt edebilmelidir.
  - `outcome == "invalid_source_record"` — hatalı biçimlendirilmiş
    bir kaynak kaydı (eksik/string olmayan durum). HTTP **200**'e,
    projeksiyon gövdesiyle olduğu gibi eşlenir, aynı gerekçeyle: bu
    adaptörün zaten güvenli şekilde sınıflandırdığı veridir, bir
    sunucu hatası değil.
- **İç hata davranışı (`outcome == "source_unavailable"`):**
  joints modülü import edilemediğinde veya alttaki okuma
  `JointRevisionNotFoundError` dışında herhangi bir istisna
  fırlattığında adaptör tarafından döndürülür. HTTP **200**'e,
  projeksiyon gövdesiyle olduğu gibi eşlenir (adaptör bunu zaten
  güvenli, genel bir `safe_reason`'a indirgemiştir — asla ham bir
  istisna, dosya sistemi yolu veya traceback değil). Rota,
  adaptörü çağırmanın ötesinde ek bir istisna işleme yapmaz, çünkü
  `project_joint_revision` zaten asla hata fırlatmaz.
- **Yol sızıntısı yok, traceback sızıntısı yok:** rota,
  `project_joint_revision`'ı bir istisnanın `str()`'ini, bir yığın
  izini veya herhangi bir dosya sistemi yolunu yanıta sızdırabilecek
  bir `try/except` içine sarmamalıdır — bu gereksizdir çünkü
  adaptörün kendisi asla hata fırlatmaz ve böyle bir işleyici
  eklemek, tam olarak adaptörün önlemek için inşa edildiği sızıntıyı
  yeniden tanıtma riski taşır.
- **Yazma yan etkisi yok, governance olay oluşturma yok, yetkili
  kaynak verisinin mutasyonu yok:** rota gövdesi
  `project_joint_revision(revision_id)`'e tek bir çağrı ve sonucunun
  durum kodu/serileştirme eşlemesidir — `backend.governance.service`,
  `backend.governance.store`'a veya `project_joint_revision`'ın zaten
  dahili olarak gerçekleştirdiği fonksiyon dışında herhangi bir
  `backend.joints.*` fonksiyonuna çağrı yoktur.
- **Açıkça tanımlanmayan:** joint revision'lar için `POST`, `PUT`,
  `PATCH` veya `DELETE` rotası yok. Sorgu parametresi yok.

## 6. Frontend Contract / Frontend Sözleşmesi

**EN.** A minimal additive extension of the existing
`page-governance` workspace in `frontend/index.html`:

- Add one small input + button group (reusing the existing
  `form-row3` / `form-group` / `form-input` / `btn btn-primary` CSS
  classes already used by the "Aggregate Lookup" card) allowing entry
  of a joint revision identifier.
- On submit, call the new `GET /api/governance/joint-revision/{revision_id}`
  route via the existing `apiRequest` helper — the same helper
  `govLoad()` already uses.
- Render the existing projection fields as returned (`source_status`,
  `lifecycle_group`, `canonical_status`, `outcome`, `safe_reason`) —
  no new fields invented for display.
- Distinguish rendering for each outcome:
  - `supported` → normal status card.
  - `not_found` → the existing "empty state" treatment already used
    by `govRenderEmpty()` for the generic lookup's 404 case.
  - `unsupported_status` / `invalid_source_record` /
    `source_unavailable` → a clearly labeled non-error informational
    state (reusing existing alert/muted-text classes), not styled as
    if the request itself failed.
- TR/EN parity: every new user-facing string gets a `data-i18n` key
  in both the `en` and `tr` translation tables, following the
  existing `gov.*` key naming convention (e.g. `gov.joint_revision_*`).
  `tests/test_i18n_key_parity.py` must continue to pass with zero new
  parity gaps.
- Reuse existing CSS classes only — no new stylesheet rules, no new
  layout primitives.
- No new standalone page: this is an additive section inside the
  existing `page-governance` div, not a new `page-*` entry in the
  sidebar/router.

**TR.** `frontend/index.html` içindeki mevcut `page-governance`
çalışma alanının minimal, katmalı bir genişletmesi:

- "Aggregate Lookup" kartının zaten kullandığı mevcut `form-row3` /
  `form-group` / `form-input` / `btn btn-primary` CSS sınıflarını
  yeniden kullanan, bir joint revision tanımlayıcısı girişine izin
  veren küçük bir girdi + buton grubu ekle.
- Gönderimde, mevcut `apiRequest` yardımcı fonksiyonu üzerinden yeni
  `GET /api/governance/joint-revision/{revision_id}` rotasını çağır —
  `govLoad()`'un zaten kullandığı aynı yardımcı fonksiyon.
- Döndürüldüğü şekliyle mevcut projeksiyon alanlarını render et
  (`source_status`, `lifecycle_group`, `canonical_status`, `outcome`,
  `safe_reason`) — gösterim için yeni bir alan icat edilmez.
- Her sonuç için render'ı ayırt et:
  - `supported` → normal durum kartı.
  - `not_found` → genel arama için `govRenderEmpty()`'nin zaten
    kullandığı mevcut "boş durum" işlemi.
  - `unsupported_status` / `invalid_source_record` /
    `source_unavailable` → açıkça etiketlenmiş, hata olmayan bir
    bilgilendirme durumu (mevcut alert/muted-text sınıfları yeniden
    kullanılarak), isteğin kendisi başarısız olmuş gibi
    biçimlendirilmez.
- TR/EN uyumu: her yeni kullanıcıya görünen dize, mevcut `gov.*`
  anahtar adlandırma kuralını izleyerek (örn. `gov.joint_revision_*`)
  hem `en` hem `tr` çeviri tablolarında bir `data-i18n` anahtarı
  alır. `tests/test_i18n_key_parity.py` sıfır yeni uyum boşluğuyla
  geçmeye devam etmelidir.
- Yalnızca mevcut CSS sınıfları yeniden kullanılır — yeni bir
  stylesheet kuralı, yeni bir düzen ilkeli yok.
- Yeni bir bağımsız sayfa yok: bu, sidebar/router'da yeni bir
  `page-*` girişi değil, mevcut `page-governance` div'i içinde
  katmalı bir bölümdür.

## 7. Error Mapping / Hata Eşlemesi

**EN.** Only outcomes the current `joint_revision.py` implementation
already supports are mapped — no domain state is invented:

| `ProjectionOutcome` | Meaning (per adapter) | HTTP status | Notes |
|---|---|---|---|
| `supported` | Valid projection, record found and mapped | 200 | Normal case |
| `not_found` | No joint revision exists with this id | 404 | Matches existing `_require_known_aggregate` pattern |
| `unsupported_status` | Record found, source status not in the closed mapping vocabulary | 200 | Not an error — `canonical_status` is `null`, `safe_reason` explains why |
| `invalid_source_record` | Record found but malformed (missing/non-string status) | 200 | Not an error — same treatment as above |
| `source_unavailable` | Joints module import failed, or the underlying read raised (I/O, etc.) | 200 | Adapter already reduced this to a safe generic message; body carries `safe_reason` |

No separate "internal server error" (5xx) case is defined for this
route, because `project_joint_revision` is documented and tested to
never raise — every possible outcome is already represented by
`ProjectionOutcome`. If a future stage's testing discovers a code
path where the adapter *can* raise, that is a blocker to report, not
a state to invent a 500 response for silently.

**TR.** Yalnızca mevcut `joint_revision.py` uygulamasının zaten
desteklediği sonuçlar eşlenir — hiçbir alan durumu icat edilmez:

| `ProjectionOutcome` | Anlamı (adaptöre göre) | HTTP durumu | Notlar |
|---|---|---|---|
| `supported` | Geçerli projeksiyon, kayıt bulundu ve eşlendi | 200 | Normal durum |
| `not_found` | Bu id ile bir joint revision yok | 404 | Mevcut `_require_known_aggregate` desenine uyar |
| `unsupported_status` | Kayıt bulundu, kaynak durumu kapalı eşleme sözlüğünde değil | 200 | Hata değil — `canonical_status` `null`, `safe_reason` nedenini açıklar |
| `invalid_source_record` | Kayıt bulundu ama hatalı biçimlendirilmiş (eksik/string olmayan durum) | 200 | Hata değil — yukarıdakiyle aynı işlem |
| `source_unavailable` | Joints modülü import edilemedi veya alttaki okuma hata fırlattı (I/O vb.) | 200 | Adaptör bunu zaten güvenli, genel bir mesaja indirgemiştir; gövde `safe_reason` taşır |

Bu rota için ayrı bir "internal server error" (5xx) durumu
tanımlanmamıştır, çünkü `project_joint_revision`'ın asla hata
fırlatmadığı belgelenmiş ve test edilmiştir — her olası sonuç zaten
`ProjectionOutcome` tarafından temsil edilmektedir. Gelecekteki bir
aşamanın testi adaptörün *hata fırlatabildiği* bir kod yolu
keşfederse, bu sessizce bir 500 yanıtı icat edilecek bir durum değil,
raporlanacak bir engeldir.

## 8. Test Contract / Test Sözleşmesi

**EN.** Required for later stages (not implemented in Stage 1):

1. API success case — `GET` a revision id known to map to a
   supported status; assert 200 and the exact projection fields.
2. Not-found case — assert 404 and the existing empty-record message
   pattern.
3. Unsupported-state case — assert 200 for both
   `unsupported_status` and `invalid_source_record`, with
   `canonical_status` null and a non-empty `safe_reason`.
4. No source mutation — assert the `joint_revisions` table (or the
   relevant fixture data) is byte-identical before and after the
   route is called, for every outcome above.
5. No governance event persistence — assert the governance event
   store (test fixture) has zero new events after any call to this
   route, for every outcome above.
6. Real request-path import-order safety — extend
   `tests/governance/test_compatibility.py`'s existing AST/subprocess
   invariant checks to cover the new route's import path specifically
   (not just the adapter module in isolation), verifying the
   deferred-import mitigation holds when reached through
   `backend.governance.api` under real ASGI/TestClient request
   conditions, not just at collection time.
7. Existing governance route regression — the full existing
   `tests/governance/test_api.py` suite must continue to pass
   unmodified in behavior (only additive test functions may be
   added).
8. Frontend structural test — new DOM elements exist, are wired to
   the new route, and are absent from any unrelated page.
9. Frontend JS harness behavior — extend the relevant JS harness
   (whichever of the 5 existing harnesses under `tests/js/` already
   covers `frontend/index.html`'s governance workspace, or the
   closest applicable one) to cover the new outcome-rendering logic.
10. TR/EN translation parity — `tests/test_i18n_key_parity.py` passes
    with zero gaps for every new `gov.joint_revision_*` key.
11. Full governance suite — `tests/governance/` must remain 100%
    passing, count increasing only by the number of tests this phase
    adds.
12. Full repository suite — `pytest -q` at repository root must
    remain 100% passing.
13. Full quality gate — `tools/run_quality_gate.py` must report
    6/6 PASS.

**TR.** Sonraki aşamalar için gerekli (Stage 1'de uygulanmadı):

1. API başarı durumu — desteklenen bir duruma eşlendiği bilinen bir
   revision id'yi `GET` et; 200 ve tam projeksiyon alanlarını doğrula.
2. Bulunamadı durumu — 404 ve mevcut boş-kayıt mesaj desenini
   doğrula.
3. Desteklenmeyen-durum durumu — hem `unsupported_status` hem
   `invalid_source_record` için 200'ü, `canonical_status` null ve
   boş olmayan bir `safe_reason` ile doğrula.
4. Kaynak mutasyonu yok — yukarıdaki her sonuç için, rota çağrılmadan
   önce ve sonra `joint_revisions` tablosunun (veya ilgili test
   verisinin) bayt-bayt aynı olduğunu doğrula.
5. Governance olay kalıcılaştırması yok — yukarıdaki her sonuç için,
   bu rotaya yapılan herhangi bir çağrıdan sonra governance olay
   deposunun (test fixture) sıfır yeni olaya sahip olduğunu doğrula.
6. Gerçek istek-yolu import-sırası güvenliği —
   `tests/governance/test_compatibility.py`'nin mevcut AST/subprocess
   değişmez doğrulamalarını, yeni rotanın import yolunu özel olarak
   kapsayacak şekilde genişlet (yalnızca izole adaptör modülünü
   değil), gecikmeli-import çözümünün `backend.governance.api`
   üzerinden gerçek ASGI/TestClient istek koşulları altında,
   yalnızca toplama zamanında değil, geçerliliğini koruduğunu
   doğrula.
7. Mevcut governance rota regresyonu — mevcut
   `tests/governance/test_api.py` paketi davranış olarak değişmeden
   geçmeye devam etmelidir (yalnızca katmalı test fonksiyonları
   eklenebilir).
8. Frontend yapısal testi — yeni DOM elemanları var, yeni rotaya
   bağlı ve ilgisiz herhangi bir sayfada yok.
9. Frontend JS harness davranışı — ilgili JS harness'i (`tests/js/`
   altındaki 5 mevcut harness'ten `frontend/index.html`'in
   governance çalışma alanını zaten kapsayan, veya en uygun olanı)
   yeni sonuç-render mantığını kapsayacak şekilde genişlet.
10. TR/EN çeviri uyumu — `tests/test_i18n_key_parity.py`, her yeni
    `gov.joint_revision_*` anahtarı için sıfır boşlukla geçer.
11. Tam governance paketi — `tests/governance/` %100 geçer durumda
    kalmalı, sayı yalnızca bu fazın eklediği test sayısı kadar
    artmalı.
12. Tam depo paketi — depo kökünde `pytest -q` %100 geçer durumda
    kalmalı.
13. Tam kalite kapısı — `tools/run_quality_gate.py` 6/6 PASS
    bildirmeli.

## 9. Files Allowed to Change / Değişmesine İzin Verilen Dosyalar

**EN.** For the full phase (Stages 1–5 combined), only the following
files may change:

```text
backend/governance/api.py
backend/governance/adapters/__init__.py
frontend/index.html
tests/governance/
tests/js/
docs/phases/
docs/11_PRODUCT_BACKLOG.md
docs/314_Roadmap.md
docs/CHANGELOG.md
```

This list is **not** blanket permission to change every file in it.
Only files whose change is justified by an actual implementation need
identified during the stage that touches them may change. Stage 1
(this document) touches only `docs/phases/` — no other file in this
list is expected to change until Stage 2 or later.

**TR.** Tüm faz için (Stage 1–5 birleşik), yalnızca aşağıdaki
dosyalar değişebilir:

```text
backend/governance/api.py
backend/governance/adapters/__init__.py
frontend/index.html
tests/governance/
tests/js/
docs/phases/
docs/11_PRODUCT_BACKLOG.md
docs/314_Roadmap.md
docs/CHANGELOG.md
```

Bu liste, içindeki her dosyayı değiştirmek için genel bir izin
**değildir**. Yalnızca değişikliği, o dosyaya dokunan aşama sırasında
belirlenen gerçek bir uygulama ihtiyacıyla gerekçelendirilen dosyalar
değişebilir. Stage 1 (bu belge) yalnızca `docs/phases/`'a dokunur —
bu listedeki başka hiçbir dosyanın Stage 2 veya sonrasına kadar
değişmesi beklenmez.

## 10. Protected Files / Korunan Dosyalar

**EN.** No changes are allowed to the following unless a proven
blocker is found. If a blocker is found, the phase stops and reports
it instead of changing a protected file:

```text
backend/governance/adapters/joint_revision.py
backend/governance/store.py
backend/governance/service.py
backend/governance/events.py
backend/governance/transitions.py
backend/joints/
backend/engineering_core/
backend/vdi2230_core/
backend/calculation_engine/
backend/library/
```

**TR.** Kanıtlanmış bir engel bulunmadıkça aşağıdakilerde
değişikliğe izin verilmez. Bir engel bulunursa, faz durur ve korunan
bir dosyayı değiştirmek yerine bunu raporlar:

```text
backend/governance/adapters/joint_revision.py
backend/governance/store.py
backend/governance/service.py
backend/governance/events.py
backend/governance/transitions.py
backend/joints/
backend/engineering_core/
backend/vdi2230_core/
backend/calculation_engine/
backend/library/
```

## 11. Non-Goals / Kapsam Dışı

**EN.** Explicitly excluded from Phase 2.8.13:

- New write endpoints for joint revisions.
- New governance events or event types.
- New lifecycle transitions.
- New database tables.
- New persistence mechanisms.
- New synchronization services (no washer-resolution-style
  sync/reconciliation pattern for joint revisions).
- A governance projection registry (deferred per the approved Stage 1
  repository analysis — low value at current scale of two source
  mechanisms).
- A cross-mechanism consistency validator (deferred — premature with
  only one write-integrated mechanism in existence).
- Production Validation governance integration.
- Legacy calculation revision governance integration.
- Refactoring of any adapter beyond the one corrective fix to
  `backend/governance/adapters/__init__.py`'s stale docstring/`__all__`
  scheduled for the stage that adds the new route (not this Stage 1
  document).
- Expansion of `backend/governance/ownership.py`'s
  `RESTRICTED_AGGREGATE_TYPES` (joint revision has no write path, so
  nothing needs restricting).
- Unrelated cleanup of any kind.
- Speculative abstraction beyond what this phase's bounded scope
  requires.
- Normalization or invention of unsupported joint revision data —
  the route surfaces exactly what `project_joint_revision` already
  returns, nothing more.

**TR.** Faz 2.8.13'ten açıkça hariç tutulanlar:

- Joint revision'lar için yeni yazma uç noktaları.
- Yeni governance olayları veya olay türleri.
- Yeni yaşam döngüsü geçişleri.
- Yeni veritabanı tabloları.
- Yeni kalıcılaştırma mekanizmaları.
- Yeni senkronizasyon servisleri (joint revision'lar için washer-
  resolution tarzı senkronizasyon/uzlaştırma deseni yok).
- Bir governance projeksiyon kaydı (onaylanmış Stage 1 depo
  analizine göre ertelendi — iki kaynak mekanizmasının mevcut
  ölçeğinde düşük değer).
- Mekanizmalar-arası bir tutarlılık doğrulayıcısı (ertelendi — halen
  yalnızca bir yazma-entegre mekanizma varken erken).
- Production Validation governance entegrasyonu.
- Legacy calculation revision governance entegrasyonu.
- Yeni rotayı ekleyen aşama için planlanan (bu Stage 1 belgesi değil)
  `backend/governance/adapters/__init__.py`'nin eski
  docstring/`__all__` düzeltmesi dışında herhangi bir adaptörün
  yeniden düzenlenmesi.
- `backend/governance/ownership.py`'nin `RESTRICTED_AGGREGATE_TYPES`
  genişletilmesi (joint revision'ın yazma yolu yok, bu yüzden
  kısıtlanacak bir şey yok).
- Herhangi bir türde ilgisiz temizlik.
- Bu fazın sınırlı kapsamının gerektirdiğinin ötesinde spekülatif
  soyutlama.
- Desteklenmeyen joint revision verisinin normalleştirilmesi veya
  icat edilmesi — rota, `project_joint_revision`'ın zaten döndürdüğü
  şeyi tam olarak yüzeye çıkarır, daha fazlasını değil.

## 12. Stage Plan / Aşama Planı

**Stage 1 — Scope lock and integration contract**
- Objective: lock scope, document the approved API/frontend/error/test
  contracts based on the existing adapter's real signature and
  outcomes.
- Expected files: `docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`
  (this document) only.
- Protected files: all of Section 10, plus every other file not
  listed above — nothing else changes this stage.
- Tests: none (docs only).
- Acceptance criteria: document reviewed and approved; repository
  state otherwise unchanged (`git status --short` shows exactly one
  new file).
- Rollback boundary: revert/delete this one file.

**Stage 2 — Read-only API exposure**
- Objective: implement `GET /api/governance/joint-revision/{revision_id}`
  per Section 5; correct `backend/governance/adapters/__init__.py`'s
  stale docstring/`__all__` (Section 3's items 1 and 2 from the
  approved Stage 1 repository analysis) as part of the same stage,
  since it is the natural place to add `joint_revision` to that
  package's public exports.
- Expected files: `backend/governance/api.py`,
  `backend/governance/adapters/__init__.py`.
- Protected files: Section 10's full list, unchanged.
- Tests: items 1–7 of Section 8.
- Acceptance criteria: new route tests pass; full existing
  `tests/governance/` suite (233 baseline + new tests) passes; import-
  order safety re-verified under real request-path conditions, not
  just adapter-level isolation.
- Rollback boundary: revert the two-file diff.

**Stage 3 — Frontend workspace visibility**
- Objective: implement the additive frontend extension per Section 6.
- Expected files: `frontend/index.html`, `tests/js/` (extended
  harness).
- Protected files: Section 10's full list, unchanged; no other
  frontend page.
- Tests: items 8–10 of Section 8.
- Acceptance criteria: TR/EN parity test passes with zero gaps;
  relevant JS harness passes; new DOM elements confined to
  `page-governance`.
- Rollback boundary: revert the frontend/test diff.

**Stage 4 — Full regression and integrity verification**
- Objective: full-repository proof that nothing outside the expected-
  change list moved, and that every quality gate still passes.
- Expected files: none (verification only).
- Protected files: Section 10's full list — SHA256-compared against
  this phase's baseline (`cb20e69`) and confirmed identical.
- Tests: items 11–13 of Section 8 (full governance suite, full
  repository suite, full quality gate).
- Acceptance criteria: 100% pass on all three; SHA256 comparison
  clean for every protected file; `git diff --stat` matches exactly
  the files touched in Stages 2–3.
- Rollback boundary: n/a (verification stage — any failure here means
  returning to Stage 2 or 3, not proceeding to Stage 5).

**Stage 5 — Completion documentation and release bundle**
- Objective: phase completion report (mirroring the 2.8.12 report's
  structure), backlog/roadmap/changelog updates, and — per the
  standing delivery protocol — patch + bundle + SHA256SUMS produced
  and verified on an independent clean clone before declaring the
  phase complete.
- Expected files: `docs/phases/PHASE_2.8.13_COMPLETION_REPORT.md`,
  `docs/11_PRODUCT_BACKLOG.md`, `docs/314_Roadmap.md`,
  `docs/CHANGELOG.md`.
- Protected files: Section 10's full list, plus every code file not
  already touched in Stages 2–3.
- Tests: full suite re-run as final proof, plus the delivery
  protocol's clean-clone verification.
- Acceptance criteria: completion report accurately reflects the
  actual diff (no over- or under-claiming, matching this phase's own
  standard from the 2.8.12 report); patch/bundle/SHA256SUMS verified
  on a separate clean clone with tree-hash comparison and full test
  execution.
- Rollback boundary: revert the doc commits; the branch is not merged
  until this stage's verification is complete.

## 13. Türkçe Özet

Faz 2.8.13, mevcut ve zaten test edilmiş `joint_revision` salt-okunur
governance projeksiyonunu üretim ortamında görünür kılar: bir yeni
salt-okunur `GET /api/governance/joint-revision/{revision_id}` API
rotası ve mevcut genel governance frontend çalışma alanının küçük bir
genişlemesi üzerinden. Faz, yeni bir yazma yolu, yeni bir governance
olayı, yeni bir veritabanı tablosu veya yeni bir yaşam döngüsü
tanıtmaz; joint revision mühendislik mekanizması tam yetkili kalır.
Kapsam beş aşamaya bölünmüştür (kapsam kilidi → API → frontend →
regresyon → tamamlama), her biri kendi kabul kriterleri ve geri alma
sınırıyla. Bu belge yalnızca Stage 1'i temsil eder; kod veya test
değişikliği içermez.
