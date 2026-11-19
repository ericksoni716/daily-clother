# Can the measured stripes/plaid path be removed? (read-only investigation, 19 Nov 2026)

Repo: /home/user/daily-clother. Nothing was modified. Paths below are relative to `backend/closet/` unless they say otherwise.

## Verdict

**Keep it for now. It is not safe to remove as things stand.** An ordinary action reaches it for a brand-new item
added today: tapping a different Pattern chip under Details on the item page (or saying a new pattern word in a
sentence correction). It also runs by itself in the background for older items. Removing it is reasonable, but only
after the steps in section 6: a decision on what an owner-chosen pattern word draws, plus a data check (and possibly
a re-describe) for older items. Confidence in "do not remove now": very high (about 95%). The gate is a single
branch in `patjobs.method` (line 98), and every trigger below goes through it. The tests themselves treat the
owner-override branch as intended behaviour (`tests/test_described_surface.py:133-136`).

## The gate (every trigger goes through this)

`patjobs.method(row)` (patjobs.py:86-98) decides what the pattern job does for one item:

- `_surface(row)` (patjobs.py:69-83) returns the owner's own cloth (`items.own_cloth.surface`) if they set one.
  Otherwise it returns Claude's stored `tag_answer.surface`, **unless** one of these holds, in which case it
  returns None:
  - (a) the answer has no usable surface (`surfaceform.kind_of` is None, surfaceform.py:127-134). That covers
    answers from before schema 6, **and a new answer where Claude sent `surface: null`**: the form sent says
    "required (null allowed)" (tagger/tagging.py:208-212).
  - (b) the answer's `pattern` differs from the item's `pattern` (patjobs.py:80): the owner changed the word.
- If the surface is not None, the result is SURFACE (the described path) or nothing.
- Otherwise (patjobs.py:98) it returns **the pattern word itself** when it is one of
  `stripe, plaid, floral, camo, other`. That is the measured path.
- `run_one` (patjobs.py:183) adds `how = method(row) or row["pattern"]`.

`app.real_measurer` (app.py:268-273) sends SURFACE to `patterns.surface.kept_for_item`. Anything else goes to
`patterns.measure.measure`, whose branches are: plaid gives `_plaid` (flatten/plaid/straighten, up to about 2
minutes), stripe gives `_stripes` (stripes.measure4 and friends), floral/camo/other give `_print` (prints.quilt,
**shared with the described path**), and graphic gives `_graphic` (shared).

Landmarks: patjobs.py:193-203 asks Claude (`tagger/landmarks.py`, `app.real_landmarker` app.py:263-266) for a top
whenever `ruler` is true. For the measured path that is always (`how != SURFACE`). The described path asks only for
stripes and plaid (`surfaceform.needs_ruler`). So the landmarks call is **not** unique to the measured path.

## 1. Call graph from the entry points down to the measuring code

```
pattern worker thread (app.py:275, started at app.py:119-120; woken app.py:142-143, 256-257, 370-371)
  patjobs.Worker._loop -> drain (patjobs.py:269-285; returns at once for the demo profile, :272)
     recover (:138)  'working' -> 'waiting'  (after a quit, or a restored backup holding 'working')
     run_one (:171) -> method/how (:183) -> [landmarker] -> real_measurer (app.py:268)
         SURFACE -> patterns.surface.kept_for_item -> described.* (+ straighten._spacings, stripes.straightened_sequence;
                    'other' -> measure.measure(cut, "floral") -> prints)
         else    -> patterns.measure.measure -> _plaid | _stripes | _print | _graphic
```

Items get `pattern_state = 'waiting'` only from `patjobs.mark` (patjobs.py:101-111) or `patjobs.stale`
(patjobs.py:114-135). Their callers:

