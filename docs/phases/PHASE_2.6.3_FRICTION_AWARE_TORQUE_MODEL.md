# Faz 2.6.3 — Friction-Aware Torque Model and Decomposition Readiness

- **Status:** Delivered (readiness/infrastructure only — no torque calculation added)
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç

## 1. Mevcut hesap motoru analizi (önce yapılan inceleme)

İncelenen dosyalar: `backend/engineering_core/friction.py`, `torque.py`, `joint.py`, `validation.py`; `backend/calculation_engine/` (formula_registry, provider, request/response, exceptions, `providers/vdi2230_provider.py`); `backend/app.py` (`EngineeringCheck` modeli, `/api/engineering/check` route); ilgili testler (`tests/test_engineering.py`, `tests/test_calculation_engine_scaffold.py`, `tests/test_vdi2230_*.py`).

**Bulgular:**

1. **Canlı/kullanılan yol:** `/api/engineering/check` → `evaluate_joint()` (`engineering_core/joint.py`) → `torque.tightening_torque_nm()`. Bu formül **zorunlu olarak** ayrı `mu_thread` ve `mu_bearing` ister (`EngineeringCheck` Pydantic modelinde her ikisi de `Field(ge=0, le=1)`, varsayılan yok). **Tek/birleşik μ girişi desteklenmiyor — hiçbir zaman desteklenmemiş.**
2. **Section 4 (Quick estimate, `M_A = K*d*F_M`):** `K` (nut factor) gerektiriyor. Kod tabanında hiçbir yerde bir `K` hesaplama/kabul yolu implementasyonu yok; formül spesifikasyonu zaten "K değeri türetme" kuralını taşıyor.
3. **Section 5 (Detailed decomposition, `M_G`+`M_K`):** `torque.tightening_torque_nm()` olarak implement edilmiş, ayrı `mu_thread`/`mu_bearing` gerektiriyor.
4. **`backend/calculation_engine/` (provider mimarisi, formula registry):** "prerequisite scaffolding" — henüz hiçbir canlı API route'una bağlı değil (`app.py` içinde referans yok). `VDI2230Provider` `backend.vdi2230_core`'u sarıyor, o da kendi bağımsız formül kataloğuna sahip; friction-condition library ile bağlantısı yok.
5. **Frontend hesap akışı:** `frontend/index.html` (PWA shell) mevcut API'yi çağırıyor; `friction_condition_id` gibi yeni bir alan için henüz UI yok (bu faz kapsamı dışı, UI yapılmayacak).

**Sonuç:** Ne Section 4 ne de Section 5, `FrictionConditionRecord`'un elindeki tek `overall_friction_coefficient` değerini yasaklanmış bir türetme yapmadan (K türetme veya μ'yü thread+bearing'e kopyalama) kullanabilir. **Mevcut hiçbir formül tek/birleşik μ kabul etmiyor.**

## 2. Mode A / Mode B ayrımı — uygulanan karar

### Mode A – Combined Friction Estimate

**Sonuç: torque hesabı üretilmiyor (blocked).** Gerekçe: yukarıdaki analiz. `FrictionConditionRecord`'un `overall_friction_coefficient_min/max` verisi var (18 kayıtta), ama bunu bir torque değerine çevirecek onaylı hiçbir formül yok. Bunun yerine:

- `calculation_mode = "mode_a_combined_estimate"` seçilir (veri profili eşleşiyor).
- `blocking_reasons` içinde `unsupported_friction_model` nedeni açık gerekçeyle raporlanır.
- **Friction-katsayı** (torque değil) min/nominal/max senaryosu üretilir: `combined_friction_scenarios()` — nominal değer daima aritmetik ortanca, `nominal_estimate_policy = "arithmetic_midpoint_of_reference_range"` ile açıkça etiketlenir.
- 4 zorunlu mühendislik uyarısı her zaman eklenir (bkz. §5).
- Thread/bearing torque, total torque, preload contribution — hepsi `null`.

### Mode B – Separated Friction Model

**Sonuç: hiçbir canlı kayıt bu moda uygun değil (0/18).** Hiçbir `FrictionConditionRecord`'da `mu_thread_min/max` + `mu_bearing_min/max` yok. Altyapı hazır: `assess_friction_readiness(..., has_joint_geometry=True, has_preload=True)` çağrısı, eğer gelecekte bir kayıt μ_thread+μ_bearing içerirse ve gerekli geometri/preload bayrakları da sağlanırsa, `calculation_mode = "mode_b_separated_model"` ve `decomposition_available = True` döndürecek şekilde tasarlandı ve test edildi (hipotetik/mock kayıtla doğrulandı — gerçek veri yok). **Bu modda dahi bu fazda hiçbir torque sayısı üretilmiyor** — yalnızca hazır olma durumu raporlanıyor.

