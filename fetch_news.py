#!/usr/bin/env python3
"""
Nearadin.net statik sayfa üretici.

Her çalıştığında:
  1. Google News RSS'ten (kategori x şehir) için güncel haberleri çeker (önbellekli, kotalı).
  2. /ara/<kategori>/<sehir>/index.html sayfalarını, kategori ve /ara/ hub sayfalarını üretir.
  3. Ana sayfayı (/index.html), /sehir/<il>/ merkez sayfalarını üretir (tüm il ve kategoriler ana sayfadan taranabilir).
  4. sitemap.xml ve robots.txt dosyalarını yeniler.
Ana sayfaya reklam/ek kod eklemek için data/home_head_extra.html dosyası oluşturun; içeriği <head> içine eklenir.

Yalnızca Python standart kütüphanesi kullanır (pip kurulumu gerekmez).
Ortam değişkenleri:
  MAX_FETCH  Çalışma başına en fazla kaç RSS isteği atılsın (varsayılan 400)
  CACHE_TTL_H  Haber önbelleği kaç saat geçerli (varsayılan 20)
  MIN_NEWS   Bir sayfanın dizine açılması için gereken en az haber sayısı (varsayılan 3)
"""
import html
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SITE = "https://www.nearadin.net"
ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "data" / "news_cache.json"
MAX_FETCH = int(os.environ.get("MAX_FETCH", "400"))
CACHE_TTL = int(os.environ.get("CACHE_TTL_H", "20")) * 3600
MIN_NEWS = int(os.environ.get("MIN_NEWS", "3"))
NEWS_PER_PAGE = 8

CATEGORIES = [
    "Restoran", "Tesisatçı", "Elektrikçi", "Boyacı", "Kuaför", "Berber",
    "Diş Hekimi", "Eczane", "Veteriner", "Oto Servis", "Çilingir", "Nakliyat",
    "Avukat", "Kafe", "Market", "Otel", "Klima Servisi", "Halı Yıkama",
    "Güzellik Salonu", "Temizlik Şirketi","PTT","Belediye","Kaymakamlık","Valilik",
    "Noter","Playstation","Petshop","Otel","Öğretmen Evi","Polis Evi"
]
CATEGORIES = list(dict.fromkeys(CATEGORIES))  # tekrarları (ör. Otel) temizle
CITIES = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara", "Antalya",
    "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum",
    "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir",
    "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul",
    "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kırıkkale",
    "Kırklareli", "Kırşehir", "Kilis", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa",
    "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize",
    "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Şanlıurfa", "Şırnak", "Tekirdağ", "Tokat",
    "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak",
]
TOP_CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana", "Konya", "Gaziantep","Van","Diyarbakır"]

ICONS = {
    "Restoran": "🍽️", "Tesisatçı": "🔧", "Elektrikçi": "💡", "Boyacı": "🎨", "Kuaför": "💇", "Berber": "💈",
    "Diş Hekimi": "🦷", "Eczane": "💊", "Veteriner": "🐾", "Oto Servis": "🚗", "Çilingir": "🔑", "Nakliyat": "🚚",
    "Avukat": "⚖️", "Kafe": "☕", "Market": "🛒", "Otel": "🏨", "Klima Servisi": "❄️", "Halı Yıkama": "🧺",
    "Güzellik Salonu": "💅", "Temizlik Şirketi": "🧹", "PTT": "📮", "Belediye": "🏛️", "Kaymakamlık": "🏢",
    "Valilik": "🏢", "Noter": "📜", "Playstation": "🎮", "Petshop": "🐶", "Öğretmen Evi": "🎓", "Polis Evi": "🛡️",
}


def icon(cat):
    return ICONS.get(cat, "📍")


_TR = str.maketrans("çğıöşüÇĞİÖŞÜI", "cgiosucgiosui")


def slugify(text):
    text = text.translate(_TR).lower()
    return "-".join("".join(c if c.isalnum() else " " for c in text).split())


def tr_lower(text):
    return text.replace("İ", "i").replace("I", "ı").lower()


def esc(s):
    return html.escape(s, quote=True)


