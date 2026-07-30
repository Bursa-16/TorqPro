# Phase 2.8.10 — Test Harness & Quality — Completion Report
# Faz 2.8.10 — Test Harness ve Kalite — Tamamlanma Raporu

**Branch:** `feature/faz-2.8.10-test-harness-quality`
**Commits:** `c1a6aa8`, `248a4a9`, `8294180` (on top of `d80046a`, the Faz 2.8.9 merge)
**Status:** Complete, all stages approved / Tamamlandı, tüm aşamalar onaylandı

---

## English

### 1. Objective and delivered scope

Phase 2.8.10 is a test-infrastructure and quality-tooling phase: it audits, consolidates, and strengthens TorqPro's test suite and adds one deterministic repository-level quality-gate command. It changes **no production calculation, API, or frontend behavior**. Four stages were delivered, each reviewed and approved before the next began:

- **Stage 1** — Quality audit (analysis only, no code changed)
- **Stage 2** — Shared, opt-in pytest fixtures (backend test setup)
- **Stage 3** — Shared JavaScript test-harness module + global TR/EN parity guard
- **Stage 4** — Repository quality-gate runner (`tools/run_quality_gate.py`)

### 2. Stage 1 — Quality-audit findings

Delivered as three analysis documents (`docs/phase_2_8/phase_2_8_10_stage1_*.md`, committed in `c1a6aa8`):

- **Quality Gap Report**: baseline was 1525/1525 pytest passing, 93% backend coverage (measured ad hoc; no coverage tool was part of the repo). Found: three modules below the project's own coverage norm (`backend/joints/service.py` 77%, `backend/app.py` 82%, `backend/production_validation/service.py` 85%); architectural (not logical) test duplication — 25 of ~85 test files hardcoded the admin login, 16 redefined a local `auth()` helper, and the 5 JS regression harnesses each independently re-implemented ~150–200 lines of identical DOM/extraction boilerplate; no repo-codified TR/EN parity gate (parity was 100% at the time but nothing enforced it); the delivery protocol's quality-gate steps (scoped flake8, `compileall`, determinism checks) existed only as manual practice, not as committed scripts or CI steps; no `pytest.ini` markers for the documented test pyramid.
- **Test Inventory**: full catalogue of all 81 Python test files + 5 JS harnesses, grouped by category, confirming no test was a stale duplicate safe to delete — the only duplication found was architectural boilerplate (Sec. 2.2 of the Gap Report), not test logic.
- **Recommended Test Architecture**: the proposal that Stages 2–4 subsequently implemented, in the exact sequence proposed (fixtures → parity test → markers *(deferred, see §12)* → coverage tooling *(deferred)* → shared JS module → targeted coverage additions *(deferred)*).

### 3. Stage 2 — Shared pytest fixtures

Committed in `c1a6aa8` (`tests/conftest.py`, `tests/test_shared_fixtures.py`). Added three opt-in, session-scoped fixtures — `client` (shared `TestClient`), `auth_headers` (default-admin bearer token, reused for the whole session since the token is valid 480 minutes), and `login_as` (factory for logging in as an arbitrary secondary user) — generalizing the boilerplate identified in Stage 1 §2.2. **Purely additive**: no existing test file, fixture, or helper was modified; all 1525 pre-existing tests kept passing unchanged. 7 new tests validate the fixtures themselves.

### 4. Stage 3 — Shared JS harness and global TR/EN parity guard

Committed in `248a4a9` (`tests/js/harness_common.js`, the four migrated harness files, `tests/test_i18n_key_parity.py`, and four Faz 2.8.6–2.8.9 wrapper-test allowlist updates).

