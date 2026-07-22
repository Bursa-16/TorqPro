# Faz 2.5A — Production Validation Foundation

> **Branch:** `feature/faz-2.5a-production-validation-foundation`
> **Base commit:** `2b8f3d7`
> **Related ADR:** `docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`

## 1. Kapsam

Üretim/doğrulama ölçüm verilerini proje, joint, joint revizyonu, hesaplama,
hesaplama revizyonu ve spesifikasyon ile ilişkilendiren, sürümlü ve
izlenebilir bir veri modeli. Bu fazda proses yetenek indeksleri (Cp/Cpk/
Pp/Ppk/Cmk), kontrol limitleri, normallik onayı ve otomatik üretim onayı
**uygulanmamıştır**.

Prerequisite olarak, `docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`
kararı gereği minimal bir Joint/JointRevision temel katmanı da bu fazda
teslim edilmiştir (ayrı commit grubunda).

## 2. Değişen / Eklenen Dosyalar

### Joint prerequisite
```
backend/joints/__init__.py
backend/joints/exceptions.py
backend/joints/schema.py
backend/joints/service.py
tests/test_joints_foundation.py
```

### Production validation domain
```
backend/production_validation/__init__.py
backend/production_validation/enums.py
backend/production_validation/exceptions.py
backend/production_validation/models.py
backend/production_validation/repository.py
backend/production_validation/schemas.py
backend/production_validation/service.py
backend/production_validation/validators.py
backend/api/__init__.py
backend/api/routes/__init__.py (dizin; ayrı dosya yok, mevcut paket yapısı)
backend/api/routes/production_validation.py
tests/production_validation/__init__.py
tests/production_validation/conftest.py
tests/production_validation/test_api.py
tests/production_validation/test_csv_import.py
tests/production_validation/test_models.py
tests/production_validation/test_repository.py
tests/production_validation/test_service.py
tests/production_validation/test_state_transitions.py
tests/production_validation/test_traceability.py
tests/production_validation/test_validators.py
```

### Güncellenen dosyalar
```
backend/app.py   — migrate() içine joints + production_validation şema
                   çağrıları eklendi; production_validation router'ı
                   statik dosya mount'undan önce include edildi.
docs/README.md
docs/CHANGELOG.md
docs/11_PRODUCT_BACKLOG.md
docs/06_DATABASE_SPECIFICATION.md
docs/07_API_SPECIFICATION.md
```

### Migration dosyaları

Bağımsız migration dosyası yok; mevcut mimari `backend/app.py::migrate()`
içinde idempotent `CREATE TABLE IF NOT EXISTS` yaklaşımını kullanıyor.
Faz 2.5A bu yaklaşımı korudu: `backend/joints/schema.py::migrate(c)` ve
`backend/production_validation/repository.py::migrate(c)` aynı sqlite3
`Connection` üzerinde, `app.py::migrate()` içinden çağrılıyor. Yeniden
çalıştırıldığında mevcut veriyi bozmaz (tüm `CREATE TABLE`/`CREATE INDEX`
ifadeleri `IF NOT EXISTS`).

## 3. Veri Modeli

### Joint prerequisite
- `joints(id, project_id, joint_code, name, description, status,
  current_revision_id, created_by, created_at, updated_at, archived_at)`
  — `UNIQUE(project_id, joint_code)`
- `joint_revisions(id, joint_id, revision_no, status, snapshot_json,
  change_summary, created_by, created_at, submitted_at, reviewed_by,
  reviewed_at, approved_at)` — `UNIQUE(joint_id, revision_no)`

### Production validation
- `validation_studies` — bkz. görev tanımı §4.1; `specification_id`
  başlangıçta boş, aynı transaction içinde oluşturulan snapshot'ın id'si
  ile güncellenir.
- `specification_snapshots` — `calculation_snapshot_id` doğrudan
  `calculation_revisions.id`'yi referanslar (ADR §7).
