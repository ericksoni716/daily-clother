"""Draw a review sheet from the demo closet, without reading any photos.

Regenerate from the repository root:
    python tools/make_figure_sheet.py
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from closet.drawing.figure import svg_from_pieces  # noqa: E402

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
OUTPUT = ROOT / "docs" / "screenshots" / "outfit-figures.svg"
PLACES = ("base", "mid", "outer", "bottom", "shoes")
OUTFITS = (
    ("Hot", "A simple summer day", {
        "base": "White tee", "bottom": "Olive shorts", "shoes": "White canvas sneakers",
    }),
    ("Hot", "Polo and shorts", {
        "base": "Navy polo", "bottom": "Olive shorts", "shoes": "White leather sneakers",
    }),
    ("Hot", "Light shirt and denim", {
        "base": "Madras plaid shirt", "bottom": "Light wash jeans",
        "shoes": "White leather sneakers",
    }),
    ("Mild", "Closed sweater over a shirt", {
        "base": "Blue oxford shirt", "mid": "Cream v-neck sweater",
        "bottom": "Black jeans", "shoes": "White leather sneakers",
    }),
    ("Mild", "An open shirt over a tee", {
        "base": "White tee", "mid": "Chambray shirt",
        "bottom": "Dark indigo jeans", "shoes": "White canvas sneakers",
    }),
    ("Mild", "An open chore jacket", {
        "base": "Black tee", "outer": "Tan chore jacket",
        "bottom": "Light wash jeans", "shoes": "Grey runners",
    }),
    ("Cold", "Shirt, sweater and coat", {
        "base": "White dress shirt", "mid": "Cream v-neck sweater",
        "outer": "Black overcoat", "bottom": "Grey wool trousers", "shoes": "Brown boots",
    }),
    ("Cold", "Open overshirt and coat", {
        "base": "White tee", "mid": "Plaid flannel shirt",
        "outer": "Black overcoat", "bottom": "Brown corduroy trousers", "shoes": "Brown boots",
    }),
    ("Cold", "A warm cable-knit layer", {
        "base": "Blue oxford shirt", "mid": "Burgundy cable sweater",
        "outer": "Black overcoat", "bottom": "Dark indigo jeans", "shoes": "Brown boots",
    }),
)
COLORS = {"Hot": "#926132", "Mild": "#536b52", "Cold": "#526779"}


def element(parent: ET.Element, tag: str, **attrs: object) -> ET.Element:
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", {
        key.replace("_", "-"): str(value) for key, value in attrs.items()
    })


def text(parent: ET.Element, value: str, x: int, y: int, **attrs: object) -> None:
    element(parent, "text", x=x, y=y, **attrs).text = value


def namespace_figure(figure: ET.Element, prefix: str) -> None:
    """Nested SVGs share a document's IDs, including clips and title references."""
    ids = {node.attrib["id"]: prefix + node.attrib["id"]
           for node in figure.iter() if "id" in node.attrib}
    for node in figure.iter():
        for key, value in list(node.attrib.items()):
            if key == "id":
                value = ids[value]
            elif key in ("aria-labelledby", "aria-describedby"):
                value = " ".join(ids.get(part, part) for part in value.split())
            elif key in ("href", "{http://www.w3.org/1999/xlink}href"):
                if value.startswith("#"):
                    value = "#" + ids.get(value[1:], value[1:])
            else:
                value = re.sub(
                    r"""url\((['"]?)#([^)'"]+)\1\)""",
                    lambda match: f"url(#{ids.get(match[2], match[2])})",
                    value,
                )
            node.set(key, value)


