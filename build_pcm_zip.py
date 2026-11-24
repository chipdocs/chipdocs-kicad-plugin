#!/usr/bin/env python3
"""Build a KiCad PCM-compliant ZIP archive and repository.json manifest."""
import hashlib
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
os.makedirs(DIST, exist_ok=True)
ZIP_PATH = os.path.join(DIST, "org.chipdocs.kicad-1.0.0.zip")

with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(os.path.join(ROOT, "metadata.json"), "metadata.json")
    for fname in ("__init__.py", "chipdocs_action.py"):
        zf.write(os.path.join(ROOT, "plugins", fname), f"plugins/{fname}")

with open(ZIP_PATH, "rb") as f:
    raw = f.read()
sha256 = hashlib.sha256(raw).hexdigest()
size = len(raw)

meta = json.load(open(os.path.join(ROOT, "metadata.json"), "r", encoding="utf-8"))
meta["versions"][0].update(
    {
        "download_sha256": sha256,
        "download_size": size,
        "download_url": "https://github.com/chipdocs/chipdocs-kicad-plugin/releases/download/v1.0.0/org.chipdocs.kicad-1.0.0.zip",
        "install_size": size,
    }
)
with open(os.path.join(DIST, "packages.json"), "w", encoding="utf-8") as f:
    json.dump({"packages": [meta]}, f, indent=2)

print(f"Built {ZIP_PATH} ({size} bytes, sha256={sha256})")
