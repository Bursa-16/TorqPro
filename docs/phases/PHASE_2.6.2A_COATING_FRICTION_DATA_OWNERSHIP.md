# Faz 2.6.2A — Coating and Friction Data Ownership Decision

- **Status:** Delivered
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç

## 1. Amaç ve kapsam

**Amaç:** coating, lubrication ve friction-condition verilerinin hangi domain nesnesinde tutulacağını netleştirmek — bir mimari karar ve şema tasarımı fazı.

**Kapsam:**
- Mimari karar (ADR-0010) ve şema iskeleti (yalnızca non-breaking, additive Pydantic model tanımları).
- `docs/09_LIBRARY_SPECIFICATION.md`, `docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`, `docs/11_PRODUCT_BACKLOG.md` güncellemeleri.
- Bu faz dokümanı, migration planı, JSON örnekleri, kaynak matrisi, Faz 2.6.2B kabul kriterleri.

**Kapsam dışı (bu fazda yapılmadı):** öneri motoru, tork düzeltme motoru, torque decomposition, UI, PDF raporu, veri popülasyonu (19 yeni kayıt üretimi), Tablo 9.4 kayıtlarının migration'ı.

## 2. Mevcut durum

- `CoatingRecord` (`backend/library/models.py`, `coating_library.py`) zaten mevcuttu ve **10 gerçek kayıt** taşıyor (`coating_library.json`).
- `LubricationRecord` zaten mevcuttu ve **23 gerçek kayıt** taşıyor (8 Faz 2.4.x + 15 Tablo 9.4, ADR-0009/Faz 2.6.0).
- Faz 2.6 orijinal isteğinde "lubricant" olarak sayılan bazı kalemler (Geomet, Dacromet, zinc flake, phosphate) **aslında coating** — ve bunlar `coating_library.json`'da zaten var: `COAT-GEOMET`, `COAT-DACROMET`, `COAT-DELTA_PROTEKT`, `COAT-PHOSPHATE`.
- Sürtünme değerleri şu ana kadar ya `CoatingRecord.friction_coefficient_range` (serbest metin, tek değer) ya da `LubricationRecord`'un Faz 2.6.0/2.6.1 alanlarında (kombinasyona özgü, ör. Tablo 9.4 kayıtları) tutuluyordu — hiçbiri kombinasyon-bağımlılığını temiz şekilde modellemiyor.

## 3. Seçeneklerin karşılaştırılması

| Seçenek | Açıklama | Karar |
|---|---|---|
| A | Tüm veri `LubricationRecord` içinde | Reddedildi — coating kimliğini lubricant ile karıştırır, mevcut sorunun kaynağı |
| B | Ayrı `CoatingRecord` yeterli | Reddedildi (tek başına) — coating kimliği zaten var ama kombinasyon-bağımlı sürtünmeyi çözmez |
| C | Tek `FrictionConditionRecord`, coating+lubricant+condition hepsi birden, mevcut 2 modeli değiştirir | Reddedildi — çalışan 10+23 kaydı gereksiz yere atar |
| **D** | **Hibrit: CoatingRecord + LubricationRecord kimlik verisini korur; yeni FrictionConditionRecord kombinasyon-bağımlı sürtünmeyi taşır** | **Seçildi** |

Tam gerekçe için bkz. `docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md`.

## 4. Seçilen Option D hibrit mimari — özet karar

Sürtünme katsayıları, coating veya lubricant nesnesinin doğal/değişmez bir özelliği olarak kabul edilmez. Aynı coating farklı lubricant, yüzey, bağlantı ve test koşullarında farklı sürtünme sonucu verebilir (Tablo 9.4 bunun kanıtı: aynı yüzey durumu, sadece yağlama durumuna göre ~3 kat fark). Bu nedenle doğrulanmış `μ_thread`, `μ_bearing`, `K`, scatter ve overall friction verileri **gelecekte `FrictionConditionRecord` içinde** tutulacak.

## 5. Domain sorumlulukları / Veri sahipliği tablosu

| Concern | Owner | Live records (2026-07-23) |
|---|---|---|
| Coating kimliği (ad, aile, substrate, korozyon, sıcaklık, regülasyon) | `CoatingRecord` | 10 |
| Lubricant kimliği (ad/tip, aile, uygulama, sıcaklık, reusability) | `LubricationRecord` | 23 (8 Faz 2.4.x + 15 Tablo 9.4) |
| Kombinasyon-bağımlı sürtünme davranışı (overall/split katsayı, K, scatter) | `FrictionConditionRecord` | 0 (şema/karar fazı) |

## 6. Model alanları

