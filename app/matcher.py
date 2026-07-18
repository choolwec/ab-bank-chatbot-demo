"""Free-text intent matching (§3.1B) — fully local, $0.

Pipeline position: runs only after guards and priority flows. Scoring blends
TF-IDF over character n-grams (robust to misspellings) with fuzzy string
ratios, then takes the best phrase score per intent.
"""

import yaml
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config


class Matcher:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self.intents: dict[str, dict] = {}
        phrases: list[str] = []
        owners: list[str] = []
        for path in sorted(config.INTENTS_DIR.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            items = data.get("intents", []) if isinstance(data, dict) else (data or [])
            for item in items:
                name = item["intent"]
                if name in self.intents:
                    raise ValueError(f"duplicate intent id: {name} ({path.name})")
                item["_source"] = path.name
                self.intents[name] = item
                for p in item.get("phrases", []):
                    phrases.append(str(p).lower().strip())
                    owners.append(name)
        if not phrases:
            raise RuntimeError(f"no intent phrases found under {config.INTENTS_DIR}")
        self._phrases = phrases
        self._owners = owners
        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        self._matrix = self._vec.fit_transform(phrases)

    def get(self, name: str) -> dict | None:
        return self.intents.get(name)

    def match(self, text: str, top_n: int = 5) -> list[tuple[str, float]]:
        q = " ".join((text or "").lower().split())
        if not q:
            return []
        sims = cosine_similarity(self._vec.transform([q]), self._matrix)[0]
        best: dict[str, float] = {}
        for i, owner in enumerate(self._owners):
            phrase = self._phrases[i]
            if q == phrase:
                score = 1.0
            else:
                fuzzy = max(fuzz.ratio(q, phrase), fuzz.token_sort_ratio(q, phrase)) / 100.0
                score = 0.6 * float(sims[i]) + 0.4 * fuzzy
            if score > best.get(owner, 0.0):
                best[owner] = score
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        return ranked[:top_n]