| # | Entry point | Path to mark/stale | Condition that ends in measured stripes/plaid |
|---|---|---|---|
| T1 | `PATCH /api/items/{id}` (app.py:700-708). UI: item page, Details, Pattern chips (frontend/src/screens/ItemDetail.tsx:311-316) | `items.update` -> `patjobs.mark` when "pattern" changed (items.py:343-344); also drops `own_cloth.surface` (items.py:335-339) | New word is stripe or plaid and differs from `tag_answer.pattern` (gate b). Also an item never described (tag_answer NULL, Claude out of reach), where the owner's word is always measured |
| T2 | `POST /api/items/{id}/correct` then `/correct/confirm` (app.py:907-929): the sentence correction | `corrections.confirm` -> `apply(kind="sentence")` -> `items.update(coarse)` -> mark (corrections.py:140); `cloth` mark (corrections.py:155) | The sentence changes the pattern word and Claude's correction gives no `cloth`. If it gives a `cloth`, own_cloth wins and the described path is used |
| T3 | `PUT details` (`corrections.apply`, app.py:898-899) | the same `items.update` when the changes include pattern | as T1 |
| T4 | History undo (`corrections.undo`, corrections.py:408-470) | mark (corrections.py:464-465) when pattern, tag_answer or own_cloth goes back and the saved drawing cannot be restored | Undo brings back an owner word, or a pre-surface answer (undoing a re-description) |
| T5 | Description arrives: tag worker -> `tagjobs.apply_answer` (tagjobs.py:180, 244-289) | mark (tagjobs.py:283) | (i) Claude returned `surface: null` on a stripe/plaid item: a **brand-new item**. (ii) The owner's word (source "user") is kept over the answer (`fill`, tagjobs.py:237) and differs from it: e.g. "Describe it again" (ItemDetail.tsx:389, `POST /retag` app.py:864-869, items.py:501-512) on an overridden item, or a word set while the item waited for Claude |
| T6 | Cutout made again: `jobs.run_one` (jobs.py:118-121) | mark when the item was described after the photo was added | Item without a surface (old answer, or T1/T5 states). Reached by "Try the cutout again" (`POST /retry-cutout`, app.py:717-719, items.py:486-498), by `jobs.recheck` and by `jobs.remeasure` |
| T7 | **Background, automatic**: cutout worker `drain` -> `jobs.remeasure` (jobs.py:248-249, 127-143) -> `patjobs.stale` | every drain of the cutout queue (startup and each new cutout); not in the demo | `pattern='plaid'`, state done with an old whole-garment tile (no "how", width_frac > 0.5) or failed with the old generic `FAILED` text. One-shot per item. Measured again only when there is no surface |
| T8 | **Background, automatic**: `jobs.recheck` (jobs.py:147-184, called from drain jobs.py:256) | cutout redone when `masks.doubtful_cutout` says so -> T6 -> mark | Front photo with `cutout_second` 0 or NULL, once the second model is ready; item without a surface |
| T9 | Retake photo `POST /api/items/{id}/photo` (`items.replace_photo`/`replace_front`, items.py:408-483) | clears pattern_fill (items.py:474-476); the new description marks it (T5) | Only T5(i) or (ii) |
| T10 | Restore a backup / quit mid-measure | `patjobs.recover` (patjobs.py:138-140) | Item already 'working' with no surface |

**Not callers** (checked):
- The demo closet: never measured (patjobs.py:272, jobs.py:248, DECISIONS:1109). It draws from tiles made in advance.
- `tools/`, `packaging/`, `bench/closet_bench`, `bench/tests`: no import of `closet.patterns`.
- `bench/experiments/garment_loop/{app_path,harness,run,analyse}.py` import `measure` / `_garment_width`. They are not
  in CI, so this is only research code.
- Migrations: only 0013 adds the columns. No backfill calls measuring.
- "Would this work?", shopping, Today and the stylist: none of them mark patterns.
- "Several items from one photo" goes through the same tag path (T5).

## 2. Reachability of each trigger