- Extracted the genuinely byte-identical, stable DOM/extraction/assertion helpers (`extractScript`, `extractConstDecl`, `extractFunctionDecl`, `extractStatementAfter`, `toVarDecl`, `makeElement`, `makeLocalStorage`, `scrapeDataI18nKeys`, `buildDom`, and a `createChecker()` factory) into `tests/js/harness_common.js`, after verifying byte-for-byte identity across the source harnesses (hash-compared, not assumed).
- Migrated `run_assembly_intelligence_tests.js`, `run_joint_analysis_tests.js`, `run_material_intelligence_tests.js`, and `run_washer_resolution_report_tests.js` to use the shared module. Every migrated harness was verified to produce **byte-identical output** against its pre-migration baseline (diffed, not just "still passes").
- `run_i18n_tests.js` (the original, largest harness, 4174 lines) was **deliberately left unmigrated**: several of its equivalent internal helpers had already diverged from the newer four, so unifying them would have been a behavioral risk to a large, already-passing harness rather than a pure extraction.
- Added `tests/test_i18n_key_parity.py`: a **permanent, pure-Python, Node-independent** global TR/EN key-parity guard. It parses `frontend/index.html` directly (no Node subprocess at all, so it can never be silently skipped for a Node-provisioning reason — verified by a self-check that inspects the module's own runtime state for `subprocess` imports or pytest skip markers). It checks: identical EN/TR key sets, identical key counts, and per-language duplicate-key detection, with deterministic sorted-key failure messages.
- This test **found two genuine pre-existing duplicate keys** already in `frontend/index.html` (see §8 below) — not introduced by this phase. Fixing them would be a frontend content change, out of scope for a test-infrastructure phase; they are recorded as an explicit, reviewed baseline so the test still catches any *new* duplicate without masking these two or requiring an out-of-scope production edit.
- Fixed a real regression the migration surfaced: the four existing Faz 2.8.6–2.8.9 Python wrapper tests' `test_harness_file_is_dependency_free` check didn't know about the new legitimate `require('./harness_common')` local import; each got a one-line allowlist addition (not a logic change) so they keep correctly distinguishing real external dependencies (jsdom, puppeteer, playwright) from the intentional in-repo shared module.

### 5. Stage 4 — Repository quality-gate runner

Committed in `8294180` (`tools/run_quality_gate.py`, `tests/test_run_quality_gate.py`, `docs/14_TESTING_STRATEGY.md` §9).

One deterministic command, `python tools/run_quality_gate.py`, standard-library only plus the project's own existing tools (`git`, `node`, `compileall`, `pytest` — no new dependency), running six checks in a fixed order and stopping at the first failure with full underlying output preserved:

1. `git diff --check`
2. Python compile validation (`backend/`, `tests/`)
3. JSON validity for repository-owned `*.json` files (`.git`, virtualenvs, caches, `node_modules`, `runtime/`, build/dist output, and vendor directories excluded; sorted, deterministic order)
4. TR/EN key parity (`tests/test_i18n_key_parity.py`)
5. All 5 JavaScript regression harnesses — **Node absence is an explicit failure with an actionable message, never a silent skip**
6. Full `pytest -q` suite

21 focused, hermetic tests cover ordering, short-circuit behavior (at both the gate and JS-harness level), exit-code propagation, missing-Node failure, JSON validation correctness/exclusions/ordering. Deliberately does not run full-tree `flake8` (Stage 1 found ~2175 pre-existing style-debt findings unrelated to correctness) or enforce a coverage threshold.

### 6. Final test count

**1559 / 1559 pytest tests passing** (1525 baseline + 7 Stage 2 + 6 Stage 3 + 21 Stage 4). All 5 JavaScript harnesses pass (i18n 1097, assembly 44, joint 45, material 28, washer 32 assertions — all 0 failed).

### 7. Clean-clone verification result

An independent fresh clone was created, `feature/faz-2.8.10-test-harness-quality` checked out, dependencies installed with **only** `pip install -r requirements.txt -r requirements-dev.txt` (no `pytest-cov`, no `flake8`, no undeclared package), and `python tools/run_quality_gate.py` run. **Result: PASS, all 6 gates, 1559/1559 tests, exit code 0** — with no manual setup beyond the declared requirements and an existing Node installation.

### 8. Known pre-existing translation duplicates

Two duplicate translation keys, found by the new Stage 3 parity test, already existed in `frontend/index.html` in both the `en` and `tr` blocks:

- `hizli.enter_parameters`
- `yetenek.oem_tmin_tmax`

**These duplicates were not introduced by Phase 2.8.10.** A duplicate key in a JS object literal is harmless at runtime (the later declaration silently wins), but is real, pre-existing content debt. Fixing it requires a frontend content edit, which is out of scope for this test-infrastructure phase; it is recorded here and enforced as an explicit, reviewed baseline in `tests/test_i18n_key_parity.py` so the parity guard still catches any *new* duplicate.

### 9. Production-code impact

**None.** No file under `backend/` or `frontend/` was modified in any of the four stages. Confirmed by diff review at the end of every stage.

### 10. Dependency impact

**None.** No `requirements.txt`, `requirements-dev.txt`, or package file was modified. `pytest-cov` and `flake8`, installed transiently during Stage 1's manual analysis, were explicitly uninstalled before Stage 2 began and never added to any requirements file. Stage 4's quality-gate runner uses only the Python standard library and the project's pre-existing tools.

### 11. Backward-compatibility statement

Every one of the 1525 pre-existing tests still passes, unmodified, with unmodified assertions. The 4 migrated JS harnesses produce byte-identical output to their pre-migration baselines (diff-verified, not just re-passed). No existing fixture, helper, or test file was deleted, renamed, or had its behavior changed — all Stage 2–4 additions are purely additive or (for the 4 wrapper-test allowlist edits in Stage 3) a one-line, behavior-preserving correction required by the migration itself.

### 12. Remaining recommendations (future work, not blockers)

None of the following block release of this phase; they are carried forward for a future phase to pick up if desired:

- Fix the two known pre-existing duplicate translation keys (§8) — a frontend content change.
- Close the three lowest-coverage backend modules identified in Stage 1 (`joints/service.py`, `app.py`, `production_validation/service.py`).
- Add `pytest.ini` markers matching the documented test pyramid (Stage 1 Recommended Architecture §2.6) — proposed but not implemented, since it requires no behavior change but was judged out of Stage 2–4's minimal-footprint scope.
- Migrate `run_i18n_tests.js` to the shared `harness_common.js` module, if and when it is next touched for an unrelated reason (deliberately not forced in Stage 3 — see §4).
- Wire `pytest-cov` into CI for ongoing coverage visibility (Stage 1 Recommended Architecture §2.4) — deliberately deferred to avoid adding a dependency in a test-infrastructure phase whose own constraint was "no new dependencies."

### 13. Release-readiness conclusion

Phase 2.8.10 is **release-ready**. All four stages are complete, reviewed, and committed; the full suite passes both in the working repository and in an independent clean clone using only declared dependencies; no production code, dependency, or translation content was changed; the two pre-existing translation-key duplicates are documented, non-blocking, and explicitly not introduced by this phase.

---

## Türkçe

### 1. Amaç ve teslim edilen kapsam

Faz 2.8.10, bir test altyapısı ve kalite araçları fazıdır: TorqPro'nun test paketini denetler, birleştirir ve güçlendirir; ayrıca depo düzeyinde tek bir deterministik kalite kapısı komutu ekler. **Hiçbir üretim hesaplama, API veya ön yüz davranışını değiştirmez.** Her biri bir sonrakine geçilmeden önce incelenip onaylanan dört aşama teslim edilmiştir:

- **Aşama 1** — Kalite denetimi (yalnızca analiz, kod değişikliği yok)
- **Aşama 2** — Paylaşılan, isteğe bağlı pytest fixture'ları (backend test kurulumu)
- **Aşama 3** — Paylaşılan JavaScript test harness modülü + küresel TR/EN eşlik (parity) koruması
- **Aşama 4** — Depo kalite kapısı çalıştırıcısı (`tools/run_quality_gate.py`)

### 2. Aşama 1 — Kalite denetimi bulguları

Üç analiz belgesi olarak teslim edildi (`docs/phase_2_8/phase_2_8_10_stage1_*.md`, `c1a6aa8` işlemine dahil):

- **Kalite Açığı Raporu**: başlangıç durumu 1525/1525 pytest testi geçiyor, %93 backend kapsamı (geçici olarak ölçüldü; depoda kapsam aracı yoktu). Bulgular: projenin kendi normunun altında üç modül (`backend/joints/service.py` %77, `backend/app.py` %82, `backend/production_validation/service.py` %85); mantıksal değil mimari test tekrarı — ~85 test dosyasının 25'i admin girişini sabit kodlamış, 16'sı yerel bir `auth()` yardımcı fonksiyonunu yeniden tanımlamış, 5 JS regresyon harness'i her biri bağımsız olarak ~150-200 satırlık aynı DOM/çıkarma standart kodunu yeniden uygulamış; depoya kodlanmış bir TR/EN eşlik kapısı yok (o sırada eşlik %100'dü ama hiçbir şey bunu zorunlu kılmıyordu); teslimat protokolünün kalite kapısı adımları (kapsamlı flake8, `compileall`, determinizm kontrolleri) yalnızca manuel uygulama olarak vardı, kayıtlı bir betik veya CI adımı olarak değil; belgelenen test piramidi için `pytest.ini` işaretleyicileri yok.
- **Test Envanteri**: 81 Python test dosyasının + 5 JS harness'inin tamamının kategoriye göre gruplanmış tam kataloğu; hiçbir testin silinmeye uygun bayat bir tekrar olmadığını doğruladı — bulunan tek tekrar mimari standart koddu (Açık Raporu Böl. 2.2), test mantığı değil.
- **Önerilen Test Mimarisi**: Aşama 2-4'ün önerilen tam sırayla (fixture'lar → eşlik testi → işaretleyiciler *(ertelendi, bkz. §12)* → kapsam araçları *(ertelendi)* → paylaşılan JS modülü → hedefli kapsam eklemeleri *(ertelendi)*) uyguladığı öneri.

