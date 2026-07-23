# Faz 2.6.2B — Verified Friction Condition Data Population

- **Status:** Delivered (partial population — only what existing sources support)
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç

## 1. Amaç

`FrictionConditionRecord` kütüphanesini yalnızca kaynak izlenebilirliği tam olan, doğrulanmış verilerle doldurmak. Kaynaksız hiçbir mühendislik değeri eklenmedi.

## 2. Source inventory (mevcut kaynak envanteri)

| Kaynak | İçerik | Kullanılabilir alanlar | Eksikler |
|---|---|---|---|
| `coating_library.json` (10 kayıt) | `friction_coefficient_range` (tek toplam aralık), ISO 16047/ISO 4042 kaynaklı | overall friction coefficient (min/max, parse edilebilir) | μ_thread/μ_bearing split yok; K yok; scatter yok; max_temperature (ayrı `temperature_range_c` var ama friction-testi sıcaklığı değil, coating işletme sıcaklığı — karıştırılmadı); corrosion (coating'in kendi `corrosion_class` alanında var, friction-condition'a taşınmadı çünkü coating'in kendi özelliği, kombinasyona özgü değil) |
| `lubrication_library.json` — 8 orijinal kayıt (Tablo 9.4 hariç) | `friction_coefficient_min/max`, ISO 16047 kaynaklı | overall friction coefficient | Aynı eksikler |
| `lubrication_library.json` — 15 Tablo 9.4 kaydı | `overall_friction_coefficient_min/max`, `friction_model=combined_or_unspecified`, textbook kaynaklı | overall friction coefficient (zaten var, taşınmadı) | lubricant_id eşlemesi belirsiz (bkz. §5); μ_thread/μ_bearing/K/scatter yok |
| Repo içi SDS/teknik dokümanlar (`docs/3xx_*`) | Production validation/torque/PPAP odaklı | — | Friction/coating/lubrication mühendislik verisi içermiyor, kontrol edildi |
| Kullanıcının sağladığı görseller (Tablo 9.4) | Faz 2.6.0'da zaten işlendi | — | Tekrar kaynak değil, zaten kullanıldı |

**Sonuç:** Bu fazda kullanılabilir tek doğrulanmış, deterministik kaynak: 10 coating + 8 lubrication kaydının zaten onaylı `friction_coefficient_range`/`friction_coefficient_min/max` değerleri. Bunların dışında hiçbir μ_thread, μ_bearing, K, scatter, max_temperature, corrosion_resistance, reusability, recommended_standards değeri için kaynak yok.

## 3. Coverage matrix (§14'ün genişletilmiş hali — hangi değer için hangi kaynak var/yok)

| Değer | Coating (10) | Lubrication-8 | Tablo 9.4 (15) | 19 hedef listesindeki diğerleri |
|---|---|---|---|---|
| Overall friction coefficient | **Var** (migrate edildi) | **Var** (migrate edildi) | Var ama migrate edilmedi (§5) | Yok |
| μ_thread / μ_bearing | Yok | Yok | Yok | Yok |
| Nut factor K | Yok | Yok | Yok | Yok |
| Scatter | Yok | Yok | Yok | Yok |
| max_temperature (friction bağlamında) | Yok (coating sıcaklığı var ama farklı kavram) | Yok | Yok | Yok |
| corrosion_resistance (friction-condition düzeyinde) | Coating'in kendi corrosion_class'ı var, taşınmadı | Yok | Yok | Yok |
| reusability | Yok | Yok | Yok | Yok |
| recommended_standards | Yok (source_standard var ama "recommended" listesi değil) | Yok | Yok | Yok |

## 4. Deterministik mapping kuralları (uygulanan)

1. Her `CoatingRecord` için, `friction_coefficient_range` doluysa: `FrictionConditionRecord{id=FC-<coating_id>, coating_id=<coating_id>, lubricant_id="", overall_min/max=parse(range), source_reference=coating.source}`.
2. Her `LubricationRecord` için (id `LUBE-SURF-` ile başlamıyorsa), `friction_coefficient_min/max` doluysa: `FrictionConditionRecord{id=FC-<lube_id>, coating_id="", lubricant_id=<lube_id>, overall_min/max=değerler, source_reference=lube.source}`.
3. Hiçbir sayısal değer türetilmedi/bölünmedi/tahmin edilmedi — birebir kopya.
4. `mu_thread/mu_bearing/k_factor/scatter/max_temperature/corrosion_resistance/reusability/recommended_standards` her kayıtta `null`/boş bırakıldı.

## 5. Tablo 9.4 (15 kayıt) — blocked, migrate edilmedi

**Karar: mapping yapılmadı.** Gerekçe (Faz 2.6.2B direktifinin varsayılan yaklaşımı): "Kuru", "Yağlı" (generic oil), "MoS₂ ile Yağlı" durumları belirli bir `LubricationRecord` ürün kimliğiyle ID seviyesinde kesin eşleşmiyor:

- "Kuru" kavramsal olarak `LUBE-DRY` ile aynı `lubricant_type` enum değerini paylaşıyor (`NO_LUBRICANT`), ancak bu bir *ürün* eşleşmesi değil, bir *durum* eşleşmesi — Tablo 9.4'ün "Kuru" verisi belirli bir yüzey/coating'e özgü iken `LUBE-DRY` genel bir referans kaydı.
- "Yağlı" (generic oil) hiçbir spesifik yağ ürünüyle (`LUBE-ENGINE_OIL` dahil) kesin eşleşmiyor — "herhangi bir yağ" anlamında.
- "MoS₂ ile Yağlı" (yağ+MoS2 karışımı) `LUBE-MOS2` (kuru MoS2 macunu/film) ile aynı fiziksel durum değil.

**Status:** `blocked` — `lubricant_id` alanı boş bırakıldı, kayıtlar migrate edilmedi. Mapping netleşirse (ör. ürün-seviyesi bir karar verilirse) ayrı, onaylı bir fazda yapılacak.

## 6. Referans bütünlüğü

- `coating_id` her zaman `coating_library.json` içinde bir kayda karşılık geliyor (`find_dangling_coating_references` — 0 ihlal).
- `lubricant_id` her zaman `lubrication_library.json` içinde bir kayda karşılık geliyor (`find_dangling_lubricant_references` — 0 ihlal).
- Bilinmeyen ID ile hiçbir kayıt oluşturulmadı.
- Her kayıt `source_reference`/`source_type`/`verification_status` dolu (`find_friction_coefficient_missing_source` — 0 ihlal).
- Duplicate-kombinasyon: `coating_id`+`lubricant_id`+`surface_condition`+`thread_condition`+`bearing_condition`+`source_reference` benzersiz (`find_duplicate_friction_condition_combination` — 0 ihlal, her kayıt farklı coating/lubricant id'sine sahip).

## 7. Üretilen kayıtlar

**18 `FrictionConditionRecord`** — hedef sayı belirlenmedi, yalnızca doğrulanmış kaynak sayısı kadar:
- 10 × `FC-COAT-*` (coating kaynaklı)
- 8 × `FC-LUBE-*` (lubrication kaynaklı)

Dolu alanlar: `id`, `coating_id`/`lubricant_id` (biri boş), `friction_model=combined_or_unspecified`, `overall_friction_coefficient_min/max`, `applicability`, `source_reference`, `source_type=standard`, `verification_status=reference_only`, `engineering_notes` (hangi kaynak kayıttan taşındığını belirtir), `status=provisional`, `notes`.

Bilinçli olarak boş bırakılan alanlar: `surface_condition`, `thread_condition`, `bearing_condition`, `mu_thread_min/max`, `mu_bearing_min/max`, `k_factor_min/max`, `scatter_percent`, `max_temperature_c`, `source_page_or_table` — hiçbiri için kaynak yok.

## 8. Veri generator/import script

`tools/generate_faz_2_6_2b_friction_condition_records.py` — deterministik, idempotent (iki kez çalıştırma aynı byte-identical çıktıyı verir, test edildi: `test_generator_script_is_idempotent`). Checksum SHA-256 (`population.find_checksum_mismatches` algoritmasıyla birebir uyumlu, formülü aynı).

## 9. `CoatingRecord.friction_coefficient_range` — deprecation planı

- **Bu fazda silinmedi.** Değişmeden kaldı, 10 kayıt etkilenmedi.
- Docstring'e not eklendi: aktif friction-condition hesaplama kaynağı olarak kullanılmaması, bunun yerine karşılık gelen `FrictionConditionRecord` (`FC-<coating_id>`) kullanılması gerektiği belirtildi.
- Kesin deprecation zaman çizelgesi/politikası **açık karar olarak kaldı** (ADR-0010 açık karar #1) — gelecek bir fazda ele alınacak.
- Geriye uyumluluk yolu: alan kod seviyesinde hiçbir zaman zorla kaldırılmayacak/otomatik silinmeyecek; bir üst faz açıkça karar vermeden field kaldırılmaz.

## 10. Geriye dönük uyumluluk

- 10 coating + 23 lubrication kaydının tamamı değişmeden doğrulanıyor (`test_coating_and_lubrication_files_unchanged_in_shape`, id-prefix + sayı kontrolü).
- Hiçbir mevcut alan yeniden adlandırılmadı/silinmedi/tipi değiştirilmedi.
- API/route dokunulmadı.

## 11. Dosya bazlı uygulama planı (bu fazda yapılanlar)

| Dosya | Değişiklik |
|---|---|
| `backend/library/data/friction_condition_library.json` | 0 → 18 kayıt |
| `backend/library/models.py` | `CoatingRecord.friction_coefficient_range` docstring notu (deprecation-for-calculation-use) |
| `backend/library/validator.py` | `find_duplicate_friction_condition_combination`, `find_dangling_coating_references`, `find_dangling_lubricant_references`; `validate_friction_condition_library` genişletildi |
| `backend/library/population.py` | `find_broken_friction_condition_references`, `run_all_integrity_checks()` güncellendi |
| `tools/generate_faz_2_6_2b_friction_condition_records.py` | Yeni — idempotent generator |
| `tests/test_faz2_6_2b_verified_friction_data_population.py` | Yeni — 23 test |
| `tests/test_faz2_6_2a_coating_friction_data_ownership.py`, `tests/test_loader.py`, `tests/test_population.py` | "empty by design" istisna listeleri güncellendi (friction condition library artık dolu) |
| `docs/adr/ADR-0010-*.md`, `docs/09/05/11` | Faz 2.6.2B addendum/güncelleme |
| `docs/phases/PHASE_2.6.2B_VERIFIED_FRICTION_DATA_POPULATION.md` | Bu belge |

## 12. Riskler

- 18 kayıt, coating/lubricant'ın *kendi* (kombinasyonsuz) tipik değerini temsil ediyor — gerçek bir "coating+lubricant kombinasyonu" değil (`lubricant_id` veya `coating_id`'den biri her zaman boş). Bu, ADR-0010'un asıl hedeflediği "kombinasyona bağlı" veriden farklı, ama mevcut en iyi doğrulanmış veri. Risk: birisi bunları yanlışlıkla "kombinasyon-spesifik" veri sanabilir. Azaltma: `applicability` alanı ve `engineering_notes` bunu açıkça belirtiyor.
- Aynı `overall_friction_coefficient` değeri hem `CoatingRecord.friction_coefficient_range` hem de yeni `FrictionConditionRecord`'da duruyor — senkronizasyon riski (ADR-0010 risk listesinde zaten belirtilmişti, değişmedi).

## 13. Açık kararlar (değişmeyen + yeni)

1. `CoatingRecord.friction_coefficient_range` deprecation zaman çizelgesi — hâlâ açık.
2. Tablo 9.4 `lubricant_id` mapping — hâlâ açık, blocked.
3. 19 hedef lubricant/coating listesindeki eksik kalemler (PTFE coating, zinc plated, hot-dip galvanized, stainless dry/lubricated vb.) için hiç kaynak yok — yeni kayıt oluşturulmadı.

## 14. Kaynak matrisi — güncellenmiş blocked durumu

| Kalem | Durum |
|---|---|
| μ_thread / μ_bearing (herhangi bir ürün için) | `source_missing` |
| Nut factor K | `source_missing` |
| Scatter | `source_missing` |
| max_temperature_c (friction bağlamı) | `source_missing` |
| corrosion_resistance / reusability (friction-condition düzeyinde) | `source_missing` |
| recommended_standards | `source_missing` |
| Tablo 9.4 → FrictionConditionRecord migration | `blocked` (§5) |
| Geomet/Dacromet/Phosphate/Zinc flake overall coefficient | **mevcut** (coating domain'inde, migrate edildi) |
| PTFE coating, zinc plated (ayrı), hot-dip galvanized, stainless dry/lubricated | `pending_supplier_data` — coating/lubrication domain'inde de kayıt yok |

## 15. Faz 2.6.3'e geçiş için eksikler

- μ_thread/μ_bearing split verisi olmadan torque decomposition (Faz 2.6.3) `FrictionConditionRecord`'dan gerçek bir split değeri okuyamaz; yalnızca 18 kaydın `overall_friction_coefficient` değerini "birleşik" olarak kullanabilir (mevcut API'nin zaten yaptığı gibi, kullanıcı girdisiyle).
- Recommendation/warning engine (Faz 2.6.4) için nut factor/scatter/corrosion/reusability/recommended_standards verisi yok — bu motorlar için veri toplama önce gerekiyor.
