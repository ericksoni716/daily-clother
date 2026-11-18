"""Ask Claude (the app's plan route, the app's describing model) for the app's full description of an item WITH the
experimental plaid fields added, on the cutout the app would send. Records usage.
usage (from backend/): PYTHONPATH=. python describe_cli.py out_dir mode cut.png...   mode: plaid | base"""
import json
import subprocess
import sys
import tempfile
import time
import os
from pathlib import Path

from PIL import Image
from pydantic import Field, create_model

from closet.patterns import described
from closet.tagger import claude_cli, tagging
from closet.tagger.tagging import CONFIG, PROMPT, SENT

out_dir, mode = Path(sys.argv[1]), sys.argv[2]
model = CONFIG["roles"]["tagging"]
if mode == "plaid":
    Form = create_model("ItemTagsSentPlaid", __base__=SENT,
                        plaid=(described.PlaidDescription | None, Field(description=described.FIELD_TEXT["plaid"])))
    prompt_core = PROMPT + "\n- Plaid: " + described.GUIDANCE
else:
    Form = SENT
    prompt_core = PROMPT
from anthropic.lib._parse._transform import transform_schema
schema = transform_schema(Form)
effort = CONFIG["models"][model]["effort"]
env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
for name in sys.argv[3:]:
    stem = Path(name).name.split(".")[0]
    with tempfile.TemporaryDirectory() as tmp:
        claude_cli._save(Image.open(name), Path(tmp) / "photo-1.jpg")
        prompt = f"{prompt_core}\n\nThe image file is in the current folder: photo-1.jpg. Open each with the Read tool, then give your answer."
        cmd = claude_cli.print_command(claude_cli.find_claude(), model, effort, schema, "Read", claude_cli.SYSTEM)
        t = time.time()
        with claude_cli.prompt_file(prompt) as stdin:
            proc = subprocess.run(cmd, cwd=tmp, env=env, stdin=stdin, capture_output=True, timeout=300, encoding="utf-8")
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        print(stem, "NO JSON", proc.returncode, proc.stdout[:300], proc.stderr[:300])
        continue
    ans = out.get("structured_output")
    usage = out.get("usage") or {}
    rec = {"photo": stem, "mode": mode, "model": model, "seconds": round(time.time() - t, 1),
           "usage": {k: usage.get(k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")},
           "num_turns": out.get("num_turns"), "is_error": out.get("is_error"), "answer": ans}
    (out_dir / f"{stem}.{mode}.json").write_text(json.dumps(rec, indent=1))
    print(stem, mode, rec["usage"], "turns", rec["num_turns"], "err", rec["is_error"],
          json.dumps((ans or {}).get("plaid")) if mode == "plaid" else (ans or {}).get("pattern"), flush=True)
