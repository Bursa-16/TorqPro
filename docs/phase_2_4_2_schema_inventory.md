# Faz 2.4.2A — Schema Inventory: `extra="allow"` altında modellenmemiş alanlar

**Kapsam notu:** Bu doküman yalnızca bir envanterdir. `backend/library/models.py`
içindeki hiçbir Pydantic modeli bu dokümanla birlikte değiştirilmedi.
`LibraryRecordBase.model_config`'teki `extra="allow"` bu fazda **dokunulmadan**
kalıyor. Amaç, gelecekteki olası bir `extra="forbid"` geçişi öncesinde hangi
işin yapılması gerektiğini somut verilerle ortaya koymak.

**Üretim yöntemi:** `backend.library.population.load_population_records()` ile
her domain'in canlı `data/*.json` dosyası okunup, o domain'in
`backend.library.models.get_record_model()` ile eşleşen Pydantic modelinin
`model_fields` kümesiyle karşılaştırıldı. Aradaki fark (kayıtta var, modelde
yok) "modellenmemiş alan" olarak sayıldı. `checksum` ve `metadata` gibi
`LibraryRecordBase`'de zaten tanımlı alanlar bu sayıma dahil değildir.

**Toplam:** 10 domain'den 6'sında modellenmemiş alan var; toplam
**413 kayıt** en az bir modellenmemiş alan taşıyor (176 bolt + 211 nut + 8
material + 10 coating + 8 lubrication). `washer library`, `thread library`,
`strength class library`, `compatibility library`, `joint hardware library`
(kayıtsız) ve `oem library` (kayıtsız) şu an **tam modellenmiş** durumda —
`extra="forbid"` geçişi bu dördü için ek iş gerektirmiyor.

---

## 1. `bolt library` — 176/176 kayıt etkileniyor, 17 modellenmemiş alan

`BoltRecord` şu an 42 alan modelliyor; aşağıdaki 17 alan yalnızca
`extra="allow"` sayesinde geçiyor. Bunların tamamı **Faz 2.4.1 popülasyonunda
eklenmiş, gerçek geometrik/mühendislik verisi** — açıklayıcı metadata değil.

