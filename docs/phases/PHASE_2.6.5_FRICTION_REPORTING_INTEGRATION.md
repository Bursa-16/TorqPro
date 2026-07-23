# Faz 2.6.5 — Friction Condition Reporting and Integration

- **Status:** Delivered
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç

## 1. Mevcut rapor mimarisi analizi (ön inceleme)

İncelenen alanlar: rapor üreticisi, PDF/HTML/JSON çıktı yolları, `EngineeringCheck` response modelleri, calculation service layer (`backend/calculation_engine/`), API response serialization, frontend'in mevcut rapor akışı (`frontend/index.html`), audit/traceability alanları (`backend.app.audit`, `now_iso`), export/download endpoint'leri.

**Bulgu: bu kod tabanında bir PDF/HTML rapor üreticisi henüz yok.** `docs/310_Reporting.md` tek satırlık bir yer tutucu ("PDF, Excel, Audit."). `backend/production_validation/service.py` çalışma/veri seti kayıtlarını yönetiyor, rapor render etmiyor. `organization_settings` tablosundaki `report_title`/`logo`/`footer` alanları yalnızca kurumsal metadata, aktif bir rapor motoru değil. En yakın "rapor" yüzeyi: `/api/engineering/check`'in JSON response'u ve `audit()` fonksiyonu (traceability).

**Sonuç:** Genişletilecek mevcut bir "rapor request modeli" yok (§6 Seçenek A bu nedenle uygulanamaz — icat etmek gerekirdi). **Seçenek B seçildi:** ayrı, additive bir preview endpoint'i, PDF üretmeden önce JSON olarak doğrulanabilir bir rapor bölümü üretiyor.

## 2. Seçilen entegrasyon yaklaşımı

`POST /api/friction-condition/report-preview` — yeni, additive endpoint. `backend.calculation_engine.friction_report.build_friction_condition_report_section()` çağırır; bu fonksiyon hiçbir yeni mühendislik değeri hesaplamaz, yalnızca Faz 2.6.3/2.6.4'ün zaten hesapladığı sonuçları (`assess_friction_readiness`, `assess_recommendation_readiness`, `generate_friction_warnings`, `compare_friction_conditions`) biçimlendirir.

## 3. Rapor veri modeli

`backend/calculation_engine/friction_report.py`:

- `FrictionConditionSourceSummary`: `source_reference`, `source_type`, `source_page_or_table`, `verification_status`, `applicability`, `engineering_notes`, `record_checksum`, `data_version`.
- `FrictionConditionReadinessSummary`: `recommendation_level`, `available_capabilities`, `blocked_capabilities`, `blocking_reasons`, `required_missing_data`, `torque_calculation_mode`, `torque_blocking_reasons`.
- `FrictionConditionComparisonSummary`: `friction_condition_id_a/b`, `is_self_comparison`, `range_relation`, `width_relation`, `source_classification_a/b`, `verification_status_a/b`, `source_status_relation`, `descriptive_statements`.
- `FrictionConditionReportSection`: `friction_condition_id`, `coating_reference`, `lubricant_reference`, `friction_model`, `overall_friction_coefficient_minimum/nominal_estimate/maximum`, `nominal_policy`, `source`, `readiness`, `engineering_warnings`, `safety_labels`, `intended_use`, `comparison` (opsiyonel), `report_generated_at`, `application_version`.

Tüm alanlar additive/opsiyonel; mevcut hiçbir rapor modeli değiştirilmedi (çünkü hiçbiri yoktu — §1).

## 4. API sözleşmesi

**`POST /api/friction-condition/report-preview`**
- Girdi: `friction_condition_id` (zorunlu), `compare_with_friction_condition_id` (opsiyonel), `friction_intended_use` (opsiyonel).
- Çıktı: tam `FrictionConditionReportSection` JSON'u.
- Hatalar: bilinmeyen ID (asıl veya karşılaştırma), broken coating/lubricant referansı, kaynaksız veri, geçersiz `intended_use` → `HTTPException(422, ...)`.
- Aynı ID ile karşılaştırma: hata değil — `comparison.is_self_comparison = true` ile açıkça işaretlenir, `range_relation = "identical"`.