### 3. Aşama 2 — Paylaşılan pytest fixture'ları

`c1a6aa8` işlemine dahil (`tests/conftest.py`, `tests/test_shared_fixtures.py`). Aşama 1 §2.2'de tespit edilen standart kodu genelleştiren üç isteğe bağlı, oturum kapsamlı fixture eklendi — `client` (paylaşılan `TestClient`), `auth_headers` (varsayılan admin bearer token'ı, token 480 dakika geçerli olduğundan tüm oturum boyunca yeniden kullanılır) ve `login_as` (rastgele bir ikincil kullanıcı olarak giriş yapmak için fabrika). **Tamamen eklemeli**: mevcut hiçbir test dosyası, fixture veya yardımcı fonksiyon değiştirilmedi; önceden var olan 1525 test değişmeden geçmeye devam etti. Fixture'ların kendisini doğrulayan 7 yeni test eklendi.

### 4. Aşama 3 — Paylaşılan JS harness ve küresel TR/EN eşlik koruması

`248a4a9` işlemine dahil (`tests/js/harness_common.js`, dört taşınan harness dosyası, `tests/test_i18n_key_parity.py`, ve dört Faz 2.8.6–2.8.9 wrapper-test izin listesi güncellemesi).

- Gerçekten bayt-bayt aynı, kararlı DOM/çıkarma/doğrulama yardımcı fonksiyonları (`extractScript`, `extractConstDecl`, `extractFunctionDecl`, `extractStatementAfter`, `toVarDecl`, `makeElement`, `makeLocalStorage`, `scrapeDataI18nKeys`, `buildDom`, ve bir `createChecker()` fabrikası) kaynak harness'ler arasında bayt-bayt özdeşlik doğrulandıktan sonra (varsayılmadan, hash karşılaştırmasıyla) `tests/js/harness_common.js` içine çıkarıldı.
- `run_assembly_intelligence_tests.js`, `run_joint_analysis_tests.js`, `run_material_intelligence_tests.js` ve `run_washer_resolution_report_tests.js` paylaşılan modülü kullanacak şekilde taşındı. Taşınan her harness'in taşıma öncesi referansına göre **bayt-bayt aynı çıktı** ürettiği doğrulandı (yalnızca "hâlâ geçiyor" değil, fark alınarak).
- `run_i18n_tests.js` (orijinal, en büyük harness, 4174 satır) **kasıtlı olarak taşınmadı**: eşdeğer iç yardımcı fonksiyonlarının birçoğu daha yeni dörtten zaten ayrışmıştı, bu yüzden bunları birleştirmek saf bir çıkarma değil, büyük ve zaten geçen bir harness için davranışsal bir risk olurdu.
- `tests/test_i18n_key_parity.py` eklendi: **kalıcı, saf Python, Node'dan bağımsız** küresel TR/EN anahtar eşlik koruması. `frontend/index.html` dosyasını doğrudan ayrıştırır (hiç Node alt süreci yoktur, bu yüzden Node kurulumu nedeniyle asla sessizce atlanamaz — modülün kendi çalışma zamanı durumunu `subprocess` içe aktarımları veya pytest atlama işaretleyicileri için inceleyen bir öz-kontrolle doğrulanmıştır). Şunları kontrol eder: özdeş EN/TR anahtar kümeleri, özdeş anahtar sayıları, ve dil başına yinelenen anahtar tespiti, deterministik sıralı-anahtar hata mesajlarıyla.
- Bu test `frontend/index.html` içinde zaten var olan **iki gerçek, önceden var olan yinelenen anahtar buldu** (bkz. aşağıda §8) — bu faz tarafından eklenmedi. Bunları düzeltmek bir ön yüz içerik değişikliği olurdu, bir test-altyapısı fazının kapsamı dışında; bu yüzden test hâlâ herhangi bir *yeni* yinelenmeyi yakalayabilsin, bu ikisini maskelemesin veya kapsam dışı bir üretim düzenlemesi gerektirmesin diye açık, incelenmiş bir taban çizgisi olarak kaydedildi.
- Taşımanın ortaya çıkardığı gerçek bir regresyon düzeltildi: mevcut dört Faz 2.8.6–2.8.9 Python wrapper testinin `test_harness_file_is_dependency_free` kontrolü, yeni meşru `require('./harness_common')` yerel içe aktarımından haberdar değildi; her birine (mantık değişikliği değil) tek satırlık bir izin listesi eklemesi yapıldı, böylece gerçek harici bağımlılıkları (jsdom, puppeteer, playwright) kasıtlı depo-içi paylaşılan modülden doğru şekilde ayırt etmeye devam ediyorlar.

