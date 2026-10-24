import json, os, html, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET

SITE = "https://nearadin.net"
KONULAR = ["Türkiye", "Ekonomi", "Teknoloji", "Spor", "Van"]

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
<meta name="description" content="Türkiye, ekonomi, teknoloji, spor ve Van'dan saatlik güncellenen haberler.">
<link rel="canonical" href="{SITE}/haberler.html">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body><h1>Güncel Haberler</h1>{bolum}</body></html>"""
    with open("haberler.html", "w", encoding="utf-8") as f:
        f.write(sayfa)

    bugun = datetime.date.today().isoformat()
    sm = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{SITE}/</loc><lastmod>{bugun}</lastmod></url>
<url><loc>{SITE}/haberler.html</loc><lastmod>{bugun}</lastmod></url>
</urlset>"""
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sm)

main()