| Trigger | Brand-new item added today | Existing item, user edits it | Automatic in the background | Only old data |
|---|---|---|---|---|
| T1/T3 owner taps a different Pattern chip (stripe/plaid) | **Yes** (one tap after Claude describes it, or while it waits) | **Yes** | no | no |
| T2 sentence changes the word without a cloth | **Yes** (depends on Claude's correction) | **Yes** | no | no |
| T4 undo | Yes, after T1 | Yes | no | partly |
| T5(i) Claude returns `surface: null` | **Yes**, rare (the form allows null; how often is not measured in the repo) | on "Describe it again" | yes (the tag worker) | no |
| T5(ii) owner word kept over a new answer | Yes, if they set the word before the answer arrives | Yes ("Describe it again") | yes | no |
| T6 "Try the cutout again" | only in T1/T5 states | Yes | no | mostly |
| T7 remeasure (stale plaids) | no | no | **Yes** | **Yes** (one-shot) |
| T8 recheck (second model) | no (new cutouts record `cutout_second`) | no | **Yes** | **Yes** |
| T10 recover | no | no | yes | edge |

**The owner-override path (T1/T2) is not legacy.** It was deliberately kept on 18 Nov. From DECISIONS.md:1161:
"When the owner changes an item's pattern to another word than the answer's, the described surface is put aside:
their word is measured from the photo as before". From DECISIONS.md:1179: "A pattern word the owner sets later puts
their cloth aside (the latest word wins)". A test checks this
(`tests/test_described_surface.py:133-136`: owner "stripe" over answer "plaid" -> method "stripe").

One gap in the audit's description ("old answers and the owner override"): it **misses T5(i), Claude's null
surface on a new item**, and the never-described item whose word the owner set.

## 3. What the owner would see if it were removed

**Drawing reads stored data regardless of where it came from.** `illustrations.pattern_fill` / `pattern_graphic`
(illustrations.py:141-157) -> `drawing/stored.fill_from` (stored.py:108-141) reads `items.pattern_fill`:
- `kind:"stripes"` (bands, orientation, trim_bands, sleeves_banded): written by measured stripes, and also by the
  described path's bands across the body (`surface.panel_stripes`).
- `kind:"tile"` (image, width_frac, length_frac, phase, phase_right): written by measured plaid ("how" repeat,
  straightened or whole, or none in older data), by the described path ("how" described or panels) and by prints.

The format and its reader are shared, so `stored.py` and `drawing/fills` must stay whole. **Existing items drawn
from measured data keep their look as long as nothing re-marks them.** The kept tile is in the row, and
`palette.keep/settle` colours are stored too. They only change when T4 to T8 marks them again.

What happens per trigger depends on how the removal is done:

- **Naive removal** (delete the plaid and stripe branches of `measure.measure`): `method` still returns "plaid" or
  "stripe", `measure` returns None, and `run_one` stores `pattern_fill = NULL`, state failed, "Closet could not
  measure the checks from this photo..." (patjobs.py:212, 219-220).
  - T1/T2/T5: the item is **drawn in its plain colour with a false "could not measure" note**, plus a "Retake the
    photo" offer (frontend/src/retake.ts:27) that would not help.
  - T7/T8/T6 on old items: **an item drawn today from a good measured plaid or stripe loses it** and turns plain.
    That is a visible regression that happens by itself.
- **Fallback quality of the described path, where it applies** (DECISIONS.md:1142-1165, bench/experiments/garment_loop/README.md):
  - Stripes: bands (colour, width), direction (horizontal or vertical) and size word. The repeat is read from the
    photo against the landmarks (`surface.drawn`). Widths are "said", not photo-fitted. There are no placed chest
    bands with a separate ground, and no sleeve check. Bands across the body are a separate `blocks/panels` form.
  - Plaid: one band list taken as the same both ways, widths fitted from the photo (`described.photo_widths`),
    repeat from the photo, softened colours. There is no placement on the button line (measured has `phase`), and
    no unequal warp/weft or madras irregularity.
  - Scores on the held-out half (of 15): plaid and check, measured (arm A) 6.4 against described (F) 11.4; stripes
    5.1 against 11.6. Overall, patterned garments recognisable 42% against 88%, scale within 25% 35% against 71%,
    confidently wrong 8% against 0%.
  - So stripes and plaid are both covered, and measured is clearly worse on average. But the described path
    **needs Claude's surface**. With an owner word that differs from Claude's there is no surface for that word,
    so nothing is drawn.
- **The owner override has a partial replacement already**: the sentence correction can return a whole `cloth`
  (tagger/correcting.py:69-72, 107). That sets `own_cloth.surface` and so uses the described path
  (corrections.py:144-155). The Pattern chip has no such route.

## 4. Quality evidence and what the decision log says

- DECISIONS "The cloth drawn from its description (adopted 18 November)" (lines 1142-1165): adopted on the 60-garment
  test above. Measured is **not** declared dead. It is **kept deliberately in two places**:
  - line 1161, the owner's word "is measured from the photo as before";
  - line 1164, "An answer without a surface (every item described before this change, and the demo closet's) is
    measured from the photo as before, until it is described again | No migration, and nothing is sent to Claude
    again by itself".
- The described path still reuses measured pieces on purpose: a print is pieced by the app's own measuring
  (line 1157), and sizing uses `straighten._spacings` (line 1135).
- DECISIONS "Patterns drawn from the photo" (1077-1121) still documents measured behaviour as current, including
  the once-only remeasure of old plaids (line 1100) and re-measuring on a pattern change (line 1105).
- BACKLOG still lists open measured-plaid bugs as live (docs/BACKLOG.md:94-95: a pale check against a window, a dim
  burgundy plaid), with nothing saying they became moot.
- Bench: `bench/experiments/garment_loop/README.md` (arm A is "the app today", the measured path), plus
  `app_path.py`, which checked the app path on the 60 garments.
- Tests: `tests/test_patterns.py` (585 lines, measured modules), `test_patjobs.py` (444; stale/remeasure at
  349-404, plaid failure note at 337), `test_described_surface.py` (override at 133-147), `test_surface.py`,
  `test_described_plaid.py`. No test compares measured with described.

## 5. Shared code and the removal boundary

Live users of `patterns/` outside the measured path:
- `app.real_cutter` -> `masks.doubtful`, `masks.settle` (app.py:226-229)
- `jobs.recheck` -> `masks.doubtful_cutout` (jobs.py:160)
- `app.real_measurer` -> `surface.kept_for_item` (app.py:270). Its docstring wrongly says "not called by the app"
  (surface.py:1-2).
- `surface` -> `described`, `straighten._mask/_spacings`, `common.to_lab`, `measure.measure(cut,"floral")`
  (surface.py:252-254, 300-302, 322-324, 356-358, 497-500)
- `described.photo_repeats` -> `straighten._mask/_spacings` (described.py:155-156)
- `straighten._spacings` -> `_sequence_peaks` and `stripes.straightened_sequence` (straighten.py:531-584), which
  needs `stripes.strip_profiles`, `align_piecewise`, `extend_by_repeat` (stripes.py:55-197)
- `measure._print` -> `prints.quilt_garment` -> `common.body_mask`. `measure._graphic` -> `drawing.fills.extract_graphic`.

| File | Lines | Verdict |
|---|---|---|
| `patterns/plaid.py` | 178 | **Fully removable** (only `measure` uses it) |
| `patterns/flatten.py` | 400 | **Fully removable** (only `measure` uses it) |
| `patterns/straighten.py` | 614 | **Partially**: keep `_mask`, `_sequence_peaks`, `_spacings` (about 60 lines). Remove `by_lines`, `regular`, `by_bands`, `by_repeat`, the fitting class, `_delta_e`, `preview` and the rest |
| `patterns/stripes.py` | 918 | **Partially**: keep `strip_profiles`, `align_piecewise`, `straightened_sequence`, `extend_by_repeat` (about 160 lines). Remove `measure3/4`, the fold functions, `yarn_colours`, `ground_*`, `compose_placed`, `band_colours`, `balance_to_words`, `regions_from_landmarks`, `sleeves_carry_bands` and the rest |
| `patterns/measure.py` | 313 | **Partially**: keep `measure()` dispatch for floral/camo/other and graphic, `_print`, `_graphic`, `_garment_width`. Remove `_plaid*`, `_straightened`, `_rebuilt`, `_placed`, `_moved`, `_button_x`, `_lit`, `_stripes`, `_gain_fix`, and the unused `see_through_mask` / `combine_masks` |
| `patterns/masks.py` | 187 | Must stay (cutout). `surfaces()` (160-187) is used only by measured plaid and is removable |
| `patterns/common.py` | 110 | Must stay (`to_lab`, `body_mask`, `garment_mask`). `best_tile`, `soft_tile`, `signal`, `autocorr`, `soft`, `lab_to_rgb` become unused by the app (the bench harness uses `soft`) |
| `patterns/prints.py` | 128 | Must stay (`lean` goes with plaid) |
| `patterns/described.py`, `surface.py` | 465, 513 | Must stay (live default) |
| `palette.exposure` | small | Removable (only `measure._lit`) |
| `patjobs.stale` + `jobs.remeasure` | about 40 | Removable or rewritten. Today they only make sense for measured plaids |
| `patjobs.py:98` fallback, `PLAID_FAILED` wording | | Must change, not just be deleted (see 6) |
| `drawing/stored.py`, `drawing/fills`, `tagger/landmarks.py`, `palette.keep/settle`, `items.pattern_fill` | | **Must stay** (shared format and reader; landmarks are used by the described path) |
| OpenCV dependency | | Stays (`described`, `masks`, `prints` use cv2) |

Realistic removal: about 1,700 to 1,900 app lines, plus most of `test_patterns.py` and parts of `test_patjobs.py`,
not the full 2.1k, because about 220 lines of straighten/stripes stay for the described path's sizing.

## 6. What would have to be true to be "extremely confident"

1. **An owner decision on the override (T1/T2/T5(ii)).** Choose what the Pattern chip draws when its word differs
   from Claude's. The options:
   - (a) plain colour with an honest note ("drawn in its colour; describe the cloth in a sentence to draw it");
   - (b) send the word to Claude as a cloth correction (the existing `correcting` route, one Haiku call), so it
     ends as `own_cloth.surface`;
   - (c) queue "Describe it again" with the word as a hint.
   This changes DECISIONS:1161 and 1179, which agents may not change themselves (AGENTS.md "Follow the decisions").
2. **Handle Claude's `surface: null` (T5(i))**: draw plain (method returns None for no surface on a new-schema
   answer, `tag_schema_version >= 6`), or retry the description once.
