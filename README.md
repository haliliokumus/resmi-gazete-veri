# resmi-gazete-veri

Resmî Gazete'nin günlük içindekiler listesi (yalnızca Yürütme ve İdare Bölümü ile Yargı Bölümü; başlık ve resmî metne bağlantı).

GitHub Actions her gün otomatik çalışır (`.github/workflows/gunluk.yml`), sonucu `veri/` klasörüne yazar:

- `veri/son.json`: en son sayı
- `veri/arsiv.json`: son 30 sayının listesi
- `veri/YYYY/YYYY-MM-DD.json`: günlük kayıtlar

Kaynak: https://www.resmigazete.gov.tr
