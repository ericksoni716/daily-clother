"""What the stylist is told and what is taken from its answer (the owner, 17 November: "inserting real
intelligence"; DECISIONS, "Outfits chosen by Claude").

Pure: no database, no network, no clock. Claude chooses the outfits (`tagger/stylist.py`); this module writes the
brief it reads and checks what comes back.

The brief, in plain words:
- the guide: the owner's menswear outfit notes from `docs/menswear-taxonomy.json`, given as preferences, not rules;
- the style profile: how the owner dresses, in their own words (it wins over the guide);
- the closet: every piece that can be worn today, one numbered line each, with what is known about it, how the
  owner rated it, when it was last worn, and the owner's own notes on it (they win over everything);
- the day: the hours dressed for as `closet/day.py` reads them, the owner's note about the day, the occasion and mood;
- what was worn lately and what the owner said about it;
- a shortlist from the rules engine, so nothing obvious is missed.

Only what cannot be worn stays a rule: a piece in the laundry, archived, being mended, for home, left out or rated
dislike is never in the list, so it cannot be chosen. From the answer, an outfit is kept when every number is in
the list, each piece is in a place it can fill, it has a top, a bottom and shoes, and it is not an outfit the
owner rated "not again"; anything else is dropped and said in `problems`. Nothing else is checked: layering,
colour, formality and warmth are Claude's to judge.

The conversation (`closet/stylejobs.py`): `talk_words` writes what was said today, and for a message just written
the outfits on the owner's screen; `keeps` shapes what Claude offers to remember for other days.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import day as dayparts
from . import outfits

GUIDE_FILE = Path(__file__).resolve().parents[2] / "docs" / "menswear-taxonomy.json"
# How the owner dresses, until they write their own in Settings, "Your style" (`closet/styleprofile.py`). The first
# line is the owner's, 17 November.
DEFAULT_KEPT = ("- I carry an umbrella, so a rain jacket is never a must. When it really rains, favour one if it suits "
                "the outfit, and boots or shoes that can take water.")
DEFAULT_PROFILE = f"""{DEFAULT_KEPT}
- Nothing else is written here yet: go by the guide and by what I have worn and said about it."""
HISTORY = 12                 # the newest this many worn outfits are told
SHORTLIST = 6                # the engine's best this many outfits are offered as a start
MAX_NOTE = 240               # the longest owner's note on a piece that is passed on (characters)
MAX_SAY = 500                # the longest message the owner can send Claude about the outfits (characters)
MAX_REPLY = 700              # the longest answer of Claude's that is kept
TALK_TURNS = 12              # the newest this many messages of the day's conversation are told
MAX_KEEPS = 2                # things Claude may offer to remember in one answer, at most
STYLE, PIECE = "style", "piece"   # where a thing to remember would be kept: Your style, or a piece's "How I wear it"
PLACE_WORDS = {"base": "base", "mid": "mid layer", "outer": "outer layer", "bottom": "bottom", "shoes": "shoes"}
RATING_WORDS = {"love": "loved", "like": "liked", "meh": "meh"}
REASON_WORDS = {"too_warm": "too warm", "too_cold": "too cold", "too_dressy": "too dressy", "too_casual": "too casual",
                "colours_clashed": "the colours clashed", "uncomfortable": "uncomfortable", "compliments": "got compliments"}
OUTFIT_RATING_WORDS = {"loved": "loved it", "fine": "fine", "not_again": "not again"}


@dataclass(frozen=True)
class Listed:
    """The pieces that can be worn today, numbered for Claude: `number[id]` and back, and each one's line."""
    ids: tuple[str, ...]                        # ids[n - 1] is piece number n
    pieces: Mapping[str, outfits.Piece]
    lines: tuple[str, ...]
    names: Mapping[str, str] = field(default_factory=dict)

    def number(self, item_id: str) -> int | None:
        try:
            return self.ids.index(item_id) + 1
        except ValueError:
            return None


def _text(v: object) -> str:
    return " ".join(str(v).split()) if isinstance(v, str) and v.strip() else ""


def _plain(v: object) -> str:
    return str(v).replace("_", " ")