### `CoatingRecord` — Faz 2.6.2A eklentileri (additive, boş varsayılan, 10 kayıt etkilenmedi)
`coating_family`, `substrate_applicability`, `regulatory_warning`, `source_reference`, `source_type`, `source_page_or_table`, `verification_status`, `applicability`, `engineering_notes`.

### `LubricationRecord` — Faz 2.6.2A eklentisi
`lubricant_family` (additive, boş varsayılan, 23 kayıt etkilenmedi).

### `FrictionConditionRecord` (yeni) — alan grupları (kavram tekrarı yok, bkz. ADR-0010 §"Field responsibilities")

| Grup | Alanlar |
|---|---|
| Referans | `coating_id`, `lubricant_id` |
| Montaj/yüzey koşulu | `surface_condition`, `thread_condition`, `bearing_condition` |
| Sürtünme modeli | `friction_model` (`FrictionModelType`, `LubricationRecord` ile paylaşılan enum) |
| Mühendislik değerleri | `overall_friction_coefficient_min/max`, `mu_thread_min/max`, `mu_bearing_min/max`, `k_factor_min/max`, `scatter_percent`, `max_temperature_c` |
| Uygulanabilirlik | `applicability` |
| Kaynak izlenebilirliği | `source_reference`, `source_type`, `source_page_or_table`, `verification_status`, `engineering_notes` |

Artı `LibraryRecordBase`'den miras alınan ortak alanlar (`id`, `notes`, `status`, vb.).

## 7. Registry/population/search entegrasyonu

- `LIBRARY_RECORD_MODELS["friction condition library"] = FrictionConditionRecord`
- `population.POPULATION_SOURCES["friction condition library"] = "friction_condition_library.json"`
- `search.CATEGORY_LIBRARY_MAP["friction_condition"]` / `["friction condition"]` → `"friction condition library"`
- `backend/library/__init__.py`: `friction_condition_library` modülü içe aktarılıp paket seviyesinde yeniden export edildi
- `validator.validate_friction_condition_library()`: Faz 2.6.1'in friction-check fonksiyonlarını (`find_friction_min_max_violations` vb.) yeniden kullanıyor — `FrictionConditionRecord` ile `LubricationRecord` aynı alan adlarını paylaştığı için kontrol mantığı tekrarlanmadı
- `population.run_all_integrity_checks()` → yeni anahtar: `"friction_condition_library_faz2_6_2a"`

## 8. JSON örnekleri

**Not:** Aşağıdaki örnekler yalnızca yapıyı gösterir. Kaynaksız hiçbir mühendislik değeri (μ_thread, μ_bearing, K, scatter, sıcaklık) verilmemiştir — sayısal alanlar `null` bırakılmıştır.

### 8.1 `FrictionConditionRecord` — yapısal alanlar dolu, mühendislik değerleri kaynaksız olduğu için `null`

```json
{
  "id": "FC-EXAMPLE-STRUCTURE-ONLY",
  "coating_id": "COAT-GEOMET",
  "lubricant_id": "LUBE-MOS2",
  "surface_condition": "",
  "thread_condition": "",
  "bearing_condition": "",
  "friction_model": "combined_or_unspecified",
  "overall_friction_coefficient_min": null,
  "overall_friction_coefficient_max": null,
  "mu_thread_min": null,
  "mu_thread_max": null,
  "mu_bearing_min": null,
  "mu_bearing_max": null,
  "k_factor_min": null,
  "k_factor_max": null,
  "scatter_percent": null,
  "max_temperature_c": null,
  "applicability": "",
  "source_reference": "",
  "source_type": "",
  "source_page_or_table": "",
  "verification_status": "",
  "engineering_notes": "Faz 2.6.2A yapı ornegi -- gercek muhendislik degeri icermez; Faz 2.6.2B'de kaynak onaylanmadan doldurulmayacak."
}
```

### 8.2 Mevcut `CoatingRecord` (gerçek, `coating_library.json`'dan — değişmedi, referans amaçlı)

```json
{
  "id": "COAT-GEOMET",
  "designation": "Geomet",
  "coating_type": "Zinc flake, non-electrolytic (Geomet 321/500)",
  "friction_coefficient_range": "..."
}
```

(Gerçek dosyadaki tam alan listesi için `backend/library/data/coating_library.json` bakınız — burada yalnızca kimlik alanları gösterilmiştir, sayısal değer bu belgede tekrarlanmamıştır.)

### 8.3 `friction_condition_library.json` — mevcut hali (tamamı)

```json
{
  "metadata": {
    "name": "Friction Condition Library",
    "version": "2.6.2a",
    "description": "...",
    "generated": "2026-07-23",
    "primary_source": ""
  },
  "records": []
}
```

## 9. Geriye dönük uyumluluk