### 5. Aşama 4 — Depo kalite kapısı çalıştırıcısı

`8294180` işlemine dahil (`tools/run_quality_gate.py`, `tests/test_run_quality_gate.py`, `docs/14_TESTING_STRATEGY.md` §9).

Tek bir deterministik komut, `python tools/run_quality_gate.py`, yalnızca standart kütüphane artı projenin mevcut araçları (`git`, `node`, `compileall`, `pytest` — yeni bağımlılık yok), sabit bir sırada altı kontrol çalıştırır ve ilk hatada durur, altta yatan çıktının tamamı korunur:

1. `git diff --check`
2. Python derleme doğrulaması (`backend/`, `tests/`)
3. Depoya ait `*.json` dosyaları için JSON geçerliliği (`.git`, sanal ortamlar, önbellekler, `node_modules`, `runtime/`, build/dist çıktısı ve vendor dizinleri hariç; sıralı, deterministik sıra)
4. TR/EN anahtar eşliği (`tests/test_i18n_key_parity.py`)
5. 5 JavaScript regresyon harness'inin tamamı — **Node eksikliği, sessiz bir atlama değil, eyleme geçirilebilir bir mesajla açık bir hatadır**
6. Tam `pytest -q` paketi

21 odaklı, hermetik test; sıralamayı, kısa devre davranışını (hem kapı hem JS-harness seviyesinde), çıkış kodu yayılımını, Node eksikliği hatasını, JSON doğrulama doğruluğunu/hariç tutmalarını/sıralamasını kapsar. Kasıtlı olarak tüm ağaç `flake8` çalıştırılmaz (Aşama 1, doğrulukla ilgisiz ~2175 önceden var olan stil borcu bulgusu tespit etmişti) veya bir kapsam eşiği zorunlu kılınmaz.

