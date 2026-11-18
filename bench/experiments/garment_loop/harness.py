"""The garment loop test's machinery (see DESIGN.md): the app's own steps, run on one garment at a time, with every
call, answer, drawing and token count kept under bench/private/garment_loop/work/<id>/.

Nothing here is app code. It calls the app's code as the app would: the cutout (`closet.cutout`, `patterns.masks`),
the description (`tagger.claude_cli`, the plan route), the landmarks, the measuring (`patterns.measure`), the item
drawing (`drawing.item`, `drawing.stored`), and the experiment's surface form (`patterns.surface`)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from closet import cutout as C  # noqa: E402
from closet.drawing import item as I  # noqa: E402
from closet.drawing import stored  # noqa: E402
from closet.drawing.illustrate import Fill, Spec, render  # noqa: E402
from closet.patterns import described, surface  # noqa: E402
from closet.patterns.common import garment_mask, soft, to_lab  # noqa: E402
from closet.tagger import claude_cli  # noqa: E402
from closet.tagger.schema import drawing_for  # noqa: E402
from closet.tagger.tagging import CONFIG, PROMPT, SENT  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402
from pydantic import BaseModel, Field, create_model  # noqa: E402

PRIV = ROOT / "bench" / "private" / "garment_loop"
PHOTOS = PRIV / "photos"
WORK = Path(os.environ.get("GARMENT_LOOP_WORK") or PRIV / "work")   # another folder for smoke tests
MODELS_DIR = ROOT / "bench" / "models"
DEMO = ROOT / "backend" / "closet" / "demo_data" / "images"

TAGGING = CONFIG["roles"]["tagging"]
SORTING = CONFIG["roles"]["sorting"]
DRAWING = CONFIG["roles"]["drawing"]
CORRECT_EFFORT = "medium"       # the app's own render-and-correct loop (tagger/shoedrawing.py EFFORT)
BOTTOMS = ("jeans", "trousers", "shorts")
TOPS = ("tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat")


class PlanLimit(RuntimeError):
    """The Claude plan's usage limit: everything waits."""


# ---- the set ----------------------------------------------------------------------------------------------

def manifest() -> list[dict]:
    return json.loads((PRIV / "set.json").read_text())


def item(gid: str) -> dict:
    return next(r for r in manifest() if r["id"] == gid)


def wdir(gid: str) -> Path:
    d = WORK / gid
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


# ---- the app's photo and cutout ---------------------------------------------------------------------------

_model_lock = threading.Lock()


def model_path(name: str) -> Path:
    spec = C.MODELS[name]
    path = MODELS_DIR / f"{name}.onnx"
    with _model_lock:
        if not path.exists():
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            urllib.request.urlretrieve(spec.url, tmp)
            if C.sha256_of(tmp) != spec.sha256:
                tmp.unlink()
                raise RuntimeError(f"{name}: the download does not match its checksum")
            tmp.replace(path)
    return path


def photo(gid: str) -> Image.Image:
    """The photo as the app keeps it: turned upright, RGB, at most 1,600 px (`images.decode`, `store_image`)."""
    rec = item(gid)
    with Image.open(rec["path"]) as im:
        im.load()
        img = ImageOps.exif_transpose(im).convert("RGB")
    img.thumbnail((1600, 1600), Image.LANCZOS)
    return img


def make_cutout(gid: str) -> Image.Image:
    """The app's cutout (`app.real_cutter`), kept as the app keeps it (WebP, quality 82)."""
    out = wdir(gid) / "cut.webp"
    if out.exists():
        return Image.open(out).convert("RGBA")
    from closet.patterns import masks
    img = photo(gid)
    mask = C.predict_mask(img, "isnet-general-use", model_path("isnet-general-use"))
    second = False
    if masks.doubtful(img, mask):
        mask = masks.settle(img, mask, C.predict_mask(img, "u2net", model_path("u2net")), lambda *_: None)
        second = True
    cut = C.make_cutout(img, mask)[0]
    cut.save(out, "WEBP", quality=82, method=4)
    save_json(wdir(gid) / "cut.json", {"second_model": second, "size": list(cut.size)})
    return Image.open(out).convert("RGBA")


def cut_of(gid: str) -> Image.Image:
    return Image.open(wdir(gid) / "cut.webp").convert("RGBA")


# ---- calls through the plan route -------------------------------------------------------------------------

