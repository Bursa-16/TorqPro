# Faz 2.6.6 — Friction Condition Frontend Workspace

- **Status:** Delivered (minimal, single-workspace)
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç

## 1. Amaç ve kapsam

Mevcut backend friction-condition readiness, warning, comparison ve report-preview altyapısını (Faz 2.6.3-2.6.5) TorqPro'nun tek dosyalı frontend mimarisine güvenli, anlaşılır, geriye dönük uyumlu biçimde entegre etmek. **Bu fazda yeni mühendislik formülü, yeni friction coefficient, torque recommendation veya lubricant recommendation üretilmedi** — frontend yalnızca backend'in zaten hesapladığı verileri gösteriyor.

## 2. Mevcut tek dosyalı frontend mimarisi (ön inceleme bulguları)

`frontend/index.html` (2201 → ~2600+ satır): tek HTML dosyası, harici framework/bundler yok. Navigasyon: `sidebar-item` div'leri `onclick="showPage(id)"` ile `#page-<id>` bloklarını `.page.active` sınıfıyla açıp kapatıyor. `showPage()` fonksiyonu ayrıca bir if-zinciriyle sayfa-özel yükleme fonksiyonlarını tetikliyor. API çağrıları `apiRequest(path, options)` helper'ı üzerinden (Bearer token, JSON, hata mesajı ayrıştırma). Mevcut render deseni: `innerHTML` + template literal/string concatenation — **escape helper'ı yoktu**, bu fazda `fcEsc`/`fcEscRaw` eklendi. Mobilde `.sidebar` `transform:translateX(-100%)` ile gizleniyor, `toggleMobileMenu()` ile açılıyor. State: modül seviyesinde `let` değişkenleri (örn. `AUTH_TOKEN`), event listener'lar `addEventListener` değil `onclick` attribute'ları ile bağlanıyor (bu nedenle her `innerHTML` yeniden yazımı otomatik olarak eski listener'ları temizliyor — birikme riski yapısal olarak yok). Download: `downloadText(filename, text, type)` mevcut, yeniden kullanıldı.

## 3. Navigasyon entegrasyonu

"Referans" sidebar bölümüne, "OEM Norm Sorgu" ile "Norm Rehberi" arasına tek bir additive `sidebar-item` eklendi: `onclick="showPage('frictioncondition')"`. `showPage()`'in if-zincirine `if(id==='frictioncondition'){loadFrictionConditionWorkspace();}` eklendi. Modül/sekme adı tam olarak **"Friction Condition"** — hiçbir yerde "Lubrication Module" kullanılmadı (test edildi).

## 4. UI bilgi mimarisi

Tek workspace sayfası (`#page-frictioncondition`), ayrı route değil, kart tabanlı bölümler:
1. **Condition Selection**: arama kutusu + grup filtresi (coating-based/lubricant-based) + verification status filtresi + source type filtresi → kart listesi (`.fc-condition-card`, klavye erişilebilir `tabindex="0"` + `onkeydown` Enter/Space).
2. **Overview**: ID, coating/lubricant referansı, friction model, overall range, nominal midpoint ("Arithmetic midpoint of reference range — not a measured nominal value" etiketiyle), verification status, source reference, applicability.
3. **Overall Friction Range** (SVG): min/mid/max marker, sayısal değerler, reference-only badge — torque split/preload/thread-bearing decomposition **yok**, iyi/kötü renk skalası **yok**.
4. **Recommendation Readiness**: calculation mode, recommendation readiness level, available/blocked capability badge'leri, blocking reasons, "Decomposition available: Yes/No" (backend `torque_calculation_mode`'dan türetilen, sabit kodlanmamış).
5. **Engineering Warnings**: backend `engineering_warnings` + `safety_labels` metni **birebir**, yalnızca CSS sınıfı ile önem derecesine göre renklendirilmiş (information/caution/blocked/restricted) — metin frontend'de üretilmiyor.
6. **Comparison**: ikinci condition seçici, backend `compare_with_friction_condition_id` kullanıyor; lower/higher/overlapping/identical, source/verification status karşılaştırması, self-comparison açık etiketi, "better/safer/..." hiç yok.
7. **Source & Traceability / Report Preview**: tam `report-preview` çıktısı (source_reference, source_type, source_page_or_table, verification_status, applicability, engineering_notes, checksum, data_version, timestamp, app version) + JSON indirme butonu.