### 6. Nihai test sayısı

**1559 / 1559 pytest testi geçiyor** (1525 taban + 7 Aşama 2 + 6 Aşama 3 + 21 Aşama 4). 5 JavaScript harness'inin tamamı geçiyor (i18n 1097, assembly 44, joint 45, material 28, washer 32 doğrulama — hepsi 0 başarısız).

### 7. Temiz klon doğrulama sonucu

Bağımsız, taze bir klon oluşturuldu, `feature/faz-2.8.10-test-harness-quality` çekildi, bağımlılıklar **yalnızca** `pip install -r requirements.txt -r requirements-dev.txt` ile kuruldu (pytest-cov yok, flake8 yok, beyan edilmemiş paket yok), ve `python tools/run_quality_gate.py` çalıştırıldı. **Sonuç: BAŞARILI, 6 kapının tamamı, 1559/1559 test, çıkış kodu 0** — beyan edilen bağımlılıklar ve mevcut bir Node kurulumu dışında manuel kurulum gerekmedi.

### 8. Bilinen önceden var olan çeviri tekrarları

Yeni Aşama 3 eşlik testi tarafından bulunan iki yinelenen çeviri anahtarı, `frontend/index.html` içinde hem `en` hem `tr` bloklarında zaten mevcuttu:

- `hizli.enter_parameters`
- `yetenek.oem_tmin_tmax`