- 10 `CoatingRecord` ve 23 `LubricationRecord` kaydının tamamı değişmeden doğrulanıyor (`test_all_ten_coating_records_unaffected`, `test_all_twenty_three_lubrication_records_still_unaffected`).
- Hiçbir alan yeniden adlandırılmadı, silinmedi veya tipi değiştirilmedi.
- Hiçbir route/API şeması dokunulmadı.
- `CoatingRecord.friction_coefficient_range` (mevcut, serbest metin) olduğu gibi bırakıldı — bu ADR ile yeniden yorumlanmadı, taşınmadı, deprecate edilmedi.

## 10. Migration planı

Faz 2.6.2A veri taşımaz. Kurallar (tam detay ADR-0010 §"Migration plan"):

1. Mevcut 23 `LubricationRecord` kaydı şimdilik korunacak, değiştirilmeyecek.
2. Mevcut 15 Tablo 9.4 kaydı hemen taşınmayacak; `combined_or_unspecified` referans verisi olarak `LubricationRecord` üzerinde kalacak.
3. Gelecekteki migration idempotent ve doğrulanabilir olacak (mevcut `MigrationEngine` konvansiyonuyla uyumlu).
4. Eski kimlikler (`LUBE-SURF-*`) kaybolmayacak — en az belgelenmiş bir geçiş penceresi boyunca çözümlenebilir kalacak.
5. Kaynak izlenebilirliği (source_reference, source_type, source_page_or_table, verification_status, applicability, engineering_notes) taşıma sırasında birebir kopyalanacak, yeniden üretilmeyecek.
6. API ve kullanıcı kayıtları kırılmayacak — migration fazı, hiçbir canlı endpoint'in `LubricationRecord`'un sürtünme alanlarını kullanmadığı varsayımını taşımadan önce yeniden doğrulamalı.
7. Migration doğrulanabilir olacak: eski/yeni kayıt arasında sayısal ve kaynak alanlarının birebir eşleştiğini kanıtlayan bir kontrol (find_checksum_mismatches benzeri) taşınacak.
8. Migration yalnızca ayrı, onaylı bir fazda (Faz 2.6.2C veya sonrası) yapılacak.

### 15 Tablo 9.4 kaydının gelecekte nasıl taşınacağı

