#!/usr/bin/env python3
"""Resmî Gazete günlük içindekiler listesini çeker.

Yalnızca YÜRÜTME VE İDARE BÖLÜMÜ ile YARGI BÖLÜMÜ alınır (İlan Bölümü alınmaz).
Metinler kopyalanmaz; yalnızca başlık ve resmî metne giden bağlantı tutulur.

Çıktılar:
  veri/son.json            -> en son sayı
  veri/YYYY/YYYY-MM-DD.json -> günlük arşiv
  veri/arsiv.json          -> son 30 sayının tarih listesi

Kullanım: python rg.py [YYYY-MM-DD]
"""
import json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

TR = timezone(timedelta(hours=3))
KOK = "https://www.resmigazete.gov.tr"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

ALINACAK = {"YÜRÜTME VE İDARE BÖLÜMÜ": "Yürütme ve İdare Bölümü",
            "YARGI BÖLÜMÜ": "Yargı Bölümü"}
DURDUR = ("İLAN BÖLÜMÜ",)
ATLA = ("ÖNCEKİ", "SONRAKİ", "PDF", "ARŞİV", "TÜMÜ")


def ust(s):
    s = s.replace("i", "İ").replace("ı", "I").upper()
    return s.replace("Â", "A").replace("Î", "İ").replace("Û", "U")


def kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def baslikla(s):
    """Türkçe kurallara göre 'YÖNETMELİKLER' -> 'Yönetmelikler'."""
    kel = []
    for i, w in enumerate(kucuk(s).split()):
        if i and w in ("ve", "ile", "ilişkin", "dair", "ait"):
            kel.append(w)
        else:
            kel.append(ust(w[:1]) + w[1:])
    return " ".join(kel)