| Alan | Kayıt sayısı | Görülen tipler | Örnek değerler | Önerilen Pydantic tipi | Zorunlu/Optional |
|---|---|---|---|---|---|
| `diameter_mm` | 176 | int×174, float×2 | `3`, `3.5` | `float` (int'ler otomatik yükseltilir; **tam strict olursa int reddedilir** — bkz. §6) | zorunlu |
| `pitch_coarse_mm` | 176 | float×176 | `0.5`, `0.6` | `float` | zorunlu |
| `pitch_fine_mm` | 176 | float×176 | `0.45`, `0.5` | `float` | zorunlu |
| `stress_area_mm2` | 176 | float×176 | `5.031`, `6.775` | `float` | zorunlu |
| `minor_diameter_mm` | 176 | float×176 | `2.4588` | `float` | zorunlu |
| `pitch_diameter_mm` | 176 | float×176 | `2.6753` | `float` | zorunlu |
| `head_across_flats_mm` | 176 | float×41, int×123, None×12 | `5.5`, `6`, `None` | `float \| None` | **optional** |
| `head_across_corners_mm` | 176 | float×164, None×12 | `6.35`, `None` | `float \| None` | optional |
| `head_height_mm` | 176 | float×164, None×12 | `1.91`, `None` | `float \| None` | optional |
| `socket_size_mm` | 176 | None×126, float×48, int×2 | `None`, `1.8` | `float \| None` | optional (çoğunlukla None — hex-head ailelerde anlamsız) |
| `washer_face_diameter_mm` | 176 | float×164, None×12 | `6.15`, `None` | `float \| None` | optional |
| `bearing_diameter_mm` | 176 | float×83, int×81, None×12 | `5.5`, `6`, `None` | `float \| None` | optional |
| `recommended_hole_mm` | 176 | float×176 | `4.0` | `float` | zorunlu |
| `clearance_hole_medium_mm` | 176 | float×176 | `4.1` | `float` | zorunlu |
| `tap_drill_mm` | 176 | float×176 | `2.5` | `float` | zorunlu |
| `thread_engagement_mm` | 176 | float×176 | `3.0` | `float` | zorunlu |
| `weight_kg_per_100` | 176 | float×176 | `0.033` | `float` | zorunlu |

**İsim varyasyonu / dikkat:** `BoltRecord` zaten modellenmiş `length_mm` alanına
sahip; JSON'daki `diameter_mm` bu değil (çap, uzunluk değil) — çakışma yok, yeni
bağımsız alan.

---

## 2. `nut library` — 211/211 kayıt etkileniyor, 5 modellenmemiş alan

| Alan | Kayıt sayısı | Görülen tipler | Örnek değerler | Önerilen Pydantic tipi | Zorunlu/Optional |
|---|---|---|---|---|---|
| `bearing_face` | 211 | str×211 | `"Flat, chamfered"` | `str` | zorunlu |
| `flange` | 211 | bool×211 | `False` | `bool` | zorunlu |
| `width_across_flats_mm` | 211 | float×81, int×130 | `5.5`, `6` | `float` | zorunlu |
| `locking_type` | 211 | str×211 | `"None"` (string, `null` değil) | `str` | zorunlu |
| `strength_compatibility` | 211 | list×211 | `["4.6","4.8",...]` | `List[str]` | zorunlu |

**İsim varyasyonu / dikkat:** `NutRecord` zaten `width_across_corners_mm` ve
`bearing_surface_diameter_mm` modelliyor. `width_across_flats_mm` bunlardan
**farklı, bağımsız bir geometrik ölçü** (flats vs. corners) — isim benzerliği
kafa karıştırabilir ama çakışma/typo değil. `locking_type` değeri string
`"None"` (Python `None`/JSON `null` değil) — modelleme sırasında bu ayrıma
dikkat edilmeli, aksi halde `"None"` string'i yanlışlıkla boş/null gibi
yorumlanabilir.

---

## 3. `material library` — 8/8 kayıt etkileniyor, 5 modellenmemiş alan (2'si muhtemel duplike)

| Alan | Kayıt sayısı | Görülen tipler | Örnek değerler | Önerilen Pydantic tipi | Zorunlu/Optional |
|---|---|---|---|---|---|
| `density_kg_mm3` | 8 | float×8 | `7.85e-06` | `float` | zorunlu |
| `poisson_ratio` | 8 | float×8 | `0.3` | `float` | zorunlu |
| `thermal_expansion_per_k` | 8 | float×8 | `1.2e-05` | `float` | zorunlu |
| `ultimate_mpa` | 8 | int×8 | `500`, `1100` | **bkz. not aşağıda** | — |
| `yield_mpa` | 8 | int×8 | `350`, `900` | **bkz. not aşağıda** | — |

**Kritik bulgu — muhtemel duplike alan:** `MaterialRecord` zaten `rm_mpa`
(ultimate tensile) ve `rp02_mpa` (yield/proof) alanlarını modelliyor. 8
kaydın **tamamında** `ultimate_mpa == rm_mpa` ve `yield_mpa == rp02_mpa`
birebir aynı sayısal değere sahip (örn. `MAT-STEEL`: `rm_mpa=500,
ultimate_mpa=500` / `rp02_mpa=350, yield_mpa=350`). Bu, yeni model alanı
eklenmesi gereken bir durum değil — muhtemelen eski/legacy isimlendirmenin
veri dosyasında hâlâ durmasından kaynaklanıyor. **Öneri:** `extra="forbid"`
öncesi bu iki alanın veri dosyasından kaldırılması (tek doğruluk kaynağı
`rm_mpa`/`rp02_mpa` kalması) değerlendirilmeli — yeni alan modellemesi değil,
veri temizliği konusu.

---

## 4. `coating library` — 10/10 kayıt etkileniyor, 3 modellenmemiş alan

| Alan | Kayıt sayısı | Görülen tipler | Örnek değerler | Önerilen Pydantic tipi | Zorunlu/Optional |
|---|---|---|---|---|---|
| `corrosion_class` | 10 | str×10 | `"Moderate (240-720h salt spray typ.)"` | `str` | zorunlu |
| `remark` | 10 | str×10 | `"Electrolytic zinc, ISO 4042"` | `str` | optional (serbest metin) |
| `temperature_range_c` | 10 | str×10 | `"-40..300"` | **kasıtlı string — bkz. not** | zorunlu |

**Kasıtlı string/range alanı:** `temperature_range_c` tüm 10 kayıtta
`"<min>..<max>"` formatında bir **aralık ifadesi** — sayısal bir alan değil,
`float`'a çevrilmemeli. `extra="forbid"` geçişinde bu alan ya `str` olarak
aynen modellenmeli, ya da (tercih edilirse) parse edilip
`temperature_min_c: float` / `temperature_max_c: float` ikilisine
bölünmeli — ama bu bir **format kararı**, mevcut alan adı yanıltıcı
(`_c` soneki tek bir sayı çağrıştırıyor, aslında bir aralık).

---

## 5. `lubrication library` — 8/8 kayıt etkileniyor, 1 modellenmemiş alan

| Alan | Kayıt sayısı | Görülen tipler | Örnek değerler | Önerilen Pydantic tipi | Zorunlu/Optional |
|---|---|---|---|---|---|
| `oem_compatibility` | 8 | list×8 | `["FIAT","VW","Ford","GM","Toyota"]` | `List[str]` | zorunlu |

---

## 6. Tam modellenmiş domain'ler (ek iş gerekmiyor)

| Domain | Kayıt sayısı | Modellenmemiş alan |
|---|---|---|
| `washer library` | 223 | 0 |
| `thread library` | 134 | 0 |
| `strength class library` | 15 | 0 |
| `compatibility library` | 9 | 0 |
| `joint hardware library` | 0 (kayıtsız, Faz 2.4.1C shell) | 0 |
| `oem library` | 0 (adapter-only, hiç kayıt tutmuyor) | — |

---

## 7. `extra="forbid"` geçişinden önce tamamlanması gereken model listesi

Öncelik sırasıyla (etkilenen kayıt sayısına göre):

1. **`BoltRecord`** (176 kayıt, 17 alan) — en büyük iş kalemi. Ayrıca tek
   domain: `diameter_mm`'in `int`/`float` karışık geldiği, tam strict modda
   ek bir coercion/validator kararı gerektiren alan (§8'e bakınız).
2. **`NutRecord`** (211 kayıt, 5 alan) — `locking_type` alanındaki string
   `"None"` ayrımına dikkat.
3. **`MaterialRecord`** (8 kayıt, 5 alan → gerçekte 3 yeni alan +
   2 duplike/temizlik kararı).
4. **`CoatingRecord`** (10 kayıt, 3 alan) — `temperature_range_c` format
   kararı önce netleşmeli.
5. **`LubricationRecord`** (8 kayıt, 1 alan) — düşük risk, doğrudan
   eklenebilir.

`WasherRecord`, `ThreadRecord`, `StrengthClassRecord`, `CompatibilityRecord`,
`JointHardwareRecord`, `OEMRecord` listede yok — zaten tam modellenmiş.

---

## 8. `extra="forbid"` + strict numeric tipler için ayrı bir uyarı

Bu envanterin ötesinde, olası bir strict-mode geçişi için önemli bir teknik
not: yukarıdaki taramada **12 domain-alan kombinasyonunda** aynı alan
kayıtlar arasında hem `int` hem `float` olarak saklanıyor (örn. bolt
`diameter_mm`: 174 kayıt `int`, 2 kayıt `float`; `head_across_flats_mm`: 41
`float` + 123 `int`; nut `width_across_flats_mm`: 81 `float` + 130 `int`).
Pydantic v2'de saf `StrictFloat`, `int` girişini **kabul etmez** (yalnızca
`bool` dışlanmış `float` tipini kabul eder) — bu alanlara doğrudan
`StrictFloat` uygulanırsa, veri dosyasında hâlâ `int` olarak yazılmış
yüzlerce mevcut kayıt validation'da başarısız olur. Bu, dokümanın 5.
maddesindeki "geçerli mevcut veriler bozulmamalıdır" şartıyla doğrudan
çelişir. Strict geçişi tasarlanırken ya (a) bu alanlar için `int`'i de kabul
eden özel bir `Union[StrictInt, StrictFloat]` / custom validator kullanılmalı,
ya da (b) geçiş öncesi veri dosyalarında bu alanların tamamı `float`'a
normalize edilmeli (ör. `3` → `3.0`). Bu doküman bir karar önermiyor, sadece
riski işaretliyor.

---

## 9. Sonuç

- Toplam etkilenen kayıt: **413** (176 + 211 + 8 + 10 + 8).
- Toplam yeni "gerçek" alan (duplike/format-kararı gerektirenler hariç): **~28**
  (bolt 17 + nut 5 + material 3 + coating 2 [`corrosion_class`, `remark`] +
  lubrication 1).
- 2 alan (`ultimate_mpa`, `yield_mpa`) muhtemel duplike — model değil, veri
  temizliği kararı gerektiriyor.
- 1 alan (`temperature_range_c`) format kararı gerektiriyor (string aralık mı
  kalsın, iki sayıya mı bölünsün).
- 12+ alan-domain kombinasyonunda int/float karışık veri var — saf strict tip
  geçişi öncesi ayrıca ele alınmalı.

Bu doküman **yalnızca envanterdir**; hiçbir model bu fazda değiştirilmedi.