# --------------------------------------------------------------------------- haber çekme
def fetch_rss(cat, city):
    q = f"{cat} {city} when:30d"
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
           + "&hl=tr&gl=TR&ceid=TR:tr")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Nearadin.net bot)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                root = ET.fromstring(r.read())
            items = []
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                source = (it.findtext("source") or "").strip()
                if source and title.endswith(" - " + source):
                    title = title[: -len(source) - 3]
                link = (it.findtext("link") or "").strip()
                try:
                    date = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
                except Exception:
                    date = ""
                if title and link.startswith("http"):
                    items.append({"title": title, "link": link, "source": source, "date": date})
                if len(items) >= NEWS_PER_PAGE:
                    break
            return items
        except Exception as e:
            time.sleep(2 * (attempt + 1))
            err = e
    print(f"  ! RSS alınamadı: {cat} {city}: {err}")
    return None


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def refresh_cache(cache):
    now = time.time()
    keys = [(c, s) for c in CATEGORIES for s in CITIES]
    stale = [k for k in keys if now - cache.get("|".join(k), {}).get("t", 0) > CACHE_TTL]
    stale.sort(key=lambda k: cache.get("|".join(k), {}).get("t", 0))  # en eski önce
    batch = stale[:MAX_FETCH]
    print(f"Önbellek: {len(keys) - len(stale)} taze, {len(stale)} eski; bu turda {len(batch)} çekilecek.")

    def work(k):
        time.sleep(0.3)
        return k, fetch_rss(*k)

    with ThreadPoolExecutor(max_workers=4) as ex:
        for k, items in ex.map(work, batch):
            if items is not None:
                cache["|".join(k)] = {"t": now, "items": items}
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- şablonlar
CSS = """
:root{--p:#0056b3;--a:#c24e00;--bg:#f6f8fb;--t:#1f2933;--m:#52606d;--l:#dbe3ec}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--t);line-height:1.6}
a{color:var(--p)}:focus-visible{outline:3px solid #ff6600;outline-offset:2px}
header.top{background:#fff;border-bottom:1px solid var(--l);position:sticky;top:0;z-index:50}
.bar{max-width:1000px;margin:auto;display:flex;align-items:center;justify-content:space-between;padding:10px 15px}
.burger{width:44px;height:44px;border:1px solid var(--l);border-radius:10px;background:#fff;cursor:pointer;display:flex;flex-direction:column;justify-content:center;gap:5px;padding:0 11px}
.burger span{display:block;height:3px;background:var(--p);border-radius:2px;transition:transform .25s,opacity .25s}
.burger[aria-expanded=true] span:nth-child(1){transform:translateY(8px) rotate(45deg)}
.burger[aria-expanded=true] span:nth-child(2){opacity:0}
.burger[aria-expanded=true] span:nth-child(3){transform:translateY(-8px) rotate(-45deg)}
.bar-cta{font-weight:600;font-size:.9rem;text-decoration:none;padding:8px 14px;border-radius:99px;background:#eef5fd}
.menu{max-height:0;overflow:hidden;transition:max-height .3s;background:#fff}
.menu.open{max-height:80vh;overflow:auto;border-top:1px solid var(--l)}
.menu-in{max-width:1000px;margin:auto;padding:8px 15px 14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:4px}
.menu-in a{padding:10px 12px;border-radius:8px;text-decoration:none;font-weight:600;color:var(--t)}
.menu-in a:hover{background:#eef5fd}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}
.cat{display:flex;flex-direction:column;align-items:center;gap:6px;padding:16px 8px;border:1px solid var(--l);border-radius:14px;background:#fff;text-decoration:none;color:var(--t);font-weight:600;text-align:center;transition:transform .2s,box-shadow .2s,border-color .2s}
.cat:hover{transform:translateY(-3px);box-shadow:0 8px 20px rgba(0,86,179,.15);border-color:var(--p)}
.cat b{font-size:2rem;line-height:1}
.logo{font-size:1.8rem;font-weight:800;color:var(--p);text-decoration:none}.logo span{color:#ff6600}
main{max-width:1000px;margin:22px auto;padding:0 15px}
.crumb{font-size:.9rem;color:var(--m);margin-bottom:12px}
.card{background:#fff;border:1px solid var(--l);border-radius:12px;padding:22px;margin-bottom:20px}
h1{font-size:1.7rem;line-height:1.25;color:#17324d;margin-bottom:8px}
h2{font-size:1.25rem;color:#17324d;margin-bottom:10px}
p{max-width:72ch;margin-bottom:10px;color:#3e4c59}
.alt{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.alt a,.tags a{padding:7px 14px;border-radius:6px;background:#eef5fd;text-decoration:none;font-weight:600;font-size:.9rem}
.tags{display:flex;flex-wrap:wrap;gap:8px}.tags a{font-weight:500;border-radius:99px;border:1px solid var(--l);background:#fff}
iframe{display:block;width:100%;height:60vh;min-height:380px;border:0;border-radius:8px;margin-top:8px}
ul.news{list-style:none}ul.news li{padding:10px 0;border-top:1px solid var(--l)}
ul.news small{display:block;color:var(--m)}
footer{padding:22px 15px;text-align:center;color:#616e7c;font-size:.9rem;background:#fff;border-top:1px solid var(--l)}
footer a{margin:0 8px}
"""


