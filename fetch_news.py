import json, os, html, datetime, subprocess, urllib.request, urllib.parse
import xml.etree.ElementTree as ET

SITE = "https://nearadin.net"
KONULAR = ["Türkiye", "Ekonomi", "Teknoloji", "Spor"]
HARIC = {"404.html"}
HARIC_KLASOR = {".git", ".github", "veri", "node_modules"}


def cek(konu):
    q = urllib.parse.quote(konu)
    url = f"https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"
    with urllib.request.urlopen(url, timeout=30) as r:
        kok = ET.fromstring(r.read())
    out = []
    for it in kok.iter("item"):
        out.append({
            "baslik": it.findtext("title", ""),
            "link": it.findtext("link", ""),
            "tarih": it.findtext("pubDate", ""),
            "kaynak": it.findtext("source", ""),
        })
    return out[:15]


def son_degisiklik(yol):
    try:
        t = subprocess.check_output(
            ["git", "log", "-1", "--format=%cs", "--", yol],
            text=True).strip()
        if t:
            return t
    except Exception:
        pass
    return datetime.date.today().isoformat()


def sitemap_uret():
    urller = []
    for kok, klasorler, dosyalar in os.walk("."):
        klasorler[:] = [d for d in klasorler if d not in HARIC_KLASOR]
        for ad in dosyalar:
            if not ad.endswith(".html") or ad in HARIC:
                continue
            yol = os.path.relpath(os.path.join(kok, ad), ".").replace(os.sep, "/")
            if yol == "index.html":
                adres, oncelik, sik = SITE + "/", "1.0", "daily"
            elif yol == "haberler.html":
                adres, oncelik, sik = f"{SITE}/{yol}", "0.9", "hourly"
            elif yol.startswith("detaylar/"):
                adres, oncelik, sik = f"{SITE}/{yol}", "0.7", "weekly"
            else:
                adres, oncelik, sik = f"{SITE}/{yol}", "0.5", "monthly"
            urller.append((adres, son_degisiklik(yol), sik, oncelik))
    urller.sort(key=lambda u: (-float(u[3]), u[0]))
    satirlar = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for adres, lastmod, sik, oncelik in urller[:50000]:
        satirlar.append(
            f"<url><loc>{html.escape(adres)}</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>{sik}</changefreq><priority>{oncelik}</priority></url>")
    satirlar.append("</urlset>")
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar))
    print("Sitemap:", len(urller), "adres")


def main():
    veri = {"guncelleme": datetime.datetime.utcnow().isoformat() + "Z", "konular": {}}
    for k in KONULAR:
        try:
            veri["konular"][k] = cek(k)
        except Exception as e:
            print("Hata:", k, e)
    os.makedirs("veri", exist_ok=True)
    with open("veri/haberler.json", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)

    bolum = ""
    for k, liste in veri["konular"].items():
        bolum += f"<h2>{html.escape(k)}</h2><ul>"
        for h in liste:
            bolum += (f'<li><a href="{html.escape(h["link"])}" rel="nofollow noopener">'
                      f'{html.escape(h["baslik"])}</a></li>')
        bolum += "</ul>"
    sayfa = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>Güncel Haberler | nearadin.net</title>
<meta name="description" content="Türkiye, ekonomi, teknoloji ve spor haberleri, saatlik güncellenir.">
<link rel="canonical" href="{SITE}/haberler.html">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body><h1>Güncel Haberler</h1>{bolum}</body></html>"""
    with open("haberler.html", "w", encoding="utf-8") as f:
        f.write(sayfa)

    sitemap_uret()


main()