def places_of(p: outfits.Piece) -> list[str]:
    """The places a piece can fill: some of base, mid, outer, bottom, shoes, or ["accessory"]."""
    if p.category in outfits.ACCESSORY_CATEGORIES:
        return ["accessory"]
    return [place for place in outfits.PLACES if outfits._fits(p, place)]


def _line(n: int, item: dict, p: outfits.Piece, days_ago: int | None) -> str:
    sil = item.get("silhouette") if isinstance(item.get("silhouette"), dict) else {}
    kind = _plain(item.get("kind") or p.category)
    where = " or ".join(PLACE_WORDS.get(pl, pl) for pl in places_of(p)) or "no place in an outfit"
    colour = _plain(p.color or item.get("color") or "colour unknown")
    parts = [f"{n}. {_text(item.get('name')) or p.label}", f"{kind} ({where})",
             colour if p.pattern == "solid" else f"{colour}, {_plain(p.pattern)}"]
    cloth = [w for w in (_text(item.get("material")), _plain(outfits.WEIGHT_CLASSES[p.weight])) if w]
    parts.append(", ".join(cloth))
    parts.append(_plain(outfits.rules().levels[p.formality]))
    if p.season != "all":
        parts.append(f"{p.season} season")
    shape = [f"{_plain(sil[k])} {word}".strip() for k, word in (("fit", "fit"), ("sleeve", "sleeve"), ("neck", "neck"),
                                                                 ("leg", "leg"), ("shoe_height", "height"))
             if isinstance(sil.get(k), str) and sil[k]]
    if shape:
        parts.append(", ".join(shape))
    if p.rating in RATING_WORDS:
        parts.append(RATING_WORDS[p.rating])
    parts.append("never worn" if days_ago is None else "worn today" if days_ago == 0 else
                 "worn yesterday" if days_ago == 1 else f"worn {days_ago} days ago")
    if p.in_storage:
        parts.append("put away in storage")
    for key, words in (("wear_notes", "how I wear it"), ("notes", "my note"), ("fit_notes", "fit")):
        note = _text(item.get(key))[:MAX_NOTE]
        if note:
            parts.append(f"{words}: “{note}”")
    return " | ".join(parts)


def listed(rows: list[dict], ctx: outfits.Context) -> Listed:
    """The closet as Claude is given it: every piece that can be worn today, in the order of the outfit's places
    (tops, bottoms, shoes, accessories), then by name. A piece the owner builds around is in it whatever its state,
    as for the engine."""
    order = {place: i for i, place in enumerate((*outfits.PLACES, "accessory"))}
    found = []
    for item in rows:
        p = outfits._piece(item) if isinstance(item, dict) else None
        if p is None or (outfits._unavailable(item, ctx) and p.id != ctx.build_around):
            continue
        places = places_of(p)
        if places:
            found.append((order[places[0]], p.label.lower(), p.id, p, item))
    found.sort(key=lambda f: f[:3])
    ids = tuple(f[2] for f in found)
    lines = tuple(_line(n, item, p, ctx.worn_days_ago.get(p.id)) for n, (_, _, _, p, item) in enumerate(found, 1))
    return Listed(ids, {f[2]: f[3] for f in found}, lines, {f[2]: _text(f[4].get("name")) or f[3].label for f in found})


# ---------------------------------------------------------------------- the guide
def guide(path: Path = GUIDE_FILE) -> str:
    """The owner's outfit notes from the menswear taxonomy, as plain lines under each heading."""
    data = json.loads(path.read_text(encoding="utf-8")).get("outfit") or {}

    def say(v: object, depth: int = 0) -> list[str]:
        pad = "  " * depth
        if isinstance(v, dict):
            out = []
            for k, x in v.items():
                if isinstance(x, dict | list):
                    out += [f"{pad}- {_plain(k)}:", *say(x, depth + 1)]
                else:
                    out.append(f"{pad}- {_plain(k)}: {x}")
            return out
        if isinstance(v, list):
            if all(not isinstance(x, dict | list) for x in v):
                return [f"{pad}- {', '.join(str(x) for x in v)}"]
            return [line for x in v for line in (say(x, depth) if not isinstance(x, dict)
                                                 else [f"{pad}- " + "; ".join(f"{_plain(k)} {y}" for k, y in x.items())])]
        return [f"{pad}- {v}"]

    out = []
    for heading, body in data.items():
        out += [f"{_plain(heading).capitalize()}:", *say(body)]
    return "\n".join(out)