## 3. Uygulama kapsamı

### 3.1 Yeni readiness katmanı

`backend/calculation_engine/friction_readiness.py` (yeni, additive):

- `assess_friction_readiness(friction_condition_id, *, has_joint_geometry=False, has_preload=False) -> FrictionReadinessResult`
- Durum kodları (direktifin örnek listesi + kesin çözümleme hataları): `combined_estimate_available`, `separated_model_available`, `insufficient_friction_data`, `missing_joint_geometry`, `reference_only_source`, `unsupported_friction_model`, `unknown_friction_condition_id`, `broken_reference`, `missing_source_traceability`.
- `FrictionReadinessResult` alanları: `calculation_mode`, `friction_condition_id`, `friction_model`, `data_completeness`, `decomposition_available`, `blocking_reasons`, `source_reference`, `verification_status`, `engineering_warnings`, `combined_friction_scenarios`, ve (her zaman `None`) `thread_raising_torque`, `thread_friction_torque`, `bearing_friction_torque`, `total_torque`, `preload_contribution_percent`.

### 3.2 ID çözümlemesi

- Kayıt bulunamazsa: `CalculationInputError("unknown_friction_condition_id: ...")`.
- `coating_id`/`lubricant_id` broken ise (Faz 2.6.2B'nin `find_dangling_coating_references`/`find_dangling_lubricant_references` fonksiyonları yeniden kullanılıyor): `CalculationInputError("broken_reference: ...")`.
- `source_reference` boşsa: `CalculationInputError("missing_source_traceability: ...")`.
- `verification_status = reference_only` ise: hata değil, `engineering_warnings`'e etiket eklenir.

### 3.3 Senaryo hesabı (yalnızca katsayı, torque değil)

`combined_friction_scenarios(overall_min, overall_max)` → `{minimum, nominal_estimate, nominal_estimate_policy, maximum, unit}`. `nominal_estimate_policy` her zaman `"arithmetic_midpoint_of_reference_range"` — başka bir politika yok, ölçülmüş bir değer değil.

### 3.4 API/servis katmanı — additive

`backend/app.py`: `EngineeringCheck` modeline `friction_condition_id: Optional[str] = None` eklendi. Route:
- `friction_condition_id` verilmezse: davranış **birebir eskisi gibi** (yeni alan response'a eklenmiyor).
- Verilirse: mevcut deterministik `evaluate_joint()` sonucu **değişmeden** hesaplanır, ayrıca `result["friction_readiness"] = assess_friction_readiness(...).to_dict()` eklenir.
- Geçersiz/bulunamayan/broken/kaynaksız `friction_condition_id` → `HTTPException(422, ...)`, deterministik ve okunabilir mesaj.

## 4. Decomposition readiness modeli — alan eşlemesi

Direktifin istediği alanlar birebir karşılanıyor: `calculation_mode`, `friction_condition_id`, `friction_model`, `data_completeness`, `decomposition_available`, `blocking_reasons`, `source_reference`, `verification_status`, `engineering_warnings`, ve Mode-B-only (`null` kalan) `thread_raising_torque`, `thread_friction_torque`, `bearing_friction_torque`, `total_torque`, `preload_contribution_percent`.

## 5. Uyarılar (Mode A'da her zaman eklenen 4 metin)

- "Combined friction data does not support thread/bearing torque decomposition."
- "Result is a sensitivity estimate based on a reference friction range."
- "This result must not be interpreted as ISO 16047 test certification."
- "Verified mu_thread and mu_bearing data are required for separated decomposition."

## 6. Güvenlik kurallarına uyum (doğrulama)

| Kural | Durum |
|---|---|
| Overall μ'yü μ_thread/μ_bearing'e kopyalama | **Uygulanmadı** — hiçbir kod yolu bunu yapmıyor (test: `test_no_mu_split_is_ever_inferred_from_combined_scenarios`) |
| K türetme | **Uygulanmadı** |
| Sabit torque split yüzdesi | **Uygulanmadı** — hiçbir yerde %45/%40/%15 gibi sabit değer yok |
| Kaynaksız formül/katsayı | **Uygulanmadı** |
| `CoatingRecord.friction_coefficient_range`'i doğrudan hesaplamada kullanma | **Uygulanmadı** — readiness yalnızca `FrictionConditionRecord` çözümlüyor |
| Yalnızca `FrictionConditionRecord` çözümlemesi | **Uygulandı** |
| `reference_only`'den production-approved sonuç üretme | **Uygulanmadı** — hiçbir sonuç "approved" etiketlenmiyor, hep `reference_only`/estimate |
| Sonuçta veri sınırlamasını gizleme | **Uygulanmadı** — `blocking_reasons` + `engineering_warnings` her zaman açık |

## 7. Dosya bazlı değişiklikler

| Dosya | Değişiklik |
|---|---|
| `backend/calculation_engine/friction_readiness.py` | Yeni |
| `backend/app.py` | `EngineeringCheck.friction_condition_id` (additive optional), route entegrasyonu, dual-path import |
| `tests/test_faz2_6_3_friction_aware_torque_model.py` | Yeni — 21 test |
| `docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`, `docs/09_LIBRARY_SPECIFICATION.md`, `docs/11_PRODUCT_BACKLOG.md`, `docs/adr/ADR-0010-*.md` | Faz 2.6.3 notu/addendum |
| `docs/phases/PHASE_2.6.3_FRICTION_AWARE_TORQUE_MODEL.md` | Bu belge |

`backend/engineering_core/` (friction.py, torque.py, joint.py) — **dokunulmadı**. `backend/calculation_engine/__init__.py`'nin `__all__` listesi — **dokunulmadı** (yeni modül ayrı, opsiyonel import; mevcut `test_calculation_engine_scaffold.py`'nin exact-match testi bozulmadı).

## 8. Veri yeterlilik matrisi

| Veri | 18 kayıtta durum |
|---|---|
| Overall friction coefficient | 18/18 mevcut |
| μ_thread / μ_bearing | 0/18 |
| Nut factor K | 0/18 |
| Joint geometry (thread pitch, bearing diameter vb.) | Kayıt seviyesinde yok — API çağrısı zamanında sağlanmalı (`has_joint_geometry` bayrağı) |
| Preload/clamp load | Kayıt seviyesinde yok — API çağrısı zamanında sağlanmalı (`has_preload` bayrağı) |
| Kaynak referansı | 18/18 mevcut |

## 9. Hesaplama akış diyagramı (metin)

```
friction_condition_id
      |
      v
[resolve raw record] --(not found)--> CalculationInputError(unknown_friction_condition_id)
      |
      v
[check coating_id/lubricant_id integrity] --(broken)--> CalculationInputError(broken_reference)
      |
      v
[check source_reference non-empty] --(missing)--> CalculationInputError(missing_source_traceability)
      |
      v
[parse FrictionConditionRecord]
      |
      v
has mu_thread & mu_bearing & has_joint_geometry & has_preload?
      |-- yes --> calculation_mode = mode_b_separated_model, decomposition_available = True
      |            (infrastructure only -- no live record reaches this branch;
      |             no torque value computed even here in Faz 2.6.3)
      |
      |-- no, but has overall coefficient --> calculation_mode = mode_a_combined_estimate
      |            blocking_reasons += unsupported_friction_model [+ others]
      |            combined_friction_scenarios computed (coefficient range, not torque)
      |            engineering_warnings += the 4 mandated warnings
      |
      |-- no data at all --> calculation_mode = blocked
                   blocking_reasons += insufficient_friction_data
```

## 10. Testler

23 test kalemi kapsandı (`tests/test_faz2_6_3_friction_aware_torque_model.py`, 21 test fonksiyonu): friction_condition_id resolution (2), unknown ID (1), broken reference (1), missing traceability (1), reference-only warning (1), min/mid/max scenario generation + midpoint policy (3), no μ split inference (1), Mode A decomposition fields null (1), Mode A mandated warnings (1), Mode B insufficient-data blocking + hypothetical-qualification (2), API backward compatibility (3), regression (response shape, 1), import/smoke (2).

**Sonuç: 748 test geçti** (727 → 748, 0 regresyon).

## 11. Blocked durumlar (özet)

- **Mode A gerçek tork hesabı:** blocked — hiçbir onaylı formül tek/birleşik μ kabul etmiyor.
- **Mode B:** blocked — 0/18 kayıtta μ_thread/μ_bearing split verisi var.
- **Recommendation/warning engine, torque correction, UI, PDF:** bu fazda yapılmadı (kapsam dışı, direktifin kendisi tarafından hariç tutuldu).

## 12. Faz 2.6.4'e geçiş kriterleri (öneri)

1. Önerilecek en az bir lubricant/coating için onaylı μ_thread/μ_bearing kaynak (VDI 2230 tablosu veya ISO 16047 test raporu) sağlanması — bu olmadan Mode B hiçbir zaman gerçek veriyle tetiklenemez.
2. `friction_readiness` çıktısının frontend'de nasıl gösterileceğine dair bir tasarım kararı (bu faz UI yapmadı).
3. Recommendation engine'in `blocking_reasons`/`data_completeness` alanlarını nasıl tüketeceğine dair bir arayüz sözleşmesi.
4. Nut factor K için ayrı, açık kaynaklı bir veri toplama kararı (Faz 2.6.2B'nin kaynak matrisinde `source_missing` olarak işaretliydi, hâlâ öyle).