_SCRUB = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _schema(model_cls) -> dict:
    from anthropic.lib._parse._transform import transform_schema
    return transform_schema(model_cls)


def _save_image(img: Image.Image, path: Path, max_edge: int) -> None:
    if max_edge == 1024:
        claude_cli._save(img, path)        # exactly as the app sends a cutout
        return
    im = img.convert("RGB").copy()
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    im.save(path, "JPEG", quality=90)


def price(model: str, usage: dict) -> float:
    p = CONFIG["models"][model]
    return round((usage.get("input_tokens", 0) * p["input"] + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]
                  + usage.get("cache_read_input_tokens", 0) * p["cache_read"] + usage.get("output_tokens", 0) * p["output"]) / 1e6, 5)


def plan_call(prompt: str, images: list[Image.Image], schema_cls, model: str, effort: str, system: str,
              max_edge: int = 1024, timeout: float = 420, attempts: int = 3) -> dict:
    """One call through `claude -p`, as the app's plan route makes it. One answer, kept as given."""
    exe = claude_cli.find_claude()
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    schema = _schema(schema_cls)
    last = None
    for attempt in range(1, attempts + 1):
        with tempfile.TemporaryDirectory(prefix="garment-loop-") as tmp:
            names = []
            for i, im in enumerate(images, 1):
                name = f"photo-{i}.jpg"
                _save_image(im, Path(tmp) / name, max_edge)
                names.append(name)
            listing = ", ".join(names)
            full = (f"{prompt}\n\nThe image file{'s are' if len(names) > 1 else ' is'} in the current folder: {listing}. "
                    "Open each with the Read tool, then give your answer.")
            cmd = claude_cli.print_command(exe, model, effort, schema, "Read", system)
            t0 = time.time()
            try:
                with claude_cli.prompt_file(full) as stdin:
                    proc = subprocess.run(cmd, cwd=tmp, env=env, stdin=stdin, capture_output=True, timeout=timeout,
                                          encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                last = "timeout"
                continue
        seconds = round(time.time() - t0, 1)
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            out = {}
        text = f"{out.get('result') or ''} {proc.stderr or ''} {proc.stdout if not out else ''}".lower()
        answer = out.get("structured_output")
        failed = proc.returncode != 0 or bool(out.get("is_error")) or answer is None
        if failed and any(w in text for w in claude_cli._LIMIT_WORDS):
            raise PlanLimit((out.get("result") or proc.stderr or "")[:300])
        if failed:
            last = (out.get("result") or proc.stderr or proc.stdout or "no output")[:300]
            time.sleep(5 * attempt)
            continue
        usage = {k: int((out.get("usage") or {}).get(k) or 0) for k in
                 ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
        return {"model": model, "effort": effort, "seconds": seconds, "usage": usage, "attempts": attempt,
                "cli_cost_usd": out.get("total_cost_usd"), "price_usd": price(model, usage),
                "num_turns": out.get("num_turns"), "answer": answer,
                "prompt_sha": hashlib.sha256(full.encode()).hexdigest()[:12]}
    raise RuntimeError(f"no usable answer from {model}: {last}")


# ---- the calls the arms make ------------------------------------------------------------------------------

def base_description(gid: str) -> dict:
    """The app's own description of the garment (the describing model, its unchanged form): every arm's shape."""
    path = wdir(gid) / "base.json"
    rec = load_json(path)
    if rec is None:
        rec = plan_call(PROMPT, [cut_of(gid)], SENT, TAGGING, CONFIG["models"][TAGGING]["effort"], claude_cli.SYSTEM)
        rec["answer"] = claude_cli.fitted(rec["answer"]).model_dump(mode="json")
        save_json(path, rec)
    return rec


def is_bottom(gid: str) -> bool:
    return base_description(gid)["answer"]["category"] in BOTTOMS


def ruler(gid: str) -> dict | None:
    """The chest's underarm points on a top (the app's landmarks call, the larger model), the waistband on a
    bottom (from the cutout)."""
    path = wdir(gid) / "ruler.json"
    rec = load_json(path)
    if rec is None:
        cat = base_description(gid)["answer"]["category"]
        if cat in BOTTOMS:
            rec = {"how": "waist", "points": surface.waist_ruler(cut_of(gid))}
        elif cat in TOPS:
            from closet.tagger import landmarks
            t0 = time.time()
            marks = landmarks.ask(cut_of(gid), ("plan",))
            rec = {"how": "landmarks", "points": marks, "seconds": round(time.time() - t0, 1)}
        else:
            rec = {"how": "none", "points": None}
        save_json(path, rec)
    return rec["points"]


SurfaceForm = create_model("ItemTagsSentSurface", __base__=SENT,
                           surface=(surface.Surface, Field(description=surface.FIELD_TEXT["surface"])))
DESCRIBE_PROMPT = PROMPT + "\n" + surface.GUIDANCE


def describe(gid: str, model: str, run: int) -> dict:
    """Arms B and C: the description call with `surface` added, one answer per run."""
    tag = {TAGGING: "B", SORTING: "C-sonnet", DRAWING: "C-opus"}[model]
    path = wdir(gid) / "calls" / f"{tag}_run{run}.json"
    rec = load_json(path)
    if rec is None:
        rec = plan_call(DESCRIBE_PROMPT, [cut_of(gid)], SurfaceForm, model, CONFIG["models"][model]["effort"],
                        claude_cli.SYSTEM)
        rec["surface"] = rec["answer"].get("surface")
        save_json(path, rec)
    return rec


class Patch(BaseModel):
    seen: str = Field(description="One short line: what differs between the drawing's cloth and the photo's, or "
                                  "'matches'.")
    kind: surface.Kind | None = Field(description="null to keep. " + surface.FIELD_TEXT["kind"])
    bands: list[described.Band] | None = Field(description="null to keep. " + surface.FIELD_TEXT["bands"])
    direction: surface.Direction | None = Field(description="null to keep. " + surface.FIELD_TEXT["direction"])
    blocks: list[surface.Block] | None = Field(description="null to keep. " + surface.FIELD_TEXT["blocks"])
    colors: list[surface.Colour] | None = Field(description="null to keep. " + surface.FIELD_TEXT["colors"])
    scale: float | None = Field(description="null to keep. Only when the repeat is drawn too big or too small: how "
                                            "much bigger to draw it (2 = twice as big, 0.5 = half as big).")


CORRECT_SYSTEM = ("You check a drawing of a piece of clothing against its photo for a private wardrobe app. Look at "
                  "the image file named in the request with the Read tool, then answer in the required JSON format. "
                  "Do nothing else.")
CORRECT_PROMPT = """The image shows, on the left, a photo of one piece of clothing with its background removed and, on the right, the drawing a wardrobe app made of it from the description of its cloth below. The drawing's outline and details are the app's and stay as they are; only the cloth (its colours and its pattern) comes from the description, and only the description can be changed.

Compare the cloth in the drawing with the cloth in the photo: the ground colour; the other colours and how much of each; the kind of pattern; the order and widths of the bands; the way they run; the size of the repeat against the garment. Then give a patch: each field you give replaces that field of the description whole; leave a field null to keep it. To make the repeat bigger or smaller, use scale, not size. If the drawing's cloth already matches the photo, leave every field null. A drawing that says less (plain, or other with the main colours) is better than one that shows the wrong pattern.

The description of the cloth now:
{surface}"""


def correct(gid: str, tag: str, chain: int, rnd: int, current: dict, compare: Image.Image, model: str) -> dict:
    """One correction of the loop: the cutout and the drawing side by side, and the description as it stands."""
    path = wdir(gid) / "calls" / f"{tag}_chain{chain}_round{rnd}.json"
    rec = load_json(path)
    if rec is None:
        prompt = CORRECT_PROMPT.format(surface=json.dumps(current, indent=1))
        effort = CORRECT_EFFORT if model == DRAWING else CONFIG["models"][model]["effort"]
        rec = plan_call(prompt, [compare], Patch, model, effort, CORRECT_SYSTEM, max_edge=1568)
        save_json(path, rec)
    return rec


# ---- drawing --------------------------------------------------------------------------------------------------

CARD = (241, 238, 232)


def _uncarded(svg: str) -> str:
    import re
    return re.sub(r'<rect width="400" height="460" rx="18" fill="#[0-9a-fA-F]{6}"/>', "", svg, count=1)


def svg_surface(answer: dict, d: dict, uid: str) -> str:
    """The app's drawing of the garment (its shape from `answer`) with a described surface (`surface.drawn`)."""
    tags = I._tags(answer, [])
    template, params, extras, _ = drawing_for(tags)
    if template in ("tie", "socks"):
        params.pop("pattern", None)
    params.pop("colorblock", None)
    extras.pop("block_color", None)
    if d["blocks"]:
        params["colorblock"] = tuple(p for p, _ in d["blocks"])
        extras["block_color"] = d["blocks"][0][1]
    fill = stored.fill_from(d["kept"], d["body"]) if d["kept"] else None
    fill = fill or Fill("solid", d["body"])
    return _uncarded(render(Spec(template, params, fill, **extras), I.STYLE, uid=uid))


def svg_measured(answer: dict, kept: dict | None, uid: str) -> str:
    """Arm A: the app's drawing with what measuring kept, else in the item's colour."""
    tags = I._tags(answer, [])
    hex_ = I._color(None, tags.color)
    fill = stored.fill_from(kept, hex_) if kept else None
    graphic = stored.graphic_from(kept) if kept else None
    return _uncarded(I.drawing_from_answer(answer, None, uid=uid, fill=fill, graphic=graphic).svg)


def rasterise(pairs: list[tuple[Path, Path]], scale: int = 2) -> None:
    """SVG files to transparent PNGs through Chromium."""
    todo = [{"svg": str(s), "png": str(p), "scale": scale} for s, p in pairs]
    if not todo:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(todo, f)
    try:
        subprocess.run(["node", str(HERE / "shoot.js"), f.name], check=True, capture_output=True, timeout=600,
                       cwd=str(HERE))
    finally:
        os.unlink(f.name)


def draw(gid: str, name: str, svg: str) -> Image.Image:
    """Keep a drawing as SVG and transparent PNG under work/<id>/draw/; returns the PNG."""
    d = wdir(gid) / "draw"
    d.mkdir(exist_ok=True)
    (d / f"{name}.svg").write_text(svg)
    rasterise([(d / f"{name}.svg", d / f"{name}.png")])
    return Image.open(d / f"{name}.png").convert("RGBA")


def _crop(img: Image.Image) -> Image.Image:
    a = np.asarray(img)[..., 3]
    ys, xs = np.where(a > 20)
    return img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)) if len(xs) else img


