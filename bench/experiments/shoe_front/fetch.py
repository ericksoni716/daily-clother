"""Fetch a side, front, top and pair photo for each of a few real shoes from one shop whose pages label each photo's
view, into WORK/photos/<key>/<VIEW>.jpg, and write WORK/report.json (which views each page had). The search takes
whatever the shop lists first that matches the colour words, so the shoe found is not always the one named: the
line-up only needs real shoes, not particular ones. A site that refuses the request is left alone. The photos are
the shop's: they stay under bench/private (git-ignored) and are never committed."""
import re, json, subprocess, sys, time, pathlib, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import WORK
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
def get(url, out=None):
    args = ["curl", "-s", "-m", "40", "-A", UA, "-L", url]
    if out: args += ["-o", out]
    r = subprocess.run(args, capture_output=True)
    return r.stdout.decode("utf8", "ignore")
SHOES = [  # key, search term, words the colour should contain (any order), or None for the first style
    ("stan_navy", "adidas originals stan smith men", ["white", "navy"]),
    ("clubc", "reebok club c 85 men", ["white", "green"]),
    ("af1", "nike air force 1 07 men", ["white", "white"]),   # found a grey mesh runner instead; kept under this key
    ("samba", "adidas originals samba og men", ["white", "black"]),
    ("oldskool", "vans old skool", ["black", "white"]),
    ("nb574", "new balance classics 574 men", ["grey"]),
    ("runner_black", "brooks ghost men", ["black"]),
    ("runner_colour", "asics gel-kayano men", None),
    ("desert", "clarks desert boot men", ["beeswax"]),
    ("timberland", "timberland 6 premium boot men", ["wheat"]),
    ("docs", "dr martens 1460 smooth leather", ["black"]),
    ("oxford", "allen edmonds park avenue", ["walnut"]),
    ("loafer", "g.h. bass larson weejuns men", None),
    ("kswiss", "k-swiss classic vn men white", ["white"]),   # found a black skate shoe with a big white logo; kept
    ("grandpro", "cole haan grandpro tennis sneaker men", ["white"]),
    ("boot_wheat", "timberland 6 inch premium waterproof boot men", ["wheat"]),
    ("blundstone", "blundstone 500 chelsea", ["brown"]),
]
out = WORK / "photos"; out.mkdir(parents=True, exist_ok=True)
report = {}
for key, term, want in SHOES:
    s = get("https://www.zappos.com/search?term=" + urllib.parse.quote_plus(term))
    links = list(dict.fromkeys(re.findall(r'/p/[a-z0-9-]+/product/\d+', s)))
    if not links:
        report[key] = "no results"; continue
    found = None
    for link in links[:4]:
        p = get("https://www.zappos.com" + link).replace('\\"', '"')
        name = re.search(r'<title>([^<]*)</title>', p)
        styles = re.findall(r'"color":"([^"]*)","colorId":"\d+","coreFlag":[^,]*,"images":\[([^\]]*)\]', p)
        for colour, imgs in styles:
            if want is None or all(w in colour.lower() for w in want):
                found = (link, name.group(1) if name else "", colour, re.findall(r'"imageId":"([^"]+)","type":"([A-Z0-9]+)"', imgs)); break
        if found: break
        time.sleep(1)
    if not found:
        report[key] = {"miss": [c for c, _ in styles][:12], "link": links[0]}; continue
    link, name, colour, imgs = found
    types = {}
    for iid, typ in imgs:
        types.setdefault(typ, iid)
    d = out / key; d.mkdir(exist_ok=True)
    for typ, iid in types.items():
        if typ in ("LEFT", "RGHT", "FRNT", "TOPP", "PAIR"):
            get(f"https://m.media-amazon.com/images/I/{iid}._AC_SR1200,1200_.jpg", str(d / f"{typ}.jpg"))
    report[key] = {"name": name, "colour": colour, "views": sorted(types), "link": link}
    time.sleep(1)
json.dump(report, open(WORK / "report.json", "w"), indent=1)
for k, v in report.items(): print(k, v)
