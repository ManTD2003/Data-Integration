from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
STAGING = DATA / "staging"

for _p in (RAW, STAGING):
    _p.mkdir(parents=True, exist_ok=True)