# ---------------------------------------------------------------------- the day
def _deg(v: object) -> str:
    return f"{round(float(v))}°C"


def day_words(context: Mapping, ctx: outfits.Context, when: date) -> str:
    """The day in plain lines, from Today's `context` (its `detail` and `note` when there are any) and the choices."""
    out = [f"Date: {when.strftime('%A %d %B %Y')}." + (f" Place: {context['place']}." if context.get("place") else "")]
    d = context.get("detail")
    if isinstance(d, dict):
        out.append(f"Hours dressed for: {dayparts.span_words(d['from_hour'], d['to_hour'])}.")
        out.append(f"Temperature: {_deg(d['temp_low_c'])} to {_deg(d['temp_high_c'])}; it feels like "
                   f"{_deg(d['feels_low_c'])} to {_deg(d['feels_high_c'])}.")
        rain = d.get("rain")
        if rain:
            how = [f"{rain['chance']}% chance" if rain.get("chance") is not None else "",
                   f"about {rain['mm']} mm" if rain.get("mm") is not None else ""]
            out.append(f"Rain: {rain['words']} ({', '.join(h for h in how if h)}).".replace(" ().", "."))
        else:
            out.append("Rain: none expected in those hours.")
        wind = d.get("wind") or {}
        if wind.get("kmh") is not None:
            gust = f", gusts {round(wind['gust_kmh'])}" if wind.get("gust_kmh") is not None else ""
            out.append(f"Wind: up to {round(wind['kmh'])} km/h{gust}" + (f" ({wind['words']})." if wind.get("words") else "."))
        if d.get("uv") is not None:
            out.append(f"Sun: UV index up to {round(d['uv'])}." + (" Humid." if d.get("humid") else ""))
    else:
        how = {"mild": "no forecast could be had, so a mild day is assumed", "given": "typed by the owner"}.get(
            context.get("source"), "the whole day's forecast")
        out.append(f"Temperature: {_deg(ctx.low_c)} to {_deg(ctx.high_c)}; {'rain' if ctx.rain else 'no rain'} ({how}).")
    note = context.get("note")
    if isinstance(note, dict) and note.get("active"):
        took = "; ".join(note.get("words") or [])
        out.append(f"The owner's note about the day: “{_text(note.get('text'))}” (read as: {took}).")
    out.append(f"Occasion: {_plain(ctx.occasion)}. Mood: {_plain(ctx.mood)}.")
    return "\n".join(out)


# ---------------------------------------------------------------------- what was worn
def history_words(worn: list[dict], names: Mapping[str, str]) -> str:
    """The newest worn outfits, one line each, by the pieces' names (a piece may be in the laundry now, so it has
    no number), with the day they were worn for and what the owner said."""
    lines = []
    for o in worn[:HISTORY]:
        placed = o.get("pieces") if isinstance(o.get("pieces"), dict) else {}
        ids = [placed.get(pl) for pl in outfits.PLACES] + list(placed.get("accessories") or [])
        what = ", ".join(names.get(str(i), "a piece no longer in the closet") for i in ids if i)
        if not what:
            continue
        c = o.get("context") if isinstance(o.get("context"), dict) else {}
        on = [f"{_deg(c['low_c'])} to {_deg(c['high_c'])}" if isinstance(c.get("low_c"), int | float)
              and isinstance(c.get("high_c"), int | float) else "", "rain" if c.get("rain") else "",
              _plain(c["occasion"]) if c.get("occasion") else ""]
        said = [OUTFIT_RATING_WORDS.get(o.get("rating"), "not rated")]
        said += [REASON_WORDS[r] for r in (o.get("rating_reasons") or []) if r in REASON_WORDS]
        if _text(o.get("rating_note")):
            said.append(f"“{_text(o['rating_note'])[:MAX_NOTE]}”")
        day_of = f" ({', '.join(w for w in on if w)})" if any(on) else ""
        lines.append(f"- {o.get('worn_on')}{day_of}: {what}. The owner: {', '.join(said)}.")
    return "\n".join(lines) or "- Nothing has been recorded as worn yet."


