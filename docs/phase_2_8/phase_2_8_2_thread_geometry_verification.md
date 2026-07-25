# Faz 2.8.2 - Thread Geometry Data Verification & Confidence Upgrade

Kapsam: mevcut 72 kayıt (Fine 35 + Extra Fine 29 + Coarse M68-M100 8). Yeni çap, yeni seri veya yeni kayıt eklenmedi. `ThreadRecord` şeması değiştirilmedi (`extra="forbid"` aynen korunuyor).

## 0. Önemli sınırlamalar (doğrulamanın kapsamı ne anlama GELMİYOR)

- **72/72 kayıt geometrik olarak mevcut formüllerle doğrulandı** (ISO 724/68-1 temel profil formülü + ISO 898-1 stress area formülü, bağımsız yeniden hesaplama). **Bu, kayıtların BİRİNCİL standart kaynağıyla (ISO 261/262 metni/tablosu) doğrulandığı anlamına GELMEZ.** Yalnızca "kayıtlı pitch doğruysa, kayıtlı geometri de doğru hesaplanmış" önermesi kanıtlanmıştır -- pitch'in kendisinin standart tablosuyla eşleştiği ayrı bir sorudur (bkz. aşağı).
- Fine ve Extra Fine seriler (toplam **64 kayıt**), ISO 261/262 birincil tablosuna bu oturumda erişim olmadığı için **G4/provisional seviyesinde bırakıldı.**
- M68, M72, M80, M90 ve M100 coarse kayıtları **yalnızca iki bağımsız İKİNCİL kaynakla** (Aspen Fasteners, mfindllc.com teknik referans tabloları) doğrulandığı için **G3/"reference_only" seviyesine yükseltildi** -- G1/G2 ("birincil standarttan doğrudan doğrulandı") DEĞİL.
- M76, M85 ve M95 kayıtlarının coarse pitch değerleri hiçbir bağımsız kaynakta bulunamadığı, dolayısıyla doğrulanamadığı için **G4 olarak kaldı.**
- **Hiçbir geometrik değer değiştirilmedi** (nominal_diameter_mm, pitch_mm, major/pitch/minor_diameter_mm, stress_area_mm2 -- 72 kaydın hiçbirinde). Yalnızca 5 kaydın provenance/confidence metadata alanları güncellendi.
- Stress-area kontrolünün kullandığı `backend.vdi2230_core.stress_area.tensile_stress_area_mm2()` fonksiyonunun kendi docstring'inde **"PROVISIONAL: requires independent source sign-off before production use"** ifadesi bulunuyor. **Bu nedenle stress-area kontrolü "birincil standart doğrulaması" olarak sunulmamaktadır** -- yalnızca üretim/formül-tutarlılığı kontrolüdür.
- ISO 68-1 için şemada ayrı, yapılandırılmış bir izlenebilirlik alanı yok; bu sınırlama **Faz 2.8.10 teknik borcu olarak kaydedilmiştir** (bkz. Bölüm 9).

## 1. İncelenen kayıt sayısı

- Toplam: **72**
  - Coarse: 8
  - Fine: 35
  - Extra Fine: 29

## 2. Sonuç özeti

- Değişmeden doğrulanan (geometri OK, confidence korunuyor): **67**
- Confidence seviyesi yükseltilen: **5**
- G4 olarak bırakılan: **67**
- Düzeltilen (değer hatası bulunan) kayıt: **0** (bu fazda hiçbir geometrik değer hatalı bulunmadı; bkz. Bölüm 3)

## 3. Geometri doğrulama (ISO 724/68-1 formülü ile bağımsız yeniden hesaplama)

Tüm 72 kayıt için major/pitch/minor diameter ve stress area, `backend.library.thread_geometry` (ISO 724/68-1 temel profil formülleri) ve `backend.vdi2230_core.stress_area` (ISO 898-1 formülü) ile bağımsız olarak yeniden hesaplandı ve toleranslar içinde (çaplar ±0.0005 mm, stress area ±max(0.002, %0.002)) mevcut kayıtlı değerlerle eşleşti. Hiçbir değer hatası bulunmadı.

### Geometrik sıralama/pozitiflik invariant kontrolü

Tüm kayıtlarda `major_diameter_mm >= pitch_diameter_mm >= minor_diameter_mm > 0` ve `stress_area_mm2 > 0` sağlandı.

## 4. Confidence yükseltme dağılımı

