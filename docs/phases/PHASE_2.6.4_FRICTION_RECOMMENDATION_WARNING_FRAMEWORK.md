# Faz 2.6.4 — Friction Condition Recommendation and Warning Framework

- **Status:** Delivered (deterministic warnings + recommendation readiness only — no recommendation engine)
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç

## 1. Kapsam ve kapsam dışı

**Kapsam:** mevcut doğrulanmış veriden deterministik mühendislik uyarıları üretmek; gelecekteki recommendation engine için veri-yeterlilik kontrollü readiness altyapısı hazırlamak; yalnızca overall friction range'e dayalı, tamamen betimleyici karşılaştırma.

**Kapsam dışı (bu fazda kesinlikle yapılmadı):** en iyi yağlayıcı/coating önerme, tork azaltma yüzdesi önerme, sıcaklığa/korozyona göre ürün seçme, reusability kararı, sıkma yöntemi seçimi, "A daha iyidir/güvenlidir" türü yargılar, "recommended torque" sonucu, "production-approved" veya "ISO 16047 certified" etiketi.

## 2. Mevcut veri yeterlilik analizi

18 `FrictionConditionRecord`'un tamamı: yalnızca `overall_friction_coefficient_min/max` + `friction_model=combined_or_unspecified`. Yok: μ_thread, μ_bearing, K, scatter, doğrulanmış corrosion rating, doğrulanmış reusability, doğrulanmış max-temperature, recommended_standards. Bu, Faz 2.6.2B'nin kaynak matrisiyle birebir tutarlı — hiçbir yeni veri toplanmadı, yalnızca mevcut alanlardan güvenli çıkarım yapıldı.

## 3. Warning rule matrix

| Uyarı grubu | Koşul | Metin | Test |
|---|---|---|---|
| Combined friction | `friction_model == combined_or_unspecified` | 3 satır (bkz. §8 kod) | `test_combined_friction_warning_present_for_every_live_record` |
| Reference-only | `verification_status == reference_only` | 2 satır | `test_reference_only_warning_present_for_every_live_record` |
| Restricted legacy | referenced coating/lubricant `status == restricted_legacy` | 2 satır + `regulatory_warning` korunur | `test_restricted_legacy_warning_and_regulatory_text_preserved` |
| Missing source | `source_reference` boş | Bloklanır (CalculationInputError) | `test_missing_source_blocks_warnings` |
| Incomplete condition | `coating_id` ve `lubricant_id` ikisi de boş | `recommendation_available=False`, blocking_reasons | `test_incomplete_condition_both_ids_empty_is_warnings_only` |
| Torque calculation | Faz 2.6.3 readiness torque hesabını bloklarsa | 2 satır | `test_torque_calculation_warning_present_for_every_live_record` |

Tüm 18 canlı kayıt için: combined friction + reference-only + torque-calculation uyarıları **her zaman** üretilir (hiçbiri μ_thread/μ_bearing'e sahip değil, hiçbiri verified test verisi değil). Restricted-legacy hiçbir canlı kayıtta tetiklenmiyor (hiçbiri restricted_legacy coating/lubricant'a referans vermiyor) — sentetik veriyle test edildi.

## 4. Readiness seviyeleri

`warnings_only` < `comparison_only` < `engineering_recommendation_ready` < `production_recommendation_ready`.

**18/18 canlı kayıt: `comparison_only`** (overall μ aralığı mevcut → `reference_comparison` capability açık; her şey diğer capability bloklu). **0/18 kayıt `engineering_recommendation_ready` veya `production_recommendation_ready`** — bu, `test_no_live_record_reaches_engineering_or_production_ready` ile doğrudan doğrulanıyor.

`intended_use` (`reference_comparison`/`engineering_calculation`/`production_release`) yalnızca boşluk uyarısı ekler, seviyeyi asla yükseltmez (`test_intended_use_annotates_gap_but_does_not_upgrade_level`).

## 5. Capability matrix

| Capability | Gerekli veri | Durum (18 kayıt) |
|---|---|---|
| Reference comparison | overall μ aralığı | **Açık** (18/18) |
| Torque sensitivity | onaylı formül + geçerli friction model | Bloklu (Faz 2.6.3: hiçbir formül tek μ kabul etmiyor) |
| Torque recommendation | K veya split friction + geometry | Bloklu (0/18) |
| Lubricant recommendation | sıcaklık/korozyon/uygulama/ürün verisi | Bloklu (0/18) |
| Coating recommendation | aynı | Bloklu (0/18) |
| Production approval | uygulamaya özel doğrulanmış test verisi | Bloklu (0/18) |

## 6. Comparison rules