## 5. Kullanılan backend endpoint'leri

- `GET /api/friction-condition` (**yeni**, Faz 2.6.6) — seçici listesi.
- `POST /api/friction-condition/report-preview` (Faz 2.6.5) — seçili kayıt + opsiyonel karşılaştırma için **tek çağrı**.

`POST /api/friction-condition/assess` (Faz 2.6.4) bilinçli olarak **kullanılmadı** — `report-preview`'in çıktısı zaten readiness/warnings/comparison'ı kapsıyor; paralel çağrı gereksiz duplication olurdu (bkz. ADR-0010 Faz 2.6.6 addendum). `/api/engineering/check` bu fazda hiç dokunulmadı.

## 6. GET list endpoint sözleşmesi

`GET /api/friction-condition` (authenticated, additive, read-only):
```json
[{
  "id": "FC-COAT-GEOMET",
  "coating_reference": "COAT-GEOMET",
  "lubricant_reference": "",
  "friction_model": "combined_or_unspecified",
  "overall_friction_coefficient_min": 0.09,
  "overall_friction_coefficient_max": 0.15,
  "verification_status": "reference_only",
  "source_type": "standard",
  "status": "provisional"
}]
```
`source_reference`, `engineering_notes`, `checksum` **kasıtlı olarak dışlandı** (bkz. §10.12, `docs/09_LIBRARY_SPECIFICATION.md`) — tam veri seti yalnızca seçili tek kayıt için `report-preview`'de.

## 7. State yönetimi

Modül seviyesi değişkenler: `FC_LIST` (liste önbelleği), `FC_SELECTED_ID`, `FC_COMPARE_ID`, `FC_REQUEST_SEQ` (stale-response guard), `FC_LAST_REPORT` (JSON indirme için). Seçim değişince (`selectFrictionCondition`) `FC_COMPARE_ID` sıfırlanıyor — eski karşılaştırma state'i taşınmıyor. API hatasında (`catch` bloğu) tüm panel innerHTML'leri hata mesajıyla değiştiriliyor, loading state kapanıyor. Boş listede `.fc-empty` mesajı gösteriliyor.

## 8. Stale-response önleme

`loadFrictionConditionSelection()` her çağrıda `++FC_REQUEST_SEQ` ile bir sıra numarası alıyor; response döndüğünde `seq !== FC_REQUEST_SEQ` ise sonuç **atılıyor** (yeni bir seçim zaten devam ediyor). Hızlı ardışık seçim değişikliklerinde eski yanıtın yanlış karta yazılması engellendi.

## 9. XSS güvenliği