- `measurement_datasets`
- `measurement_records` — `correction_of_id` ile düzeltme geçmişi
  (ham değer sessizce değiştirilmez; eski kayıt invalid'lenir, yeni kayıt
  eklenir).
- `tool_references`

Tüm tablolar ve indexler: `backend/production_validation/repository.py::DDL`,
`backend/joints/schema.py::DDL`.

## 4. API

```
POST   /api/validation-studies
GET    /api/validation-studies
GET    /api/validation-studies/{study_id}
PATCH  /api/validation-studies/{study_id}
POST   /api/validation-studies/{study_id}/datasets
GET    /api/validation-studies/{study_id}/datasets
GET    /api/measurement-datasets/{dataset_id}
PATCH  /api/measurement-datasets/{dataset_id}
POST   /api/measurement-datasets/{dataset_id}/lock
POST   /api/measurement-datasets/{dataset_id}/records
POST   /api/measurement-datasets/{dataset_id}/records/bulk
GET    /api/measurement-datasets/{dataset_id}/records
POST   /api/measurement-records/{record_id}/invalidate
POST   /api/validation-studies/{study_id}/complete
POST   /api/validation-studies/{study_id}/submit
POST   /api/validation-studies/{study_id}/approve
POST   /api/validation-studies/{study_id}/reject
POST   /api/validation-studies/{study_id}/archive
```

Joint prerequisite için API endpoint'i yok (kasıtlı — görev talimatı
sadece "tablolar ve minimum servis katmanı" istedi; `backend/joints/service.py`
doğrudan Python servis katmanı olarak kullanılıyor).

## 5. State Machine

```
draft -> data_collection -> completed -> under_review -> approved
                                              |
                                              v
                                          rejected -> data_collection
(any non-terminal state) -> archived
```

`draft -> data_collection` geçişi ilk dataset oluşturulduğunda otomatik
tetiklenir. `approved` durumu terminal ve immutable'dır (patch, dataset
ekleme, tekrar submit/complete hepsi engellenir).

## 6. Güvenlik Kuralları

- Tüm veri bütünlüğü kuralları (`docs` görev tanımı §5, 16 madde) —
  `backend/production_validation/validators.py` + `service.py` + DB
  `UNIQUE`/`NOT NULL` constraint'leri.
- CSV import: zorunlu kolon kontrolü, NaN/Infinity reddi, satır bazlı hata
  raporu, **atomic all-or-nothing import** (bir satır bile hata verirse
  hiçbir kayıt yazılmaz — bkz. `service.py::import_csv_records`
  docstring'i), dosya SHA-256 checksum, aynı checksum'lı dosyanın tekrar
  import edilmesi engellenir, formula-injection prefix reddi (`=`, `+`,
  `-`, `@`), max 20.000 satır / 5 MB dosya boyutu, tool_code sadece
  mevcut `tool_references` tablosundan çözülür (arbitrary path/dosya
  erişimi yok).
- Approval role kontrolü: `admin`/`engineer` (mevcut `calculation_revisions`
  onay deseniyle aynı), kendi kendine onay engellenir.
- Approved study değiştirilemez; locked dataset'e kayıt eklenemez.

## 7. Test Sonucu

- Başlangıç (Faz 2.5A öncesi, temiz venv): **590 passed**
- Faz 2.5A sonrası tam regresyon: **663 passed** (yeni: 73 test — 9 joint
  prerequisite + 64 production_validation)
- Regresyon: mevcut 590 testin tamamı hâlâ geçiyor, hiçbiri değiştirilmedi.

## 8. Kapsam Dışı (Faz 2.5B/2.5C'ye bırakılan)

- Cp, Cpk, Pp, Ppk, Cmk
- Control limits / SPC
- Normallik onayı
- Otomatik üretim onayı / proses release kararı
- 4-sigma/6-sigma sınıflandırması
- Excel import
- Joint için: tam BOM, parça seçim ekranı, geometri editörü, calculation
  orchestration, tam approval workflow yeniden tasarımı (bkz. ADR §4)