def side_by_side(left: Image.Image, right: Image.Image, height: int = 760, bg=(128, 128, 128), gap: int = 40) -> Image.Image:
    """Two pictures at the same height on one background, nothing else."""
    def fit(im):
        im = im.convert("RGBA")
        return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
    a, b = fit(left), fit(right)
    out = Image.new("RGB", (a.width + b.width + 3 * gap, height + 2 * gap), bg)
    out.paste(a, (gap, gap), a)
    out.paste(b, (2 * gap + a.width, gap), b)
    return out


def compare_image(cut: Image.Image, drawing: Image.Image) -> Image.Image:
    """What the corrector sees: the cutout and the drawing, each cropped to its garment, the same height, on grey."""
    return side_by_side(_crop(cut), _crop(drawing))


def judge_image(gid: str, drawing: Image.Image) -> Image.Image:
    """What the judge sees: the original photo and the drawing on its card, the same height, on white."""
    card = Image.new("RGBA", drawing.size, CARD + (255,))
    card.alpha_composite(drawing)
    return side_by_side(photo(gid), card, height=800, bg=(255, 255, 255), gap=24)


# ---- the loop's score (DESIGN.md section 6) ------------------------------------------------------------------------

EMD_SPAN = 30.0       # colour: 1 minus the make-up distance over this
SAY_LESS = 0.35       # structure given to a drawing with no pattern
WINDOWS = 24
TURNS = (-15, -10, -5, 0, 5, 10, 15)


