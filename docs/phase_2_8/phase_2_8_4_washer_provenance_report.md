# Faz 2.8.4 - Washer Library Provenance & Verification Readiness

Bu rapor 223 `washer_library.json` kaydinin kanit durumunu izlenebilir bicimde kaydeder. Hicbir geometrik dogruluk iddiasi tasimaz ve bu raporu uretmek icin `washer_library.json` icindeki hicbir alan degistirilmedi.

## Kapsam ve sinirlamalar

- Bu faz, birincil ISO/DIN standardina dogrudan erisim icermiyor; yalnizca Google Drive'da incelenen ikincil, dogrulanmamis bir katalog (XLSX) ve kayitlarin kendi ic provenance alanlariyla (`confidence`, `validation_status`, `approval_status`, `metadata.estimated_fields`, `notes`) karsilastirma yapildi.
- `action_needed` kategorisi kesin bir geometrik hata iddiasi degildir; yalnizca inceleme onceligini isaret eder.

## Kategori toplamlari

| Kategori | Kayit |
|---|---:|
| `standard_verified` | 0 |
| `secondary_source_only` | 8 |
| `generated_from_unverified_source` | 0 |
| `no_external_evidence` | 139 |
| `action_needed` | 76 |
| **Toplam** | **223** |

## Reason-code dagilimi (yalnizca action_needed)

| Reason code | Kayit |
|---|---:|
| `estimated_value_diverges_from_secondary_source` | 10 |
| `standard_identity_requires_review` | 5 |
| `confidence_metadata_contradiction` | 27 |
| `high_internal_confidence_lacks_external_evidence` | 34 |

## Standart bazli dagilim

| Standart | `standard_verified` | `secondary_source_only` | `generated_from_unverified_source` | `no_external_evidence` | `action_needed` | Toplam |
|---|---|---|---|---|---|---|
| DIN 125 | 0 | 0 | 0 | 27 | 0 | 27 |
| DIN 127 B | 0 | 0 | 0 | 0 | 34 | 34 |
| DIN 9021 | 0 | 0 | 0 | 27 | 0 | 27 |
| ISO 7089 | 0 | 8 | 0 | 18 | 1 | 27 |
| ISO 7090 | 0 | 0 | 0 | 18 | 9 | 27 |
| ISO 7091 | 0 | 0 | 0 | 27 | 0 | 27 |
| ISO 7093 | 0 | 0 | 0 | 22 | 5 | 27 |
| ISO 8738 | 0 | 0 | 0 | 0 | 27 | 27 |

## XLSX kaynagi durumu

`Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx` (Google Drive, `TorqPro_17` klasoru), `Pul_Geometri` sayfasi -- yalnizca ISO 7089/7090/7093-1 icin 23 kayit. Bu dosyanin kendi `Kaynaklar` sayfasindaki SRC-005 girisi, ilgili ISO standartlarini **'Satin alinacak'** (henuz satin alinmamis/erisilmemis) olarak isaretliyor. Bu nedenle bu kaynakla eslesme `secondary_source_only` kategorisine girer, `standard_verified` olusturmaz.

## ISO 7093 / ISO 7093-1 kimlik belirsizligi

Backend `source_standard` alani "ISO 7093" (ek yok); XLSX sayfasi "ISO 7093-1" olarak etiketliyor. Bu iki etiketin ayni washer ailesini/parca revizyonunu temsil edip etmedigi bu oturumda dogrulanamadi. Ilgili 5 kayit `standard_identity_requires_review` gerekcesiyle `action_needed` olarak isaretlendi; karsilastirma sonucu sayisal dogruluk iddiasi olarak kullanilmadi.

## ISO 8738 confidence/metadata celiskisi

27 ISO 8738 kaydinin tamami `confidence=4` tasiyor, ancak ayni kayitlarin `validation_status="reference_only"`, `approval_status="pending"` ve `notes` alani ratio-estimate oldugunu beyan ediyor. Bu, confidence etiketiyle ic metadata arasinda bir kanit bosluğu -- geometri hatasi iddiasi degil.

## DIN 127 B harici kanit bosluğu

34 DIN 127 B kaydi diger tum gruplardan farkli olarak `validation_status="validated"`, `approval_status="approved"` ve bos `estimated_fields` tasiyor -- ama incelenen Drive materyallerinde bu iddiayi dogrulayacak hicbir harici kaynak bulunamadi. `high_internal_confidence_lacks_external_evidence` gerekcesiyle `action_needed` isaretlendi; ne geometri hatasi ne de confidence dusurulmesi iddia edilmiyor.

## Designation bazli action_needed tablosu