**`/api/engineering/check`:** değişmedi. `friction_condition_id` verilirse yalnızca mevcut (Faz 2.6.3) `friction_readiness` anahtarı döner — rapor katmanının `safety_labels`/`readiness` gibi zengin alanları buraya **kopyalanmadı** (gereksiz duplication'dan kaçınıldı, direktifin §6 uyarısına uyuldu).

**`/api/friction-condition/assess`:** (Faz 2.6.4) değişmedi, etkilenmedi.

## 5. Rapor örnek yapısı

```json
{
  "friction_condition_id": "FC-COAT-GEOMET",
  "coating_reference": "COAT-GEOMET",
  "lubricant_reference": "",
  "friction_model": "combined_or_unspecified",
  "overall_friction_coefficient_minimum": 0.09,
  "overall_friction_coefficient_nominal_estimate": 0.12,
  "overall_friction_coefficient_maximum": 0.15,
  "nominal_policy": "arithmetic_midpoint_of_reference_range",
  "source": {
    "source_reference": "ISO 16047 / ISO 4042 (typical range, not a test report)",
    "source_type": "standard",
    "verification_status": "reference_only",
    "record_checksum": "994b985b...",
    "data_version": "2.6.2b"
  },
  "readiness": {
    "recommendation_level": "comparison_only",
    "available_capabilities": ["reference_comparison"],
    "blocked_capabilities": ["torque_sensitivity", "torque_recommendation", "..."]
  },
  "engineering_warnings": ["Thread and bearing friction are not separately verified.", "..."],
  "safety_labels": [
    "Reference Only",
    "Not a Certified ISO 16047 Test Result",
    "Torque Decomposition Unavailable",
    "No Tightening Recommendation Generated",
    "Production Approval Not Available"
  ],
  "comparison": null,
  "report_generated_at": "2026-07-23T...",
  "application_version": "4.4"
}
```

## 6. Güvenlik etiketleri

5 deterministik etiket, koşula bağlı üretiliyor (§ Faz 2.6.5 addendum, ADR-0010): `Reference Only` (verification_status=reference_only), `Not a Certified ISO 16047 Test Result` (verification_status != verified/approved), `Torque Decomposition Unavailable` (Mode B hazır değilse), `No Tightening Recommendation Generated` (torque readiness bloklanmışsa), `Production Approval Not Available` (recommendation_level != production_recommendation_ready). **18/18 canlı kayıt için 5 etiketin tamamı üretiliyor** — test edildi.

## 7. Hata davranışları

| Durum | Davranış |
|---|---|
| unknown friction_condition_id | `CalculationInputError` → HTTP 422 |
| unknown compare_with_id | Aynı |
| broken coating/lubricant reference | `CalculationInputError("broken_reference: ...")` → 422 |
| missing source traceability | `CalculationInputError("missing_source_traceability: ...")` → 422 |
| invalid intended_use | `CalculationInputError("invalid_intended_use: ...")` → 422 |
| same-ID comparison | Hata değil — `is_self_comparison=true` ile açık etiketleme |

## 8. Backward compatibility

- `/api/engineering/check`: `friction_condition_id` verilmeden yapılan istekler **birebir** eskisi gibi (regresyon testiyle doğrulandı) — hiçbir yeni anahtar (`safety_labels`, `friction_recommendation_readiness` vb.) sızmıyor.
- `/api/friction-condition/assess` (Faz 2.6.4): değişmedi.
- Mevcut hiçbir rapor modeli yok, dolayısıyla kırılacak bir şey de yoktu — ama tüm alanlar yine de additive/opsiyonel tasarlandı (gelecekte gerçek bir PDF/HTML rapor modeli eklendiğinde bu bölüm doğrudan tüketilebilsin diye).

## 9. Traceability

Rapor bölümünde: `source_reference`, `source_type`, `source_page_or_table`, `verification_status`, `applicability`, `engineering_notes` (kayıttan birebir), `record_checksum` (mevcut `LibraryRecordBase.checksum` alanı — yeni bir checksum mekanizması kurulmadı), `data_version` (kütüphanenin JSON dosyasındaki mevcut `metadata.version` alanı — registry'nin statik in-memory versiyonu değil, dosyadan doğrudan okunuyor, böylece Faz 2.6.2B generator'ının güncellediği gerçek versiyon yansıtılıyor), `report_generated_at` (ISO 8601 UTC timestamp), `application_version` (mevcut `APP_VERSION` sabiti, `backend/app.py`).

## 10. Frontend kapsamı

Bu fazda **yapılmadı** (kapsam dışı, açıkça belirtildi): tam Friction Condition workspace, kullanıcı seçim ekranı. `frontend/index.html` tek dosyalı yapısına **dokunulmadı**. Minimal entegrasyon (warning badge, readiness level, source status, comparison summary, blocked recommendation notu) Faz 2.6.6'ya bırakıldı.

## 11. Dosya bazlı değişiklikler

| Dosya | Değişiklik |
|---|---|
| `backend/calculation_engine/friction_report.py` | Yeni |
| `backend/app.py` | `FrictionConditionReportPreview` modeli, `POST /api/friction-condition/report-preview` (additive), dual-path import |
| `tests/test_faz2_6_5_friction_reporting_integration.py` | Yeni — 35 test |
| `docs/05`, `docs/09`, `docs/11`, `docs/adr/ADR-0010-*.md` | Faz 2.6.5 notu/addendum |
| `docs/phases/PHASE_2.6.5_FRICTION_REPORTING_INTEGRATION.md` | Bu belge |

`backend/engineering_core/`, `backend/calculation_engine/friction_readiness.py`, `friction_recommendations.py` — dokunulmadı (yeniden kullanıldı, değiştirilmedi).

## 12. Test sonuçları

**816 test geçti** (781 → 816, 0 regresyon). Özellikle doğrulanan: rapor bölümünün tüm zorunlu alanları, nominal politika (aritmetik ortanca), kaynak izlenebilirliği, readiness özeti tutarlılığı, decomposition alanlarının modelde **hiç bulunmadığı** (yapısal guard — sadece `None` değil, alan adının kendisi yok), 5 güvenlik etiketinin 18/18 kayıtta üretildiği, **hiçbir raporda "recommended torque"/"production approved"/"certified ISO 16047"/"best lubricant"/"best coating"/"torque reduction percentage" ifadesinin geçmediği** (18 kayıt taranarak doğrulandı), overlapping/non-overlapping/identical aralık karşılaştırması, self-comparison işaretlemesi, karşılaştırmada değerlendirici dil yasağı, unknown ID/broken reference/missing source/invalid intended_use hataları, deterministik uyarı sırası, JSON serialization, API backward compatibility, mevcut regresyon testleri.

## 13. Faz 2.6.6 kabul kriterleri (öneri)

1. Frontend'de minimal "Friction Condition" paneli: warning badge'leri, readiness seviyesi, kaynak durumu, karşılaştırma özeti, bloklu öneri notu — `index.html` tek dosya yapısı korunarak.
2. `report-preview` endpoint'inin frontend'den nasıl çağrılacağına dair bir sözleşme (mevcut auth akışıyla tutarlı).
3. Gerçek bir PDF/HTML render katmanı eklenirse, bu katmanın `FrictionConditionReportSection.to_dict()` çıktısını değiştirmeden tüketmesi (bu faz bunu doğrudan hedefleyerek tasarlandı).
4. Faz 2.6.2B'nin kaynak matrisindeki eksiklikler (μ_thread/μ_bearing/K/scatter/verified corrosion/reusability/temperature) hâlâ açık — bunlar olmadan hiçbir rapor `engineering_recommendation_ready`/`production_recommendation_ready` gösteremez.