**Bu tekrarlar Faz 2.8.10 tarafından eklenmemiştir.** Bir JS nesne değişmezinde yinelenen bir anahtar çalışma zamanında zararsızdır (sonraki bildirim sessizce kazanır), ancak gerçek, önceden var olan içerik borcudur. Düzeltilmesi bir ön yüz içerik düzenlemesi gerektirir, bu da bir test-altyapısı fazının kapsamı dışındadır; burada kaydedilmiş ve `tests/test_i18n_key_parity.py` içinde açık, incelenmiş bir taban çizgisi olarak uygulanmıştır, böylece eşlik koruması hâlâ herhangi bir *yeni* tekrarı yakalar.

### 9. Üretim kodu etkisi

**Yok.** Dört aşamanın hiçbirinde `backend/` veya `frontend/` altındaki hiçbir dosya değiştirilmedi. Her aşamanın sonunda fark incelemesiyle doğrulandı.

### 10. Bağımlılık etkisi

**Yok.** Hiçbir `requirements.txt`, `requirements-dev.txt` veya paket dosyası değiştirilmedi. Aşama 1'in manuel analizi sırasında geçici olarak kurulan `pytest-cov` ve `flake8`, Aşama 2 başlamadan önce açıkça kaldırıldı ve hiçbir zaman bir gereksinim dosyasına eklenmedi. Aşama 4'ün kalite kapısı çalıştırıcısı yalnızca Python standart kütüphanesini ve projenin önceden var olan araçlarını kullanır.

### 11. Geriye dönük uyumluluk beyanı

Önceden var olan 1525 testin her biri, değiştirilmeden, değiştirilmemiş doğrulamalarla geçmeye devam ediyor. Taşınan 4 JS harness'i, taşıma öncesi referanslarıyla bayt-bayt aynı çıktı üretiyor (yalnızca yeniden geçmekle kalmayıp fark alınarak doğrulandı). Mevcut hiçbir fixture, yardımcı fonksiyon veya test dosyası silinmedi, yeniden adlandırılmadı veya davranışı değiştirilmedi — Aşama 2-4'teki tüm eklemeler ya tamamen eklemeli ya da (Aşama 3'teki 4 wrapper-test izin listesi düzenlemesi için) taşımanın kendisinin gerektirdiği, davranışı koruyan tek satırlık bir düzeltmedir.

### 12. Kalan öneriler (gelecek iş, engelleyici değil)

Aşağıdakilerin hiçbiri bu fazın yayınlanmasını engellemez; istenirse gelecekteki bir fazın üstlenmesi için taşınmıştır:

- Bilinen iki önceden var olan yinelenen çeviri anahtarını düzeltmek (§8) — bir ön yüz içerik değişikliği.
- Aşama 1'de tespit edilen en düşük kapsamlı üç backend modülünü kapatmak (`joints/service.py`, `app.py`, `production_validation/service.py`).
- Belgelenen test piramidiyle eşleşen `pytest.ini` işaretleyicileri eklemek (Aşama 1 Önerilen Mimari §2.6) — önerildi ama uygulanmadı, çünkü davranış değişikliği gerektirmese de Aşama 2-4'ün minimal ayak izi kapsamının dışında değerlendirildi.
- `run_i18n_tests.js`'i, ilgisiz bir nedenle bir dahaki sefere dokunulduğunda paylaşılan `harness_common.js` modülüne taşımak (Aşama 3'te kasıtlı olarak zorlanmadı — bkz. §4).
- Sürekli kapsam görünürlüğü için `pytest-cov`'u CI'a bağlamak (Aşama 1 Önerilen Mimari §2.4) — kendi kısıtlaması "yeni bağımlılık yok" olan bir test-altyapısı fazında bağımlılık eklemekten kaçınmak için kasıtlı olarak ertelendi.

### 13. Yayına hazırlık sonucu

Faz 2.8.10 **yayına hazırdır**. Dört aşamanın tamamı tamamlandı, incelendi ve işlendi; tam paket hem çalışma deposunda hem de yalnızca beyan edilen bağımlılıkları kullanan bağımsız bir temiz klonda geçiyor; hiçbir üretim kodu, bağımlılık veya çeviri içeriği değiştirilmedi; iki önceden var olan çeviri anahtarı tekrarı belgelenmiştir, engelleyici değildir ve bu faz tarafından eklenmediği açıkça belirtilmiştir.
