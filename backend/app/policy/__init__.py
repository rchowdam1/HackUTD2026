"""Policy files: policy/<version>/{rules,lexicon,templates}.yaml."""
from __future__ import annotations

import yaml

from app import ROOT

VERSION = "v1.0"


def load(name: str, version: str = VERSION) -> dict:
    return yaml.safe_load((ROOT / "policy" / version / f"{name}.yaml").read_text(encoding="utf-8"))