def shortlist_words(engine: list[dict], listing: Listed) -> str:
    """The rules engine's best outfits, as the numbers of their pieces by place."""
    lines = []
    for o in engine[:SHORTLIST]:
        placed = o.get("pieces") or {}
        parts = [f"{PLACE_WORDS[pl]} {listing.number(placed[pl])}" for pl in outfits.PLACES
                 if placed.get(pl) and listing.number(placed[pl])]
        extras = [str(listing.number(a)) for a in placed.get("accessories") or [] if listing.number(a)]
        if extras:
            parts.append(f"accessories {', '.join(extras)}")
        if parts:
            lines.append("- " + "; ".join(parts))
    return "\n".join(lines) or "- The rules found no outfit."


def _numbers(o: Mapping, listing: Listed) -> str:
    placed = o.get("pieces") or {}
    parts = [f"{PLACE_WORDS[pl]} {listing.number(placed[pl])}" for pl in outfits.PLACES
             if placed.get(pl) and listing.number(placed[pl])]
    extras = [str(listing.number(a)) for a in placed.get("accessories") or [] if listing.number(a)]
    return "; ".join(parts + ([f"accessories {', '.join(extras)}"] if extras else []))


def talk_words(turns: list[dict], listing: Listed, shown: list[dict] | None = None, say: str | None = None,
               looking_at: int | None = None) -> str:
    """The day's conversation for Claude: the outfits on the owner's screen (when they have just written, `say`),
    then what was said, oldest first. `turns`: [{said, reply}] (`reply` None when no answer reached the owner).
    `looking_at`: which of the outfits shown the owner had in front of them as they wrote (0 is the first), when
    the page shows one at a time. Empty when nothing has been said."""
    out = []
    if say and shown:
        out.append("The outfits on the owner's screen now, in order (the owner may call them the first, the second "
                   "and so on):")
        for i, o in enumerate(shown, 1):
            whose = "yours" if o.get("by") == "claude" else "from the app's rules"
            why = f" You said: “{_text(o['reasons'][0])}”" if o.get("by") == "claude" and o.get("reasons") else ""
            out.append(f"- Outfit {i} ({whose}): {_numbers(o, listing)}.{why}")
    said = []
    for t in turns[-TALK_TURNS:]:
        if _text(t.get("said")):
            said.append(f"- The owner: “{_text(t['said'])}”")
            said.append(f"- You: “{_text(t['reply'])}”" if _text(t.get("reply")) else "- (your answer did not reach them)")
    if _text(say):
        at = (f", with outfit {looking_at + 1} in front of them" if shown and isinstance(looking_at, int)
              and not isinstance(looking_at, bool) and 0 <= looking_at < len(shown) else "")
        said.append(f"- The owner, just now{at}: “{_text(say)}”")
    if said:
        out += ["What was said today, oldest first:", *said]
    return "\n".join(out)


def keeps(offered: object, listing: Listed) -> list[dict]:
    """What Claude offers to remember, as it is kept until the owner answers: [{kind: "style" or "piece", item_id,
    name, text, state: "offered"}]. `offered`: [{about: 0 for the owner's style or a piece's number, text}]. One
    with no text, or about a number that is no piece, is dropped; at most `MAX_KEEPS`."""
    out = []
    for k in offered if isinstance(offered, list) else []:
        if not isinstance(k, Mapping):
            continue
        text, about = _text(k.get("text"))[:MAX_NOTE], k.get("about") or 0
        if not text or not isinstance(about, int) or isinstance(about, bool) or not 0 <= about <= len(listing.ids):
            continue
        item_id = listing.ids[about - 1] if about else None
        if any(o["text"] == text and o["item_id"] == item_id for o in out):
            continue
        out.append({"kind": PIECE if item_id else STYLE, "item_id": item_id,
                    "name": listing.names.get(item_id) if item_id else None, "text": text, "state": "offered"})
    return out[:MAX_KEEPS]


