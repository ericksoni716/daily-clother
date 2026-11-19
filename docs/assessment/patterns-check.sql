-- Read-only. Which items the measured stripes/plaid path would take (now or on the next re-measure), and which
-- items are drawn today from a pattern the measured path produced.
SELECT
  id, category, pattern, status, pattern_state,
  json_extract(source, '$.pattern')        AS pattern_set_by,      -- 'user' = the owner chose the word
  json_extract(tag_answer, '$.pattern')    AS claude_pattern,
  json_extract(tag_answer, '$.surface.kind') AS claude_surface,
  json_extract(own_cloth, '$.surface.kind')  AS own_surface,
  tag_schema_version,
  json_extract(pattern_fill, '$.kind')     AS kept_kind,
  json_extract(pattern_fill, '$.how')      AS kept_how,
  CASE
    WHEN json_extract(own_cloth, '$.surface.kind') IN ('plain','stripes','plaid','blocks','other') THEN 'described (owner cloth)'
    WHEN tag_answer IS NULL THEN 'MEASURED: never described, word set by the owner'
    WHEN json_type(tag_answer, '$.pattern') IS NOT NULL AND json_extract(tag_answer, '$.pattern') IS NOT pattern
      THEN 'MEASURED: owner word differs from Claude''s'
    WHEN json_extract(tag_answer, '$.surface.kind') IN ('plain','stripes','plaid','blocks','other') THEN 'described'
    WHEN json_type(tag_answer, '$.surface') = 'null' THEN 'MEASURED: Claude left surface null'
    ELSE 'MEASURED: answer from before the surface'
  END AS route
FROM items
WHERE pattern IN ('stripe', 'plaid')
ORDER BY route, pattern;

-- Summary: how many patterned items take each route.
SELECT route, pattern, COUNT(*) FROM (
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
  FROM items WHERE pattern IN ('stripe', 'plaid')
) GROUP BY route, pattern ORDER BY route;

-- Items drawn today from a pattern the measured path made (kept stripes with an orientation are measured unless
-- they are bands across the body, which carry sleeves_banded = true and no trim, and described tiles say how 'described').
SELECT id, category, pattern, json_extract(pattern_fill, '$.kind') AS kind, json_extract(pattern_fill, '$.how') AS how
FROM items
WHERE pattern IN ('stripe', 'plaid') AND pattern_fill IS NOT NULL
  AND coalesce(json_extract(pattern_fill, '$.how'), '') NOT IN ('described', 'panels')
  AND NOT coalesce(json_extract(pattern_fill, '$.kind') = 'stripes'
                    AND json_extract(tag_answer, '$.surface.kind') = 'blocks', 0);