3. **Old items.** Run the read-only check below against a *copy* of the owner's closet (or a backup), with the app
   closed. Then:
   - if it shows **zero** rows routed "MEASURED", and no measured-kept rows they care about, removal is safe for data;
   - otherwise, either re-describe those items once (about 2 US cents each on Sonnet; this needs the owner's
     go-ahead, since DECISIONS:1164 says nothing is sent again by itself), or change `method` so that items without
     a surface **keep their stored `pattern_fill` and are never re-marked** (`mark` must then not clear it, and
     `stale` / `remeasure` and the T6/T8 re-mark must skip them).
4. Remove `patjobs.stale` and `jobs.remeasure` in the same change, and update DECISIONS 1077-1121, README and the
   tests (replace the override test in `test_described_surface.py:133-136` per decision 1).

### The read-only check (tested on a synthetic closet built from the migrations; not run on real data)

The file is at `patterns-check.sql`.
The closet is `~/Closet/closet.db` (or `$CLOSET_DATA_DIR/closet.db`, config.py:64). Run it on a copy:

```
python3 -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro', uri=True); [print(r) for s in open(sys.argv[2]).read().split(';') if s.strip() for r in c.execute(s)]" closet-copy.db check.sql
```

(or `sqlite3 -readonly closet-copy.db < check.sql`). The core query:

