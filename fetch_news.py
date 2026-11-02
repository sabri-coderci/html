#!/usr/bin/env python3
"""Google News RSS'ten kategori bazlı başlıkları çekip haberler.json üretir."""
import json, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

KATEGORILER = {
    "Gündem": "Türkiye gündem", "Ekonomi": "ekonomi dolar borsa", "Teknoloji": "teknoloji yapay zeka",
    "Sağlık": "sağlık", "Yaşam": "yaşam", "Spor": "spor", "Magazin": "magazin", "Bilim": "bilim uzay",
    "Otomobil": "otomobil", "Eğitim": "eğitim", "Yemek": "yemek tarifi", "Seyahat": "seyahat tatil", "Oyun": "oyun e-spor",
}
out = []
for kat, sorgu in KATEGORILER.items():
    url = "https://news.google.com/rss/search?q=%s&hl=tr&gl=TR&ceid=TR:tr" % urllib.parse.quote(sorgu + " when:1d")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            kok = ET.fromstring(r.read())
    except Exception as e:
        print("Atlandı:", kat, e); continue
    for it in kok.iter("item"):
        baslik = it.findtext("title", "")
        kaynak = it.findtext("source", "")
        if kaynak and baslik.endswith(" - " + kaynak):
            baslik = baslik[: -len(kaynak) - 3]
        try:
            tarih = parsedate_to_datetime(it.findtext("pubDate")).isoformat()
        except Exception:
            continue
        out.append({"baslik": baslik, "kategori": kat, "link": it.findtext("link", ""), "kaynak": kaynak, "tarih": tarih})
        if sum(1 for o in out if o["kategori"] == kat) >= 40:
            break
if out:
    with open("haberler.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(len(out), "başlık yazıldı")
