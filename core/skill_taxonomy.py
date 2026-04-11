from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class SkillTaxonomy:
    def __init__(self, taxonomy_path: str):
        self.path = Path(taxonomy_path)
        self.skills: Dict[str, dict] = {}

    async def load(self) -> None:
        self.skills = json.loads(self.path.read_text(encoding="utf-8"))

    async def search(self, q: str) -> list[dict]:
        query = q.lower().strip()
        out = []
        for canonical, payload in self.skills.items():
            aliases = payload.get("aliases", [])
            if query in canonical.lower() or any(query in a.lower() for a in aliases):
                out.append({"skill": canonical, **payload})
        return out