Yalnızca overall μ aralığı, source classification (`coating_based`/`lubricant_based`), verification_status kullanılarak: `range_relation` (`identical`/`a_lower`/`b_lower`/`overlapping`/`not_comparable`), `width_relation` (`equal_width`/`a_narrower`/`b_narrower`), `source_status_relation` (`same`/`different`). Çıktı tamamen betimleyici — "better/safer/recommended/superior/worse" kelimeleri asla üretilmiyor (`test_comparison_never_states_better_or_safer`); her zaman "No tightening recommendation can be derived from this comparison." ekleniyor.

## 7. API sözleşmesi

**Yeni, additive endpoint:** `POST /api/friction-condition/assess`
- Girdi: `friction_condition_id` (zorunlu), `compare_with_id` (opsiyonel), `intended_use` (opsiyonel).
- Çıktı: `friction_condition_id`, `warnings`, `recommendation_readiness` (tam `FrictionRecommendationResult`), `torque_readiness` (Faz 2.6.3'ten), `source_reference`, `verification_status`, ve `compare_with_id` verilmişse `comparison`.
- Hatalar: bilinmeyen/broken/kaynaksız ID → `HTTPException(422, ...)`.

**`/api/engineering/check`:** değişmedi, kırılmadı. `friction_condition_id` verilirse yalnızca mevcut `friction_readiness` anahtarı (Faz 2.6.3'ten) döner — bu fazda `friction_recommendation_readiness` gibi ek bir alan **eklenmedi** (ayrı endpoint tercih edildi, direktifin "tercihen yeni endpoint" önerisine uyuldu).

## 8. Güvenlik sınırları — doğrulama

| Kural | Durum |
|---|---|
| Overall μ'den tork azaltma oranı üretme | Uygulanmadı |
| Lubricant/coating effectiveness sıralaması | Uygulanmadı |
| Sıcaklık/korozyon/reusability önerisi | Uygulanmadı |
| Preload/tightening-method önerisi | Uygulanmadı |
| "production-approved" etiketi | Uygulanmadı |
| "ISO 16047 certified" ifadesi | Uygulanmadı |
| "recommended torque" sonucu | Uygulanmadı |

## 9. Bloklanan öneri listesi (özet)

Her 18 kayıt için: lubricant_recommendation, coating_recommendation, torque_recommendation, torque_sensitivity, production_approval — **tümü bloklu**. Yalnızca reference_comparison açık.

## 10. Dosya bazlı değişiklikler

| Dosya | Değişiklik |
|---|---|
| `backend/calculation_engine/friction_recommendations.py` | Yeni |
| `backend/app.py` | `FrictionConditionAssess` modeli, `POST /api/friction-condition/assess` (additive), dual-path import |
| `tests/test_faz2_6_4_friction_recommendation_warnings.py` | Yeni — 33 test |
| `docs/05`, `docs/09`, `docs/11`, `docs/adr/ADR-0010-*.md` | Faz 2.6.4 notu/addendum |
| `docs/phases/PHASE_2.6.4_FRICTION_RECOMMENDATION_WARNING_FRAMEWORK.md` | Bu belge |

`backend/engineering_core/`, `backend/calculation_engine/friction_readiness.py` — dokunulmadı.

## 11. Test sonuçları

**781 test geçti** (748 → 781, 0 regresyon). Özellikle doğrulanan: combined-friction/reference-only/restricted-legacy/torque-calculation uyarıları, `regulatory_warning` korunması, unknown ID/broken reference/missing source blokajı, warnings-only/comparison-only readiness, lower/higher/overlapping/non-overlapping/identical aralık karşılaştırması, "better" yargısının hiç üretilmediği, torque/temperature/corrosion önerisinin hiç üretilmediği, `intended_use` davranışı, API backward compatibility, deterministik uyarı sırası, regresyon testleri. **18/18 kaydın hiçbiri `engineering_recommendation_ready`/`production_recommendation_ready` döndürmüyor** — doğrudan test edildi.

## 12. Faz 2.6.5'e geçiş kriterleri (öneri)

1. En az bir lubricant/coating için onaylı μ_thread/μ_bearing veya K kaynağı sağlanmadan `engineering_recommendation_ready` hiçbir zaman tetiklenemez — bu veri toplama kararı hâlâ açık (Faz 2.6.2B kaynak matrisi).
2. `friction_recommendations` çıktısının frontend'de nasıl sunulacağına dair tasarım kararı (bu faz UI yapmadı).
3. `/api/friction-condition/assess` için rol/yetkilendirme politikasının gözden geçirilmesi (şu an yalnızca `Depends(user)` — mevcut `/api/engineering/check` ile aynı seviye).
4. Coating/lubricant referans bütünlüğü kontrolünün (Faz 2.6.2B) recommendation readiness akışına düzenli olarak entegre kalması için `run_all_integrity_checks()` üzerinden izlenmesi.