def brief(rows: list[dict], context: Mapping, ctx: outfits.Context, when: date, worn: list[dict],
          engine: list[dict], profile: str | None = None) -> tuple[dict[str, str], Listed]:
    """Everything the stylist is told, as named blocks of text, and the numbered closet to read its answer with."""
    listing = listed(rows, ctx)
    names = {str(r["id"]): _text(r.get("name")) or outfits._label(r) for r in rows if isinstance(r, dict) and r.get("id")}
    must = []
    if ctx.build_around and listing.number(ctx.build_around):
        must.append(f"Every outfit must include piece {listing.number(ctx.build_around)}: the owner wants to build around it.")
    kept = [listing.number(i) for i in ctx.keep if listing.number(i)]
    if kept:
        must.append(f"Every outfit must include pieces {', '.join(str(n) for n in kept)}: the owner is wearing an outfit again.")
    return {
        "guide": guide(),
        "profile": _text(profile) and profile.strip() or DEFAULT_PROFILE,
        "closet": "\n".join(listing.lines),
        "day": day_words(context, ctx, when),
        "worn": history_words(worn, names),
        "shortlist": shortlist_words(engine, listing),
        "must": "\n".join(must),
    }, listing


# ---------------------------------------------------------------------- the answer
def check(looks: list[dict], listing: Listed, ctx: outfits.Context,
          not_again: Mapping[tuple[str, ...], str] | None = None) -> tuple[list[dict], list[str]]:
    """The outfits kept from Claude's answer, in the engine's shape, and what was wrong with the others.

    `looks`: [{base, mid, outer, bottom, shoes (numbers, 0 for none), accessories: [numbers], why, watch}].
    Returns ([{"pieces": {base, mid, outer, bottom, shoes, accessories}, "score": None, "reasons": [why],
    "warnings": [watch], "by": "claude"}], [problem sentences]).
    """
    kept, problems, seen = [], [], set()
    for i, look in enumerate(looks, 1):
        def wrong(why: str, i=i) -> None:
            problems.append(f"Outfit {i} was left out: {why}.")
        placed: dict[str, str | None] = {}
        bad = None
        for place in outfits.PLACES:
            n = look.get(place) or 0
            if not n:
                placed[place] = None
                continue
            if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(listing.ids):
                bad = f"{n} is not a piece in the list"
                break
            item_id = listing.ids[n - 1]
            if place not in places_of(listing.pieces[item_id]):
                bad = f"piece {n} cannot be worn as the {PLACE_WORDS[place]}"
                break
            placed[place] = item_id
        if bad:
            wrong(bad)
            continue
        missing = [PLACE_WORDS[pl] for pl in ("base", "bottom", "shoes") if not placed[pl]]
        if missing:
            wrong(f"it has no {' or '.join(missing)}")
            continue
        core = [v for v in placed.values() if v]
        if len(set(core)) != len(core):
            wrong("the same piece is in two places")
            continue
        extras, kinds = [], set()
        for n in look.get("accessories") or []:
            if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(listing.ids):
                continue   # an accessory that is not in the list is dropped, the outfit stands
            item_id = listing.ids[n - 1]
            p = listing.pieces[item_id]
            if places_of(p) != ["accessory"] or p.category in kinds or item_id in extras:
                continue   # nor one that is no accessory, or a second of its kind
            kinds.add(p.category)
            extras.append(item_id)
        ids = set(core) | set(extras)
        if ctx.build_around and ctx.build_around not in ids:
            wrong("it leaves out the piece to build around")
            continue
        if ctx.keep and not set(ctx.keep) <= ids:
            wrong("it leaves out a piece kept from the outfit worn before")
            continue
        key = tuple(placed[pl] or "" for pl in outfits.PLACES)
        if not_again and key in not_again:
            wrong(f"the owner said “not again” to it on {not_again[key]}")
            continue
        if key in seen:
            wrong("it is the same as an outfit before it")
            continue
        seen.add(key)
        why, watch = _text(look.get("why")), _text(look.get("watch"))
        kept.append({"pieces": {**placed, "accessories": extras}, "score": None,
                     "reasons": [why] if why else [], "warnings": [watch] if watch else [], "by": "claude"})
    return kept, problems