def temiz(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return re.sub(r"^[\-–—―−•·\s]+", "", s).strip()


class Akis(HTMLParser):
    """Sayfayı belge sırasına göre ('metin', s) ve ('link', href, s) olaylarına çevirir."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.olaylar, self.href, self.atext, self.buf, self.gizli = [], None, [], [], 0

    def _bosalt(self):
        t = temiz("".join(self.buf))
        if t:
            self.olaylar.append(("metin", t))
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self.gizli += 1
        elif tag == "a":
            self._bosalt()
            self.href, self.atext = dict(attrs).get("href"), []
        elif tag in ("div", "p", "br", "li", "tr", "td", "h1", "h2", "h3", "h4", "h5", "span", "b", "strong"):
            if self.href is None:
                self._bosalt()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head"):
            self.gizli = max(0, self.gizli - 1)
        elif tag == "a" and self.href is not None:
            t = temiz("".join(self.atext))
            if t:
                self.olaylar.append(("link", self.href, t))
            self.href, self.atext = None, []
        elif self.href is None and tag in ("div", "p", "li", "tr", "td", "h1", "h2", "h3", "h4", "h5", "span", "b", "strong"):
            self._bosalt()

    def handle_data(self, d):
        if self.gizli:
            return
        (self.atext if self.href is not None else self.buf).append(d)

    def close(self):
        super().close()
        self._bosalt()


def indir(url):
    son = None
    for deneme in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                ham = r.read()
            for kod in ("utf-8", "windows-1254", "iso-8859-9"):
                try:
                    return ham.decode(kod)
                except UnicodeDecodeError:
                    pass
            return ham.decode("utf-8", "replace")
        except Exception as e:  # ağ hatası: biraz bekleyip yeniden dene
            son = e
            time.sleep(5 * (deneme + 1))
    raise RuntimeError(f"{url} indirilemedi: {son}")


def ayristir(html, taban):
    p = Akis()
    p.feed(html)
    p.close()
    if os.environ.get("RG_DEBUG"):
        with open("veri/_debug.txt", "a", encoding="utf-8") as f:
            f.write(taban + "\n" + repr(p.olaylar[:40]) + "\n" + html[:3000] + "\n\n")
    bolumler, bolum, grup, sayi = [], None, None, None
    for o in p.olaylar:
        if o[0] == "metin":
            t = o[1]
            U = ust(t)
            if any(U.startswith(d) for d in DURDUR):
                if bolum:
                    bolum = None
                if bolumler:
                    break
                continue
            hit = next((ad for k, ad in ALINACAK.items() if U.startswith(k)), None)
            if hit:
                bolum = next((b for b in bolumler if b["ad"] == hit), None)
                if not bolum:
                    bolum = {"ad": hit, "gruplar": []}
                    bolumler.append(bolum)
                grup = None
                continue
            # Alt başlık: linksiz, tamamı büyük harf, kısa satır (YÖNETMELİKLER, KURUL KARARI ...)
            if bolum and len(t) <= 80 and t == ust(t) and re.search(r"[A-ZÇĞİÖŞÜ]{3}", t):
                grup = {"ad": baslikla(t), "maddeler": []}
                bolum["gruplar"].append(grup)
        else:
            _, href, t = o
            if not bolum or not href or ust(t) in ATLA or href.startswith(("#", "javascript")):
                continue
            url = urljoin(taban, href)
            if "resmigazete.gov.tr" not in url:
                continue
            if grup is None:
                grup = {"ad": "Diğer", "maddeler": []}
                bolum["gruplar"].append(grup)
            if not any(m["url"] == url and m["baslik"] == t for m in grup["maddeler"]):
                grup["maddeler"].append({"baslik": t, "url": url})
    duz = " ".join(o[-1] for o in p.olaylar)
    m = re.search(r"Say[ıiIİ]\s*:?\s*(\d{2}[.\s]?\d{3})\b", duz)
    if m:
        sayi = int(re.sub(r"\D", "", m.group(1)))
    for b in bolumler:
        b["gruplar"] = [g for g in b["gruplar"] if g["maddeler"]]
    bolumler = [b for b in bolumler if b["gruplar"]]
    return bolumler, sayi


def cek(gun):
    ymd = gun.strftime("%Y%m%d")
    adaylar = [
        f"{KOK}/eskiler/{gun:%Y}/{gun:%m}/{ymd}.htm",
        f"{KOK}/fihrist?tarih={gun:%Y-%m-%d}",
    ]
    if gun == datetime.now(TR).date():
        adaylar.append(KOK + "/")
    hatalar = []
    for url in adaylar:
        try:
            bolumler, sayi = ayristir(indir(url), url)
        except Exception as e:
            hatalar.append(str(e))
            continue
        if bolumler:
            return {
                "tarih": gun.isoformat(),
                "tarih_metin": f"{gun.day} {AYLAR[gun.month - 1]} {gun.year}",
                "sayi": sayi,
                "kaynak": url,
                "bolumler": bolumler,
                "guncellendi": datetime.now(TR).isoformat(timespec="minutes"),
            }
        hatalar.append(f"{url}: içerik bulunamadı")
    raise RuntimeError("; ".join(hatalar))


def yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    gun = datetime.strptime(sys.argv[1], "%Y-%m-%d").date() if len(sys.argv) > 1 else datetime.now(TR).date()
    veri = cek(gun)
    yaz(f"veri/{gun:%Y}/{gun.isoformat()}.json", veri)
    try:
        with open("veri/son.json", encoding="utf-8") as f:
            onceki = json.load(f)["tarih"]
    except Exception:
        onceki = ""
    if gun.isoformat() >= onceki:
        yaz("veri/son.json", veri)
    try:
        with open("veri/arsiv.json", encoding="utf-8") as f:
            arsiv = json.load(f)
    except Exception:
        arsiv = []
    arsiv = [a for a in arsiv if a["tarih"] != veri["tarih"]]
    arsiv.append({"tarih": veri["tarih"], "tarih_metin": veri["tarih_metin"], "sayi": veri["sayi"]})
    arsiv = sorted(arsiv, key=lambda a: a["tarih"], reverse=True)[:30]
    yaz("veri/arsiv.json", arsiv)
    n = sum(len(g["maddeler"]) for b in veri["bolumler"] for g in b["gruplar"])
    print(f"{veri['tarih']} sayı {veri['sayi']}: {n} başlık ({veri['kaynak']})")


if __name__ == "__main__":
    main()
