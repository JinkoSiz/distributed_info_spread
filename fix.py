import json
import pathlib
import re

root = pathlib.Path("archive")
for p in root.rglob("experiment_*.json"):
    alg = re.match(r"([a-z_]+)_", p.parent.name).group(1)
    data = json.loads(p.read_text())
    for rec in data:
        rec["algorithm"] = alg
    p.write_text(json.dumps(data, indent=2))