Her `LUBE-SURF-<SURFACE>-<STATE>` kaydı → yeni bir `FrictionConditionRecord`:
- `coating_id` = (varsa) ilgili `CoatingRecord.id` — ör. galvanize kayıtları için coating domain'inde karşılık aranacak; bugün otomatik bir eşleme yok, bu da migration fazının kendi kararı olacak.
- `lubricant_id` = "" (Tablo 9.4 kayıtları belirli bir ticari lubricant ürününü değil, genel bir durumu — "Kuru"/"Yağlı"/"MoS2 ile Yağlı" — tanımlıyor; `lubricant_type` enum değeri `FrictionConditionRecord`'da bugün ayrı bir alan olarak yok, bu migration fazında kararlaştırılacak açık bir noktadır).
- `surface_condition` = eski kaydın `surface_condition` değeri, birebir.
- `overall_friction_coefficient_min/max`, `friction_model`, tüm source-traceability alanları birebir kopyalanacak.
- Eski `LUBE-SURF-*` kaydı migration sonrası silinmez (kural 4).

## 11. Dosya bazlı uygulama planı (bu fazda yapılanlar)

| Dosya | Değişiklik |
|---|---|
| `backend/library/models.py` | `FrictionConditionRecord` (yeni), `CoatingRecord`/`LubricationRecord` additive alanlar, `LIBRARY_RECORD_MODELS`, `__all__` |
| `backend/library/friction_condition_library.py` | Yeni — registry shell |
| `backend/library/data/friction_condition_library.json` | Yeni — boş (`"records": []`) |
| `backend/library/__init__.py` | Yeni modül import/export |
| `backend/library/population.py` | `POPULATION_SOURCES`, `validate_friction_condition_library_records()`, `run_all_integrity_checks()`, `__all__` |
| `backend/library/validator.py` | `validate_friction_condition_library()` |
| `backend/library/search.py` | `CATEGORY_LIBRARY_MAP` girişleri |
| `tests/test_faz2_6_2a_coating_friction_data_ownership.py` | Yeni — 17 test |
| `tests/test_faz2_4_1c_joint_hardware_infrastructure.py`, `tests/test_library_models.py`, `tests/test_loader.py`, `tests/test_population.py` | Domain sayısı/empty-by-design güncellemeleri |
| `docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md` | Yeni |
| `docs/09_LIBRARY_SPECIFICATION.md`, `docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`, `docs/11_PRODUCT_BACKLOG.md` | Güncellendi |
| `docs/phases/PHASE_2.6.2A_COATING_FRICTION_DATA_OWNERSHIP.md` | Bu belge |

## 12. Riskler

- İki kayıt tipi (`LubricationRecord`, `FrictionConditionRecord`) geçici olarak örtüşen şekilli sürtünme alanları taşıyor; gelecekte biri yanlışlıkla `LubricationRecord`'a yeni veri girebilir. Azaltma: ADR-0010 ve bu belge açıkça "yeni değerler `FrictionConditionRecord`'a" diyor; Faz 2.6.2B kabul kriterleri bunu zorunlu kılıyor.
- `coating_id`/`lubricant_id` serbest metin, doğrulanmamış referanslar — yazım hatası sessizce çözümlenmez. Azaltma: Faz 2.6.2B'de `find_broken_compatibility_references` benzeri bir kontrol eklenmesi önerildi.
- `CoatingRecord.friction_coefficient_range` ile yeni `FrictionConditionRecord` verisi aynı coating için ileride tutarsız hale gelebilir. Bu ADR'de çözülmedi — açık karar olarak taşındı.

## 13. Açık kararlar

1. `CoatingRecord.friction_coefficient_range`'in ne zaman/nasıl deprecate edileceği.
2. `coating_id`/`lubricant_id` için referans bütünlüğü kontrolü eklenip eklenmeyeceği.
3. `thread_condition`/`bearing_condition` için kapalı sözlük (enum) gerekip gerekmediği.
4. Migrasyon sonrası `LUBE-SURF-*` kimlikleri için kesin deprecation penceresi/politikası.
5. Tablo 9.4 kayıtlarının migration'ında `lubricant_id` nasıl doldurulacak (yukarıda §10 "15 Tablo 9.4" bölümünde not edildi).

## 14. Kaynak matrisi (Faz 2.6.2B için gerekli kaynaklar)

| Değer | Gerekli kaynak tipi | Mevcut durum |
|---|---|---|
| μ_thread / μ_bearing (bağımsız) | VDI 2230 tablosu, ISO 16047 test raporu veya tedarikçi datasheet | Yok — onaylanmamış |
| K (nut factor) | Onaylı nut-factor kaynağı (standart veya iç test) | Yok |
| Scatter | İç ISO 16047 test serisi (istatistiksel) | Yok |
| max_temperature_c | Coating/lubricant üretici datasheet'i veya standart | Yok |
| corrosion_resistance / reusability | Kapalı ölçek veya kaynak henüz tanımlanmadı | Yok — ölçek kararı da açık |
| recommended_standards | Lubricant/coating → standart eşlemesi | Yok |
| coating_id eşlemeleri (Geomet/Dacromet/Phosphate vb.) | Mevcut `coating_library.json` — zaten var | **Mevcut**, kullanılabilir |
| Tablo 9.4 overall coefficient (combined) | Makine Elemanlari ders kitabı, Tablo 9.4, s.211 | **Mevcut**, `LubricationRecord` üzerinde (henüz migrate edilmedi) |

## 15. Faz 2.6.2B kabul kriterleri (öneri)

1. Her yeni mühendislik değeri (`overall_friction_coefficient_*`, `mu_thread_*`, `mu_bearing_*`, `k_factor_*`, `scatter_percent`, `max_temperature_c`) yalnızca `FrictionConditionRecord` üzerinde, dolu `source_reference`/`source_type`/`source_page_or_table`/`verification_status` ile girilir — `LubricationRecord`/`CoatingRecord`'a yeni sayısal değer eklenmez (ADR-0010 riski #1'in doğrudan uygulaması).
2. Her yeni kayıt, açık kararlar §13.2 çözülene kadar `coating_id`/`lubricant_id` için mevcut bir `CoatingRecord`/`LubricationRecord` id'sine referans verir; boşsa gerekçesi `engineering_notes`'ta belirtilir.
3. Kaynaksız hiçbir değer girilmez — `find_friction_coefficient_missing_source` kontrolü `FrictionConditionRecord` verisi için de 0 ihlal döndürür.
4. `μ_thread` girilirse `μ_bearing` da girilir (ve tersi) — `find_friction_one_sided_thread_bearing` 0 ihlal.
5. Tüm min/max çiftleri min≤max, hiçbiri tek taraflı değil.
6. Mevcut 10 coating + 23 lubrication + (yeni popülasyondan önceki) 0 friction-condition kaydı hâlâ değişmeden yükleniyor.
7. Tam pytest + flake8 + `git diff --check` temiz; working tree clean.
8. Bu fazın açık kararlarından en az #1 (coating_id/lubricant_id referans bütünlüğü kontrolü) ele alınır veya bilinçli olarak ertelendiği gerekçelendirilir.