`fcEsc(s)` (boş değerler için em dash "—" gösterir) ve `fcEscRaw(s)` (ham escape, boş string koru) — `&<>"'` karakterlerini HTML entity'lerine çeviriyor. **Backend'den gelen her dinamik metin** (`source_reference`, `source_type`, `engineering_notes`, `regulatory_warning` — warnings listesi içinde geliyor, escape ediliyor —, `applicability`, warning mesajları, comparison `descriptive_statements`, `blocking_reasons`, capability adları, coating/lubricant referans ID'leri) bu iki fonksiyondan biri (veya onları saran `fcFmtLabel`) üzerinden geçiyor — kod incelemesiyle satır satır doğrulandı. `innerHTML` yalnızca statik template parçaları + escape edilmiş değerlerle kullanılıyor, hiçbir yerde ham API metni doğrudan enjekte edilmiyor.

## 10. Accessibility

Condition kartları `tabindex="0"`, `role="option"`, `aria-selected`, `onkeydown` (Enter/Space) ile klavye erişilebilir. SVG range görselleştirmesi `role="img"` + açıklayıcı `aria-label` taşıyor. Butonlar (`Clear`, `Download JSON`) standart `<button>` elemanları — disabled capability'ler buton değil, pasif `<span class="fc-badge">` rozetleri (aktif buton gibi görünme riski yok).

## 11. Responsive tasarım

`@media(max-width:900px)` breakpoint'i: toolbar dikeyleşiyor, form input/select tam genişlik, condition grid tek sütuna düşüyor, field-value maksimum genişlik kısıtı kaldırılıyor. Playwright ile 1366×768, 1024×768, 390×844 (mobil, hamburger menü üzerinden) doğrulandı — hiçbirinde yatay taşma yok, warning metni kesilmiyor (bkz. §12).

## 12. Browser doğrulama sonuçları

**Playwright, gerçek Chromium, üç viewport doğrulandı.** İlk denemeler (sunucu başlatma ve Playwright çalıştırma ayrı tool-call'larda) ortam kısıtı nedeniyle zaman aşımına uğradı — arka plan işlemler tool-call'lar arası kalıcı değil. Sunucu+tarayıcı **tek bir `timeout N bash -c '...'` sarmalı komutta** birleştirilip sıkı zaman sınırıyla çalıştırılınca başarılı oldu.

| Viewport | Kayıt listesi | Overview | Readiness | Warnings | Comparison | Report Preview | Yatay taşma | Özellik-spesifik console error |
|---|---|---|---|---|---|---|---|---|
| 1366×768 | 18 kayıt yüklendi | OK | OK | OK (kesilme yok) | OK | OK | Yok | Yok* |
| 1024×768 | 18 kayıt yüklendi | OK | OK | OK (kesilme yok) | OK | OK | Yok | Yok* |
| 390×844 (mobil) | 18 kayıt yüklendi | OK | OK | OK (kesilme yok) | OK | OK | Yok | Yok* |

\* Her üç viewport'ta da sayfa yüklenirken (login öncesi) 2 adet `401 Unauthorized` console hatası gözlemlendi — bu, Friction Condition sekmesine hiç gidilmeden, oturum açılmadan önce tetiklenen, bu fazdan bağımsız, **mevcut/önceden var olan** bir davranış; Friction Condition workspace'ine özgü değil, bu fazın kapsamında incelenmedi/düzeltilmedi.

Page error (uncaught exception) hiçbir viewport'ta görülmedi. Butonlar erişilebilir bulundu (`document.querySelectorAll('#page-frictioncondition button').length === 2`). Ekran görüntüleri (`friction-condition-1366x768.png`, `friction-condition-1024x768.png`, `friction-condition-mobile.png`) geçici doğrulama çıktısı olarak üretildi — teslimat paketine dahil edilmedi (zorunlu değil).

**Kullanılan komut (özet):** `uvicorn` sunucusu ve Playwright script'i tek bir `timeout` sarmalı komutta başlatıldı; mobil viewport için `toggleMobileMenu()` tetiklenip sidebar açıldıktan sonra `[onclick="showPage('frictioncondition')"]` seçicisiyle tıklama yapıldı (düz `text=` seçici mobilde 4 eşleşme + viewport-dışı element sorunu yarattığı için).

## 13. Bilinen kısıtlar

- Yalnızca minimal, tek-workspace entegrasyon yapıldı — tam kullanıcı seçim ekranı (ayrı, zengin bir sayfa) kapsam dışı bırakıldı (direktifin kendisi böyle istedi).
- `intended_use` seçimi için frontend'de bir UI kontrolü yok (backend destekliyor, opsiyonel — bu fazda gösterilmedi).
- Sayfa yüklenirken gözlemlenen 2 adet 401 console hatası (Friction Condition'a özgü değil) araştırılmadı/düzeltilmedi.
- PDF üretimi yok (Faz 2.6.5'in kapsamı zaten değildi, bu fazda da yok).

## 14. Faz 2.6.7 kabul kriterleri (öneri)

1. Sayfa-yükleme zamanı 401 console hatasının kök nedeni araştırılmalı (bu özelliğin dışında ama genel UX/log temizliği için).
2. `intended_use` için opsiyonel bir UI kontrolü eklenmesi değerlendirilmeli.
3. Faz 2.6.2B'nin kaynak matrisindeki eksiklikler (μ_thread/μ_bearing/K/scatter/verified corrosion/reusability/temperature) hâlâ açık — bunlar olmadan Readiness paneli hiçbir kayıt için `engineering_recommendation_ready`/`production_recommendation_ready`/Mode B gösteremez.
4. Daha zengin bir workspace (ayrı sayfa, çoklu-karşılaştırma, filtrelenebilir tablo görünümü) istenirse ayrı bir faz olarak planlanmalı.