def header_html():
    pop = "".join(f'<a href="/ara/{slugify(c)}/">{icon(c)} {esc(c)}</a>' for c in CATEGORIES[:8])
    return ('<header class="top"><div class="bar">'
            '<button class="burger" id="bb" type="button" aria-label="Menüyü aç/kapat" aria-expanded="false" aria-controls="nav">'
            '<span></span><span></span><span></span></button>'
            '<a class="logo" href="/" title="Nearadin.net ana sayfa">Nearadin<span>.net</span></a>'
            '<a class="bar-cta" href="/ara/">Kategoriler</a></div>'
            '<nav class="menu" id="nav" aria-label="Ana menü"><div class="menu-in">'
            '<a href="/">🏠 Ana sayfa</a><a href="/ara/">📂 Tüm kategoriler</a><a href="/sehir/">📍 Tüm şehirler</a>'
            + pop + '<a href="/#harita">🗺️ Haritada ara</a></div></nav></header>')


def head(title, desc, path, extra="", css="", top=""):
    robots = "index,follow,max-image-preview:large"
    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<meta name="robots" content="{robots}"><meta name="theme-color" content="#0056b3">
<link rel="canonical" href="{SITE}{path}">
<meta property="og:type" content="website"><meta property="og:locale" content="tr_TR"><meta property="og:site_name" content="Nearadin.net">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{SITE}{path}">
<meta property="og:image" content="{SITE}/og-image.png"><meta name="twitter:card" content="summary_large_image">
{extra}<style>{CSS}{css}</style></head><body>
{header_html()}{top}{WAUST}
<main>"""


FOOT = """</main>
<footer><nav aria-label="Alt menü"><a href="/">Ana sayfa</a><a href="/ara/">Tüm kategoriler</a><a href="/sehir/">Tüm şehirler</a></nav>
<p>&copy; 2026 Nearadin.net - Tüm hakları saklıdır.</p></footer>
<script>(function(){var b=document.getElementById('bb'),m=document.getElementById('nav');if(!b)return;
b.onclick=function(){var o=m.classList.toggle('open');b.setAttribute('aria-expanded',o)};
m.addEventListener('click',function(e){if(e.target.tagName=='A')m.classList.remove('open')})})();</script>
</body></html>
"""


def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"


def crumbs_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + p} for i, (n, p) in enumerate(items)]}


def fmt_date(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return ""


def page_path(cat, city):
    return f"/ara/{slugify(cat)}/{slugify(city)}/"


def render_page(cat, city, items, today):
    path = page_path(cat, city)
    cl = tr_lower(cat)
    title = f"{city} {cat} - Harita ve Güncel Haberler | Nearadin.net"
    desc = (f"{city} bölgesindeki {cl} işletmelerini harita üzerinde bulun, "
            f"{city} {cl} ile ilgili güncel haberleri okuyun.")
    indexable = len(items) >= MIN_NEWS
    q = urllib.parse.quote(f"{cat} {city}")
    crumbs = [("Ana sayfa", "/"), (cat, f"/ara/{slugify(cat)}/"), (city, path)]
    ld = jsonld(crumbs_ld(crumbs)) + jsonld({
        "@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": SITE + path,
        "inLanguage": "tr-TR", "dateModified": today, "about": f"{city} {cl}"})
    out = [head(title, desc, path, ld)]
    out.append(f'<p class="crumb"><a href="/">Ana sayfa</a> › <a href="/ara/{slugify(cat)}/">{esc(cat)}</a> › {esc(city)}</p>')
    out.append(f'<section class="card"><h1>{esc(city)} {esc(cat)}</h1>'
               f"<p>{esc(city)} bölgesinde {esc(cl)} arayanlar için harita, hızlı arama bağlantıları ve bölgeyle ilgili güncel haberler. "
               f"Konum, telefon, yorum ve çalışma saatleri için haritadaki işletmeye tıklayın.</p>"
               f'<div class="alt"><a href="https://www.google.com/maps/search/?api=1&amp;query={q}" target="_blank" rel="noopener nofollow">Google Haritalar\'da aç</a>'
               f'<a href="https://yandex.com.tr/harita/?text={q}" target="_blank" rel="noopener nofollow">Yandex Haritalar\'da aç</a>'
               f'<a href="/?ne={urllib.parse.quote(cat)}&amp;nerede={urllib.parse.quote(city)}">İlçe veya mahalle ara</a></div>'
               f'<iframe title="{esc(city)} {esc(cl)} haritası" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen '
               f'src="https://www.google.com/maps?q={q}&amp;hl=tr&amp;output=embed"></iframe></section>')
    if items:
        lis = "".join(
            f'<li><a href="{esc(i["link"])}" target="_blank" rel="noopener nofollow">{esc(i["title"])}</a>'
            f'<small>{esc(i["source"])}{" · " if i["source"] and i["date"] else ""}{fmt_date(i["date"])}</small></li>'
            for i in items)
        out.append(f'<section class="card"><h2>{esc(city)} {esc(cl)} ile ilgili güncel haberler</h2><ul class="news">{lis}</ul>'
                   f"<p><small>Haber başlıkları Google Haber kaynaklarından derlenir; içerikler ilgili yayıncılara aittir. Son güncelleme: {today}.</small></p></section>")
    other_cities = [c for c in TOP_CITIES if c != city]
    out.append(f'<section class="card"><h2>{esc(cat)} diğer şehirlerde</h2><div class="tags">'
               + "".join(f'<a href="{page_path(cat, c)}">{esc(c)} {esc(cat)}</a>' for c in other_cities)
               + f'<a href="/ara/{slugify(cat)}/">Tüm şehirler</a></div></section>')
    others = [c for c in CATEGORIES if c != cat][:12]
    out.append(f'<section class="card"><h2>{esc(city)} bölgesinde diğer hizmetler</h2><div class="tags">'
               + "".join(f'<a href="{page_path(c, city)}">{esc(city)} {esc(c)}</a>' for c in others)
               + f'<a href="/sehir/{slugify(city)}/">{esc(city)} tüm hizmetler</a></div></section>')
    out.append(FOOT)
    return "".join(out), indexable


def render_category(cat, today):
    path = f"/ara/{slugify(cat)}/"
    title = f"{cat} - Şehirlere Göre İşletme Rehberi | Nearadin.net"
    desc = f"Türkiye'nin 81 ilinde {tr_lower(cat)} işletmelerini harita üzerinde bulun."
    out = [head(title, desc, path, jsonld(crumbs_ld([("Ana sayfa", "/"), ("Kategoriler", "/ara/"), (cat, path)])))]
    out.append(f'<p class="crumb"><a href="/">Ana sayfa</a> › <a href="/ara/">Kategoriler</a> › {esc(cat)}</p>')
    out.append(f'<section class="card"><h1>{esc(cat)} - şehre göre seçin</h1><p>Aradığınız şehri seçerek {esc(tr_lower(cat))} işletmelerini haritada görün.</p>'
               '<div class="tags">' + "".join(f'<a href="{page_path(cat, c)}">{esc(c)}</a>' for c in CITIES)
               + "</div></section>" + FOOT)
    return "".join(out)


def render_index(today):
    path = "/ara/"
    title = "İşletme Kategorileri - Firma ve Hizmet Rehberi | Nearadin.net"
    desc = "Restoran, tesisatçı, kuaför, doktor ve daha fazlası: kategoriye ve şehre göre işletme arayın."
    out = [head(title, desc, path, jsonld(crumbs_ld([("Ana sayfa", "/"), ("Kategoriler", path)])))]
    out.append('<section class="card"><h1>İşletme kategorileri</h1><p>Bir kategori seçin, ardından şehrinizi belirleyin.</p><div class="tags">'
               + "".join(f'<a href="/ara/{slugify(c)}/">{esc(c)}</a>' for c in CATEGORIES) + "</div></section>" + FOOT)
    return "".join(out)


def latest_news(cache, city=None, limit=6):
    found, seen = [], set()
    for key, val in cache.items():
        cat, _, c = key.partition("|")
        if city and c != city:
            continue
        for it in val.get("items", []):
            if it["date"] and it["title"] not in seen:
                seen.add(it["title"])
                found.append((it["date"], it, cat, c))
    found.sort(key=lambda x: x[0], reverse=True)
    return found[:limit]


def news_list(rows):
    return "".join(
        f'<li><a href="{esc(i["link"])}" target="_blank" rel="noopener nofollow">{esc(i["title"])}</a>'
        f'<small>{esc(c)} {esc(tr_lower(cat))} · {esc(i["source"])} · {fmt_date(i["date"])}</small></li>'
        for _, i, cat, c in rows)


HOME_CSS = """
.hero{background:#0b3d75;background-image:linear-gradient(rgba(255,255,255,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.07) 1px,transparent 1px);background-size:34px 34px;color:#fff;border-radius:18px;padding:38px 20px;margin-bottom:22px;text-align:center}
.hero h1{color:#fff;font-size:2.1rem;max-width:20ch;margin:0 auto 10px}
.hero p{color:#dbe9f8;margin:0 auto 20px}
.sel{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;max-width:780px;margin:auto;background:#fff;padding:10px;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.25)}
.sel select,.sel button{height:52px;border-radius:10px;border:1px solid var(--l);font-size:1rem;padding:0 12px;background:#fff;color:var(--t)}
.sel button{background:#ff6600;border-color:#ff6600;color:#fff;font-weight:700;cursor:pointer;padding:0 28px}
.sel button:hover{background:#e55a00}
.pop{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.pop a{background:rgba(255,255,255,.16);color:#fff;border-radius:99px;padding:6px 14px;text-decoration:none;font-size:.88rem}
.pop a:hover{background:rgba(255,255,255,.3)}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.step{background:#eef5fd;border-radius:12px;padding:16px}.step b{font-size:1.6rem}
.cnt{text-align:center;padding:6px 0}
.mapf{display:flex;flex-wrap:wrap;gap:8px}
.mapf input{flex:1 1 180px;height:46px;border:1px solid var(--l);border-radius:10px;padding:0 12px;font-size:1rem}
.mapf button{height:46px;border:0;border-radius:10px;background:var(--p);color:#fff;font-weight:700;padding:0 22px;cursor:pointer}
@media(max-width:640px){.sel{grid-template-columns:1fr}.hero h1{font-size:1.55rem}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

HOME_JS = """<script>(function(){
var C=document.getElementById('sc'),S=document.getElementById('ss'),$=function(i){return document.getElementById(i)};
$('go').onclick=function(){var c=C.value,s=S.value;location.href=c&&s?'/ara/'+c+'/'+s+'/':c?'/ara/'+c+'/':s?'/sehir/'+s+'/':'/ara/'};
function show(ne,nr){var q=encodeURIComponent((ne+' '+nr).trim());if(!q)return;var f=$('mf');
f.src='https://www.google.com/maps?q='+q+'&hl=tr&output=embed';f.style.display='block'}
$('mb').onclick=function(){show($('ne').value,$('nr').value)};
var p=new URLSearchParams(location.search),ne=p.get('ne')||'',nr=p.get('nerede')||'';
if(ne||nr){$('ne').value=ne;$('nr').value=nr;show(ne,nr);$('harita').scrollIntoView()}
})();</script>
"""

WAUST = ('<div class="cnt"><script id="_waugih">var _wau = _wau || []; '
         '_wau.push(["dynamic", "ghv145c8aq", "gih", "c4302bffffff", "small"]);</script>'
         '<script async src="//waust.at/d.js"></script></div>')


def render_home(cache, today):
    title = "Nearadin.net - Türkiye'de İşletme ve Hizmet Rehberi | 81 İl, Harita ve Haberler"
    desc = ("Türkiye'nin 81 ilinde restoran, tesisatçı, kuaför, eczane ve daha fazlasını harita üzerinde bulun. "
            "İl ve kategori seçin, bölgeyle ilgili güncel haberleri okuyun.")
    ld = jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": "Nearadin.net", "url": SITE + "/",
                 "inLanguage": "tr-TR", "description": desc})
    try:
        extra_head = (ROOT / "data" / "home_head_extra.html").read_text(encoding="utf-8")
    except Exception:
        extra_head = ""
    out = [head(title, desc, "/", ld + extra_head, HOME_CSS,)]
    opt_c = "".join(f'<option value="{slugify(c)}">{icon(c)} {esc(c)}</option>' for c in CATEGORIES)
    opt_s = "".join(f'<option value="{slugify(c)}">{esc(c)}</option>' for c in CITIES)
    pop = "".join(f'<a href="/sehir/{slugify(c)}/">{esc(c)}</a>' for c in TOP_CITIES)
    out.append(
        '<section class="hero"><h1>Aradığınız işletme bir tık uzağınızda</h1>'
        '<p>İlinizi ve kategoriyi seçin; harita, yorumlar ve güncel haberler tek sayfada.</p>'
        f'<div class="sel"><select id="sc" aria-label="Kategori seçin"><option value="">Kategori seçin</option>{opt_c}</select>'
        f'<select id="ss" aria-label="İl seçin"><option value="">İl seçin</option>{opt_s}</select>'
        '<button id="go" type="button">Ara</button></div>'
        f'<div class="pop">{pop}</div></section>')
    out.append('<section class="card"><h2>Kategoriler</h2><div class="grid">'
               + "".join(f'<a class="cat" href="/ara/{slugify(c)}/"><b>{icon(c)}</b>{esc(c)}</a>' for c in CATEGORIES)
               + '</div></section>')
    news = latest_news(cache, limit=6)
    if news:
        out.append(f'<section class="card"><h2>Güncel haberler</h2><ul class="news">{news_list(news)}</ul></section>')
    out.append('<section class="card" id="iller"><h2>81 il, tek yerde</h2><p>Bir il seçin, o ildeki tüm hizmetleri görün.</p>'
               '<div class="tags">' + "".join(f'<a href="/sehir/{slugify(c)}/">{esc(c)}</a>' for c in CITIES)
               + '</div></section>')
    out.append('<section class="card"><h2>Nasıl çalışır?</h2><div class="steps">'
               '<div class="step"><b>📂</b><p><strong>Kategori seçin</strong><br>Restoran, tesisatçı, eczane ve daha fazlası.</p></div>'
               '<div class="step"><b>📍</b><p><strong>İlinizi seçin</strong><br>81 ilden birini belirleyin.</p></div>'
               '<div class="step"><b>🗺️</b><p><strong>Haritada bulun</strong><br>Konum, telefon ve çalışma saatleri için işletmeye tıklayın.</p></div>'
               '</div></section>')
    out.append('<section class="card" id="harita"><h2>İlçe veya mahalle ara</h2>'
               '<p>Daha dar bir bölge için ne aradığınızı ve nerede aradığınızı yazın.</p>'
               '<div class="mapf"><input id="ne" placeholder="Ne? (ör. eczane)" aria-label="Ne arıyorsunuz"><input id="nr" placeholder="Nerede? (ör. Çankaya, Ankara)" aria-label="Nerede">'
               '<button id="mb" type="button">Haritada göster</button></div>'
               '<iframe id="mf" title="Arama haritası" style="display:none" loading="lazy" allowfullscreen></iframe></section>')
    out.append(FOOT.replace("</body></html>", HOME_JS + "</body></html>"))
    return "".join(out)


def render_city_hub(city, cache, today):
    path = f"/sehir/{slugify(city)}/"
    title = f"{city} İşletme ve Hizmet Rehberi - Tüm Kategoriler | Nearadin.net"
    desc = f"{city} ilindeki restoran, tesisatçı, kuaför, eczane ve diğer tüm hizmetleri harita üzerinde bulun."
    out = [head(title, desc, path, jsonld(crumbs_ld([("Ana sayfa", "/"), ("Şehirler", "/sehir/"), (city, path)])))]
    out.append(f'<p class="crumb"><a href="/">Ana sayfa</a> › <a href="/sehir/">Şehirler</a> › {esc(city)}</p>')
    out.append(f'<section class="card"><h1>{esc(city)} hizmet rehberi</h1><p>{esc(city)} için bir kategori seçin.</p><div class="grid">'
               + "".join(f'<a class="cat" href="{page_path(c, city)}"><b>{icon(c)}</b>{esc(c)}</a>' for c in CATEGORIES)
               + "</div></section>")
    news = latest_news(cache, city=city, limit=6)
    if news:
        out.append(f'<section class="card"><h2>{esc(city)} güncel haberler</h2><ul class="news">{news_list(news)}</ul></section>')
    out.append('<section class="card"><h2>Diğer şehirler</h2><div class="tags">'
               + "".join(f'<a href="/sehir/{slugify(c)}/">{esc(c)}</a>' for c in TOP_CITIES if c != city)
               + '<a href="/sehir/">Tüm şehirler</a></div></section>' + FOOT)
    return "".join(out)


def render_city_index(today):
    path = "/sehir/"
    title = "Şehirler - 81 İl İşletme Rehberi | Nearadin.net"
    desc = "Türkiye'nin 81 ilinde işletme ve hizmet arayın; şehrinizi seçin."
    out = [head(title, desc, path, jsonld(crumbs_ld([("Ana sayfa", "/"), ("Şehirler", path)])))]
    out.append('<section class="card"><h1>Şehirler</h1><p>Bir il seçin.</p><div class="tags">'
               + "".join(f'<a href="/sehir/{slugify(c)}/">{esc(c)}</a>' for c in CITIES) + "</div></section>" + FOOT)
    return "".join(out)


def write(rel, content):
    p = ROOT / rel.lstrip("/")
    if p.suffix == "":
        p = p / "index.html"
    elif rel.endswith("/"):
        p = p / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- ana akış
def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = load_cache()
    refresh_cache(cache)

    urls = [("/", "1.0"), ("/ara/", "0.8"), ("/sehir/", "0.8")]
    write("/", render_home(cache, today))
    write("/ara/", render_index(today))
    write("/sehir/", render_city_index(today))
    for city in CITIES:
        write(f"/sehir/{slugify(city)}/", render_city_hub(city, cache, today))
        urls.append((f"/sehir/{slugify(city)}/", "0.7"))
    for cat in CATEGORIES:
        write(f"/ara/{slugify(cat)}/", render_category(cat, today))
        urls.append((f"/ara/{slugify(cat)}/", "0.7"))
        for city in CITIES:
            items = cache.get(f"{cat}|{city}", {}).get("items", [])
            page, indexable = render_page(cat, city, items, today)
            write(page_path(cat, city), page)
            if indexable:
                urls.append((page_path(cat, city), "0.6"))

    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, pr in urls:
        sm.append(f"<url><loc>{SITE}{u}</loc><lastmod>{today}</lastmod><priority>{pr}</priority></url>")
    sm.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    print(f"Tamam: {len(CATEGORIES) * len(CITIES)} sayfa üretildi, sitemap'te {len(urls)} URL var.")


if __name__ == "__main__":
    main()