def make_sheet() -> str:
    items = json.loads((ROOT / "backend/closet/demo_data/items.json").read_text())["items"]
    by_name = {item["name"]: item for item in items}
    figures = []
    for index, (_, _, names) in enumerate(OUTFITS, 1):
        pieces = {
            place: {**by_name[name]["answer"], "color_hex": by_name[name]["color_hex"]}
            for place, name in names.items()
        }
        figure = ET.fromstring(svg_from_pieces(pieces))
        namespace_figure(figure, f"look-{index}-")
        figures.append(figure)

    # One shared frame keeps the wearer's scale and ground consistent across cards.
    bounds = [tuple(map(float, figure.attrib["viewBox"].split())) for figure in figures]
    left = min(x for x, _, _, _ in bounds)
    top = min(y for _, y, _, _ in bounds)
    right = max(x + width for x, _, width, _ in bounds)
    bottom = max(y + height for _, y, _, height in bounds)
    viewbox = f"{left:.3f} {top:.3f} {right - left:.3f} {bottom - top:.3f}"

    sheet = ET.Element(f"{{{SVG}}}svg", {
        "viewBox": "0 0 1280 2320", "width": "1280", "height": "2320",
        "role": "img", "aria-labelledby": "sheet-title sheet-description",
        "font-family": "Arial, Helvetica, sans-serif", "fill": "#292c2a",
    })
    element(sheet, "title", id="sheet-title").text = "Closet — outfits as worn"
    element(sheet, "desc", id="sheet-description").text = (
        "Nine hand-chosen outfits from the demo closet: hot, mild and cold days. "
        "One, two and three upper-body layers, shorts, trousers, sneakers and boots. "
        "Every garment uses its stored description and colour, with no photos."
    )
    element(sheet, "rect", width=1280, height=2320, fill="#f3f1ec")
    text(sheet, "CLOSET  /  THE DEMO WARDROBE", 52, 48, font_size=13,
         letter_spacing=2.2, fill="#6c7069")
    text(sheet, "Outfits as worn", 52, 101, font_size=42, font_weight=600)
    text(sheet, "Nine chosen looks · the same wearer · the clothes you already know",
         52, 137, font_size=17, fill="#656a64")
    text(sheet, "Layers count tops only. These are drawing examples, not weather recommendations.",
         52, 167, font_size=14, fill="#656a64")

    for index, ((temperature, title, names), figure) in enumerate(zip(OUTFITS, figures, strict=True)):
        x, y = 52 + (index % 3) * 400, 200 + (index // 3) * 670
        card = element(sheet, "g", transform=f"translate({x} {y})",
                       data_outfit=index + 1, data_temperature=temperature.lower())
        element(card, "rect", width=376, height=646, rx=16,
                fill="#fffefa", stroke="#deded5")
        count = sum(place in names for place in ("base", "mid", "outer"))
        text(card, temperature.upper(), 24, 35, font_size=12, font_weight=700,
             letter_spacing=1.5, fill=COLORS[temperature])
        text(card, f"{count} {'layer' if count == 1 else 'layers'}", 352, 35,
             font_size=12, fill="#73776f", text_anchor="end")
        text(card, title, 24, 64, font_size=18, font_weight=600)
        figure.attrib.update({
            "x": "24", "y": "85", "width": "328", "height": "405", "viewBox": viewbox,
        })
        card.append(figure)
        element(card, "path", d="M 24 505 H 352", stroke="#e5e4dc")
        for line, place in enumerate(place for place in PLACES if place in names):
            text(card, place.capitalize(), 24, 533 + line * 23,
                 font_size=11, fill="#7a7e75")
            text(card, names[place], 82, 533 + line * 23, font_size=14)

    text(sheet, "Drawn from the demo items’ own descriptions and colours. No photos are used.",
         52, 2240, font_size=14, fill="#656a64")
    text(sheet, "Stripes, plaid and prints appear as plain colour here; some small details are not shown.",
         52, 2266, font_size=14, fill="#656a64")
    text(sheet, "Regenerate: python tools/make_figure_sheet.py",
         52, 2297, font_size=12, fill="#7a7e75")
    return ET.tostring(sheet, encoding="unicode") + "\n"


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(make_sheet(), encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))