| Kayit | Standart | Designation | Reason code |
|---|---|---|---|
| WASH-DIN127B-M10 | DIN 127 B | M10 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M100 | DIN 127 B | M100 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M12 | DIN 127 B | M12 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M14 | DIN 127 B | M14 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M16 | DIN 127 B | M16 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M18 | DIN 127 B | M18 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M2 | DIN 127 B | M2 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M2.2 | DIN 127 B | M2.2 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M2.5 | DIN 127 B | M2.5 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M20 | DIN 127 B | M20 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M22 | DIN 127 B | M22 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M24 | DIN 127 B | M24 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M27 | DIN 127 B | M27 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M3 | DIN 127 B | M3 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M3.5 | DIN 127 B | M3.5 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M30 | DIN 127 B | M30 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M36 | DIN 127 B | M36 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M39 | DIN 127 B | M39 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M4 | DIN 127 B | M4 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M42 | DIN 127 B | M42 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M45 | DIN 127 B | M45 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M48 | DIN 127 B | M48 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M5 | DIN 127 B | M5 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M52 | DIN 127 B | M52 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M56 | DIN 127 B | M56 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M6 | DIN 127 B | M6 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M60 | DIN 127 B | M60 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M64 | DIN 127 B | M64 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M68 | DIN 127 B | M68 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M7 | DIN 127 B | M7 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M72 | DIN 127 B | M72 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M8 | DIN 127 B | M8 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M80 | DIN 127 B | M80 | `high_internal_confidence_lacks_external_evidence` |
| WASH-DIN127B-M90 | DIN 127 B | M90 | `high_internal_confidence_lacks_external_evidence` |
| WASH-ISO7089-M14 | ISO 7089 | M14 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M10 | ISO 7090 | M10 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M12 | ISO 7090 | M12 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M14 | ISO 7090 | M14 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M16 | ISO 7090 | M16 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M20 | ISO 7090 | M20 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M24 | ISO 7090 | M24 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M5 | ISO 7090 | M5 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M6 | ISO 7090 | M6 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7090-M8 | ISO 7090 | M8 | `estimated_value_diverges_from_secondary_source` |
| WASH-ISO7093-M10 | ISO 7093 | M10 | `standard_identity_requires_review` |
| WASH-ISO7093-M12 | ISO 7093 | M12 | `standard_identity_requires_review` |
| WASH-ISO7093-M16 | ISO 7093 | M16 | `standard_identity_requires_review` |
| WASH-ISO7093-M6 | ISO 7093 | M6 | `standard_identity_requires_review` |
| WASH-ISO7093-M8 | ISO 7093 | M8 | `standard_identity_requires_review` |
| WASH-ISO8738-M10 | ISO 8738 | M10 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M12 | ISO 8738 | M12 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M14 | ISO 8738 | M14 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M16 | ISO 8738 | M16 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M18 | ISO 8738 | M18 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M20 | ISO 8738 | M20 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M22 | ISO 8738 | M22 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M24 | ISO 8738 | M24 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M27 | ISO 8738 | M27 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M3 | ISO 8738 | M3 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M3.5 | ISO 8738 | M3.5 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M30 | ISO 8738 | M30 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M33 | ISO 8738 | M33 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M36 | ISO 8738 | M36 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M39 | ISO 8738 | M39 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M4 | ISO 8738 | M4 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M42 | ISO 8738 | M42 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M45 | ISO 8738 | M45 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M48 | ISO 8738 | M48 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M5 | ISO 8738 | M5 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M52 | ISO 8738 | M52 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M56 | ISO 8738 | M56 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M6 | ISO 8738 | M6 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M60 | ISO 8738 | M60 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M64 | ISO 8738 | M64 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M7 | ISO 8738 | M7 | `confidence_metadata_contradiction` |
| WASH-ISO8738-M8 | ISO 8738 | M8 | `confidence_metadata_contradiction` |

## Degismeyen davranis

Bu raporu uretmek icin `washer_library.json` icindeki hicbir geometrik deger, confidence, validation_status veya baska bir alan degistirilmedi. Bu arac `--apply` parametresi icermiyor.

## Gelecekteki dogrulama mimarisi onerisi (future architecture)

Ileride lisansli/satin alinmis birincil ISO/DIN standardi saglandiginda, mevcut checksum/population mimarisine dokunmadan eklenebilecek, salt-okunur bir karsilastirma katmani onerilir. Bu faz kapsaminda **kod olarak eklenmemistir** -- yalnizca tasarim burada belgelenmektedir:

- Girdi: birincil standarttan elle/OCR ile girilen `ExternalSourceRecord` listesi (standart no, designation, alan adi, dogrulanmis deger, kaynak dokuman, sayfa/madde, erisim tarihi).
- Islev: `washer_library.json` ile alan bazli karsilastirma; standart bazinda parametrik tolerans (2.8.2'deki sabit ±0.0005 mm kuralinin bu fazda reddedildigi ilkesiyle tutarli).
- Cikti: salt-okunur bir fark raporu; hicbir kosulda `washer_library.json` yazmaz.
- Bu mimari, saglandiginda ayri bir fazda, tam test kapsamiyla birlikte gercek bir modul olarak eklenmelidir -- bu fazda olu kod/iskelet birakilmadi.