def _cie(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    return lab * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def _quantiles(px: np.ndarray, n: int = 400) -> np.ndarray:
    q = np.linspace(0.5 / n, 1 - 0.5 / n, n)
    return np.stack([np.quantile(px[:, c], q) for c in range(3)], 1)


def photo_pixels(cut: Image.Image) -> np.ndarray:
    arr = np.asarray(cut.convert("RGBA"))
    on = cv2.erode((arr[..., 3] > 200).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    px = cv2.GaussianBlur(np.ascontiguousarray(arr[..., :3]), (0, 0), 2.0)[on]
    return _cie(px)


def drawing_pixels(drawing: Image.Image) -> np.ndarray:
    arr = np.asarray(drawing.convert("RGBA"))
    k = max(3, int(0.02 * max(arr.shape[:2])) | 1)
    on = cv2.erode((arr[..., 3] > 200).astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)
    return _cie(arr[..., :3][on])


def colour_distance(cut: Image.Image, drawing: Image.Image) -> float:
    a, b = _quantiles(photo_pixels(cut)), _quantiles(drawing_pixels(drawing))
    gap = np.abs(a - b).mean(0)
    return float(0.5 * gap[0] + gap[1] + gap[2])


def _rotated(img: np.ndarray, deg: float) -> np.ndarray:
    if deg == 0:
        return img
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def structure(cut: Image.Image, tile_rgb: np.ndarray, repeat_px: float) -> tuple[float, int]:
    """How well the drawn repeat, at the size the drawing uses, explains the photo where it is: the median over
    windows about 1.5 repeats a side of the best normalised correlation of the light-evened signal at any offset
    and at turns of up to 15 degrees. Returns (the median, the number of windows)."""
    arr = np.asarray(cut.convert("RGBA"))
    m = garment_mask(cut, thresh=128)
    ys, xs = np.where(m)
    if len(xs) < 400:
        return 0.0, 0
    bw, bh = xs.max() - xs.min(), ys.max() - ys.min()
    rep = max(6.0, float(repeat_px))
    win = int(np.clip(1.5 * rep, 40, 0.45 * min(bw, bh)))
    sig = soft(to_lab(np.ascontiguousarray(arr[..., :3])), m, light=3 * rep)
    th = max(2, round(rep * tile_rgb.shape[0] / tile_rgb.shape[1]))
    tile = cv2.resize(tile_rgb, (max(2, round(rep)), th), interpolation=cv2.INTER_AREA)
    reps = int(np.ceil((win * 1.5 + 2 * rep) / min(tile.shape[:2]))) + 3
    big = np.tile(tile, (reps, reps, 1))
    big_sig = soft(to_lab(np.ascontiguousarray(big)), light=None)
    centres = [(x, y) for y in range(ys.min() + win // 2, ys.max() - win // 2, max(4, win // 2))
               for x in range(xs.min() + win // 2, xs.max() - win // 2, max(4, win // 2))]
    good = [(x, y) for x, y in centres
            if m[y - win // 2:y - win // 2 + win, x - win // 2:x - win // 2 + win].mean() >= 0.8]
    if not good:
        return 0.0, 0
    pick = [good[i] for i in np.linspace(0, len(good) - 1, min(WINDOWS, len(good))).round().astype(int)]
    side = win + int(1.2 * rep) + 2
    cy, cx = big_sig.shape[0] // 2, big_sig.shape[1] // 2
    searches = []
    for deg in TURNS:
        r = _rotated(big_sig, deg)
        searches.append(np.ascontiguousarray(r[cy - side // 2:cy - side // 2 + side, cx - side // 2:cx - side // 2 + side]))
    best = []
    for x, y in pick:
        y0, x0 = y - win // 2, x - win // 2
        patch = sig[y0:y0 + win, x0:x0 + win].copy()
        pm = m[y0:y0 + win, x0:x0 + win]
        patch[~pm] = patch[pm].mean()
        if patch.std() < 1e-3:
            best.append(0.0)
            continue
        scores = [float(cv2.matchTemplate(s, patch.astype(np.float32), cv2.TM_CCOEFF_NORMED).max()) for s in searches
                  if s.shape[0] >= win and s.shape[1] >= win]
        best.append(max(scores) if scores else 0.0)
    return float(max(0.0, np.median(best))), len(pick)


def ruler_px(points: dict | None) -> float | None:
    try:
        a, b = points["underarm_left"], points["underarm_right"]
        return float(np.hypot(a["x"] - b["x"], a["y"] - b["y"]))
    except (KeyError, TypeError):
        return None


def loop_score(cut: Image.Image, drawing: Image.Image, d: dict, points: dict | None) -> dict:
    """The loop's own score for a drawing: colour and structure, each 0 to 1, averaged."""
    emd = colour_distance(cut, drawing)
    colour = max(0.0, 1 - emd / EMD_SPAN)
    length = ruler_px(points)
    if d.get("tile") is not None and d.get("repeats") and length:
        struct, n = structure(cut, d["tile"], length / d["repeats"])
    else:
        struct, n = SAY_LESS, 0
    return {"score": round((colour + struct) / 2, 4), "colour": round(colour, 4), "emd": round(emd, 2),
            "structure": round(struct, 4), "windows": n}