```sql
SELECT pattern, route, COUNT(*) FROM (
  SELECT pattern,
    CASE
      WHEN json_extract(own_cloth, '$.surface.kind') IN ('plain','stripes','plaid','blocks','other') THEN 'described (owner cloth)'
      WHEN tag_answer IS NULL THEN 'MEASURED: never described, word set by the owner'
      WHEN json_type(tag_answer, '$.pattern') IS NOT NULL AND json_extract(tag_answer, '$.pattern') IS NOT pattern
        THEN 'MEASURED: owner word differs from Claude''s'
      WHEN json_extract(tag_answer, '$.surface.kind') IN ('plain','stripes','plaid','blocks','other') THEN 'described'
      WHEN json_type(tag_answer, '$.surface') = 'null' THEN 'MEASURED: Claude left surface null'
      ELSE 'MEASURED: answer from before the surface'
    END AS route
  FROM items WHERE pattern IN ('stripe','plaid')
) GROUP BY pattern, route ORDER BY route;
```

`check.sql` also lists each such item (id, category, who set the word, Claude's word and surface, the kept kind and
"how"). It also lists the items drawn **today** from a measured stripe or plaid (pattern_fill not described, panels
or bands): those would change look if re-marked. It prints ids and categories only, not names, so the output can
be shared.

The demo closet tells nothing here: it is never measured, and its plaid comes from made-up tiles. Its `items.json`
answers have no surface, but that never reaches the measured path in the demo.

## Bottom line

Keep the measured path for now. It is reachable today by:
- (1) the Pattern chip or a sentence that changes the word, for any item, new or old;
- (2) Claude returning a null surface on a new item;
- (3) the background remeasure and recheck, plus "Try the cutout again" and undo, on items described before 18 Nov.

It can be removed with high confidence once: the owner decides what an owner-set stripe/plaid word draws (and
DECISIONS 1161/1179/1164 are updated); a null surface draws plain; and the check above shows no old items still
routed to measuring, or those items are re-described or frozen on their stored pattern. The stored-pattern reader
(`stored.py`, `fills`), `prints`, `masks`, `described`, `surface`, landmarks and about 220 lines of
straighten/stripes must stay.
