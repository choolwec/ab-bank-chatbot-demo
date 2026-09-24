"""Free-text intent matching (§3.1B) — fully local, $0.

Pipeline position: runs only after guards and priority flows. Scoring blends
TF-IDF over character n-grams (robust to misspellings) with fuzzy string
ratios, then takes the best phrase score per intent.
"""

import re

import yaml
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config, guards


# Punctuation carries no meaning for matching but costs score: "what are your
# opening hours?" scored 0.686 against the exact phrase without the "?".
_PUNCT_RE = re.compile(r"[^\w\s']+")


def normalise(text: str) -> str:
    return " ".join(_PUNCT_RE.sub(" ", (text or "").lower()).split())


# C10's clause splitter (router._two_questions uses it too).
CLAUSE_SPLIT_RE = re.compile(r"\?|\band\b|\balso\b", re.IGNORECASE)
CLAUSE_MIN_WORDS = 3
# For negation, commas and "but" end a clause as well, and "instead of X" /
# "rather than X" mean "not X".
_NEG_SPLIT_RE = re.compile(CLAUSE_SPLIT_RE.pattern + r"|[,;.!]|\bbut\b", re.IGNORECASE)
_NOT_MARKER_RE = re.compile(r"\b(?:instead\s+of|rather\s+than)\b", re.IGNORECASE)


def drop_negated_clauses(text: str) -> str:
    """ "I don't want a loan, I want to open an account" -> "I want to open an
    account". A clause matching guards.NEGATED_REQUEST_RE is dropped, but only
    when what is left still has CLAUSE_MIN_WORDS words; otherwise (a single
    clause, or everything negated) the text is scored unchanged. Deterministic,
    and applied in both matcher modes: the embedding reads the negated clause
    as a second topic, and the character scorer as extra matching words."""
    marked = _NOT_MARKER_RE.sub(", not", text or "")
    clauses = [c.strip() for c in _NEG_SPLIT_RE.split(marked) if c and c.strip()]
    if len(clauses) < 2:
        return text
    kept = [c for c in clauses if not guards.NEGATED_REQUEST_RE.search(c)]
    if len(kept) == len(clauses) or len(" ".join(kept).split()) < CLAUSE_MIN_WORDS:
        return text
    return " ".join(kept)


def calibrated(emb: float) -> float:
    """Map an embedding similarity onto the decision scale the router, eval
    and gates already use: EMB_MEDIUM -> MEDIUM_CONFIDENCE, EMB_HIGH ->
    HIGH_CONFIDENCE, piecewise-linear and monotone (N3/N5)."""
    hi, med = config.EMB_HIGH, config.EMB_MEDIUM
    HI, MED = config.HIGH_CONFIDENCE, config.MEDIUM_CONFIDENCE
    if emb >= hi:
        return min(1.0, HI + (emb - hi) * (1.0 - HI) / max(1e-9, 1.0 - hi))
    if emb >= med:
        return MED + (emb - med) * (HI - MED) / max(1e-9, hi - med)
    return max(0.0, emb * MED / max(1e-9, med))


class Matcher:
    """Character matcher, optionally with local embeddings (N3).

    Character mode (default, and whenever the model is off, missing or
    unverified): exactly the pre-N3 scoring.
    Hybrid mode: RANK by 0.5 * character + 0.5 * embedding similarity; the
    returned score -- used for the answer / did-you-mean / fallback decision --
    is the top-ranked intents' embedding similarity mapped through
    calibrated(), so EMB_HIGH / EMB_MEDIUM act as the thresholds.
    """

    def __init__(self, use_embeddings: bool | None = None, embedder=None) -> None:
        self._want_embeddings = use_embeddings
        self._embedder_override = embedder
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
                    phrases.append(normalise(str(p)))
                    owners.append(name)
        if not phrases:
            raise RuntimeError(f"no intent phrases found under {config.INTENTS_DIR}")
        self._phrases = phrases
        self._owners = owners
        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        self._matrix = self._vec.fit_transform(phrases)
        self._embedder = None
        self._phrase_vecs = None
        want = config.embeddings_enabled() if self._want_embeddings is None else self._want_embeddings
        if want:
            from . import embedder as embedder_mod

            self._embedder = self._embedder_override or embedder_mod.load()
            if self._embedder is not None:
                self._phrase_vecs = self._cached_phrase_vectors(phrases)
                import numpy as np

                # per-intent maxima in numpy: phrases grouped by owner
                names = list(dict.fromkeys(owners))
                self._owner_names = names
                self._owner_index = np.array([names.index(o) for o in owners])

    def _cached_phrase_vectors(self, phrases):
        """Phrase embeddings, cached on disk by (model, phrases) hash so a
        normal start-up doesn't re-embed every phrase (N3: start-up < 3 s)."""
        import hashlib

        import numpy as np

        key = hashlib.sha256(
            ("\n".join(phrases) + "|" + "|".join(sorted(config.EMBED_MODEL_SHA256.values()))).encode()
        ).hexdigest()[:24]
        cache = config.EMBED_MODEL_DIR / "cache" / f"phrases-{key}.npy"
        if self._embedder_override is None and cache.exists():
            try:
                vecs = np.load(cache)
                if vecs.shape[0] == len(phrases):
                    return vecs
            except (OSError, ValueError):
                pass
        vecs = self._embedder.embed_many(phrases)
        if self._embedder_override is None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                np.save(cache, vecs)
            except OSError:
                pass
        return vecs

    @property
    def mode(self) -> str:
        return "hybrid" if self._phrase_vecs is not None else "char"

    def get(self, name: str) -> dict | None:
        return self.intents.get(name)

    def _char_scores(self, q: str) -> dict[str, float]:
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
        return best

    def _emb_scores(self, q: str) -> dict[str, float]:
        import numpy as np

        sims = self._phrase_vecs @ self._embedder.embed([q])[0]
        best = np.full(len(self._owner_names), -1.0)
        np.maximum.at(best, self._owner_index, sims)
        return dict(zip(self._owner_names, best.tolist()))

    def detail(self, text: str) -> dict:
        """Both scorers for every intent (shadow mode, N4; calibration, N5)."""
        q = normalise(drop_negated_clauses(text))
        if not q:
            return {"char": {}, "emb": {}}
        return {"char": self._char_scores(q), "emb": self._emb_scores(q) if self.mode == "hybrid" else {}}

    def match(self, text: str, top_n: int = 5) -> list[tuple[str, float]]:
        q = normalise(drop_negated_clauses(text))
        if not q:
            return []
        char = self._char_scores(q)
        if self.mode == "char":
            return sorted(char.items(), key=lambda kv: -kv[1])[:top_n]
        emb = self._emb_scores(q)
        exact = {n for n, sc in char.items() if sc >= 1.0}  # an exact phrase stays certain
        hybrid = {n: 0.5 * char.get(n, 0.0) + 0.5 * e for n, e in emb.items()}
        ranked = sorted(hybrid, key=lambda n: -hybrid[n])[:top_n]
        return [(n, 1.0 if n in exact else calibrated(emb[n])) for n in ranked]