| Kayıt | Seri | Önce | Sonra | Kaynak kanıtı |
|---|---|:---:|:---:|---|
| THR-M68-COARSE | Coarse | G4 | G3 | Aspen Fasteners metric/inch thread pitch reference (aspenfasteners.com/content/pdf/thread_pitch.pdf): M68 coarse pitch = 6 mm; mfindllc.com METRIC PITCH THREAD CHART: M68 coarse pitch = 6 mm |
| THR-M72-COARSE | Coarse | G4 | G3 | Aspen Fasteners thread pitch reference: M72 coarse pitch = 6 mm; mfindllc.com METRIC PITCH THREAD CHART: M72 coarse pitch = 6 mm |
| THR-M80-COARSE | Coarse | G4 | G3 | Aspen Fasteners thread pitch reference: M80 coarse pitch = 6 mm; mfindllc.com METRIC PITCH THREAD CHART: M80 coarse pitch = 6 mm |
| THR-M90-COARSE | Coarse | G4 | G3 | Aspen Fasteners thread pitch reference: M90 coarse pitch = 6 mm; mfindllc.com METRIC PITCH THREAD CHART: M90 coarse pitch = 6 mm |
| THR-M100-COARSE | Coarse | G4 | G3 | Aspen Fasteners thread pitch reference: M100 coarse pitch = 6 mm; mfindllc.com METRIC PITCH THREAD CHART: M100 coarse pitch = 6 mm |

## 5. G4 olarak bırakılan kayıtlar ve nedenleri

**1 kayıt** -- M76 does not appear in either independent secondary reference consulted this session (both list ...M72, M80... with no M76 entry). Cannot confirm whether this is a genuine ISO 261 diameter/pitch combination or a non-preferred/interpolated entry without primary-standard access.
  - THR-M76-COARSE

**1 kayıt** -- M85 does not appear in either independent secondary reference consulted this session. Same limitation as M76 -- see above.
  - THR-M85-COARSE

**1 kayıt** -- M95 does not appear in either independent secondary reference consulted this session. Same limitation as M76 -- see above.
  - THR-M95-COARSE

**64 kayıt** -- Secondary-source cross-check found the pitch-selection method itself unconfirmed against the primary ISO 261/262 multi-choice pitch table (paywalled; not accessible in this session). Available secondary summaries disagree with several stored values, but ISO 261/262 fine series are multi-choice per diameter, so disagreement with a single-choice secondary summary does not prove the stored value is wrong either. Left at G4/provisional per the 'no unverifiable upgrade' rule; recommended for Faz 2.8.10 (primary-standard-table acquisition).
  - Örnekler: THR-M8x0.8-XFINE, THR-M10x1-XFINE, THR-M12x1.25-XFINE, THR-M14x1.5-XFINE, THR-M16x1.5-XFINE, THR-M18x1.75-XFINE, ... (+58 diğer)

## 6. Değer bazında before/after özeti

| Kayıt | Alan | Önce | Sonra |
|---|---|---|---|
| THR-M68-COARSE | confidence | 4 | 3 |
| THR-M68-COARSE | validation_status | provisional | reference_only |
| THR-M72-COARSE | confidence | 4 | 3 |
| THR-M72-COARSE | validation_status | provisional | reference_only |
| THR-M80-COARSE | confidence | 4 | 3 |
| THR-M80-COARSE | validation_status | provisional | reference_only |
| THR-M90-COARSE | confidence | 4 | 3 |
| THR-M90-COARSE | validation_status | provisional | reference_only |
| THR-M100-COARSE | confidence | 4 | 3 |
| THR-M100-COARSE | validation_status | provisional | reference_only |

Not: `nominal_diameter_mm`, `pitch_mm`, `major_diameter_mm`, `pitch_diameter_mm`, `minor_diameter_mm`, `stress_area_mm2` alanlarında **hiçbir değer değişmedi** -- yalnızca provenance/confidence metadata alanları (confidence, confidence_level, validation_status, approval_status, review_status, notes, source, source_reference, revision, source_revision, checksum) güncellendi.

Bu çalıştırmada dosyada değişiklik yapılmadı -- yukarıdaki yükseltmeler önceki bir `--apply` çalıştırmasında zaten uygulanmış ve kalıcı hale getirilmiştir (idempotent yeniden çalıştırma).

## 7. Kaynak bazında dağılım

| source_standard | Kayıt sayısı |
|---|---:|
| ISO 724 / ISO 261 | 8 |
| ISO 724 / ISO 261 (pitch selection unverified) | 64 |

## 8. Fine / Extra Fine / Coarse ayrı sonuçları

### Coarse

- Kayıt sayısı: 8
- Çap aralığı: M68-M100
- Yükseltilen: 5 / 8
- Duplicate (nominal_diameter_mm, pitch_mm) kombinasyonu: 0

### Fine

- Kayıt sayısı: 35
- Çap aralığı: M3-M100
- Yükseltilen: 0 / 35
- Duplicate (nominal_diameter_mm, pitch_mm) kombinasyonu: 0

### Extra Fine

- Kayıt sayısı: 29
- Çap aralığı: M8-M100
- Yükseltilen: 0 / 29
- Duplicate (nominal_diameter_mm, pitch_mm) kombinasyonu: 0

## 9. ISO 724 ve ISO 68-1 izlenebilirlik durumu

- **ISO 724**: nominal çap ve pitch serisi/tablosu kaynağı -- `source_standard` alanında ("ISO 724 / ISO 261") açıkça belirtiliyor.
- **ISO 68-1**: temel profil / geometrik formül ilişkisinin kaynağı (H = sqrt(3)/2 * P temel üçgen yüksekliği ve 0.75H/1.25H/(17/12)H faktörleri) -- `backend/library/thread_geometry.py` modül docstring'inde açıkça belgeleniyor, ancak `ThreadRecord` şemasında ayrı bir `iso_68_1_reference` alanı **yok**.
- **Teknik sınırlama**: mevcut şema (`extra="forbid"`) ISO 68-1'i ayrı, yapılandırılmış bir alan olarak taşıyamıyor. Bu faz şemayı değiştirmedi (görev kuralı). Yükseltilen 5 kayıtta bu ayrım `notes` serbest-metin alanında açıkça belirtildi ("ISO 724 basic-profile formula"); değiştirilmeyen 67 kayıtta bu ek not eklenmedi (gereksiz diff'ten kaçınmak için) -- rapor seviyesinde bu bölümde belgelendi.
- **Faz 2.8.10 önerisi**: `ThreadRecord`'a opsiyonel, additive bir `basic_profile_standard` (öntanımlı "ISO 68-1") alanı eklenmesi, ISO 724 (boyut tablosu) ile ISO 68-1 (temel profil formülü) ayrımını her kayıtta yapılandırılmış biçimde taşımayı sağlar -- şema değişikliği gerektirdiği için bu fazın kapsamı dışında bırakıldı.

## 10. Stress area doğrulama yöntemi

`backend.vdi2230_core.stress_area.tensile_stress_area_mm2()` (ISO 898-1 formülü, A_s = pi/4 * ((d2+d3)/2)^2, d2/d3 ISO 68-1 faktörleriyle) kullanılarak her 72 kayıt için bağımsız olarak yeniden hesaplandı ve kayıtlı `stress_area_mm2` değeriyle karşılaştırıldı (bkz. Bölüm 3). Bu formül modülü kendi docstring'inde "PROVISIONAL: requires independent source sign-off before production use" olarak işaretli -- bu durum değiştirilmedi, yalnızca üretim tutarlılığı doğrulandı, formülün kendisi onaylanmadı.

## 11. Açık kalan veri boşlukları

- 67 kayıt G4/provisional durumunda kalıyor (bkz. Bölüm 5) -- birincil ISO 261/262 standart tablosuna erişim olmadan pitch-seçim doğruluğu teyit edilemiyor.
- M76/M85/M95 (Coarse) için ikincil kaynaklarda doğrulama bulunamadı; bu üç çapın ISO 261'in "preferred"/"seçilmiş" serisinde olup olmadığı belirsiz kalıyor.
- Thread şemasında ISO 68-1 için ayrı, yapılandırılmış bir izlenebilirlik alanı yok (bkz. Bölüm 9, Faz 2.8.10 önerisi).
- `stress_area` formülü (`backend.vdi2230_core.stress_area`) kendi docstring'inde hâlâ PROVISIONAL; bağımsız mühendislik onayı bu fazın kapsamında değil.

## 12. Faz 2.8.3 için Go / No-Go önerisi

**GO.** Geometri hesaplama zinciri (ISO 724/68-1 formülleri, ISO 898-1 stress area) 72/72 kayıtta bağımsız olarak doğrulandı, hiçbir değer hatası bulunmadı, 5 kayıt kaynak kanıtıyla G3'e yükseltildi. Kalan G4 kayıtlar (Fine/Extra Fine tamamı + M76/M85/M95) üretim davranışını bozmuyor (population.py erişim yolu değişmedi, VDI 2230 hesaplama zincirine giren değerler aynı kaldı) ve açıkça belgelendi. Faz 2.8.3 (Strength/Washer/Friction doğrulaması) bu bulgulardan etkilenmeden başlayabilir.

