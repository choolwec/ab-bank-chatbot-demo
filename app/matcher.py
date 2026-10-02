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


# Text-speak and common misspellings, word by word, for phrases and
# messages alike ("hw r u", "wats ur number", "tnx", "open acc pls").
_SPELLING = {
    "u": "you", "ur": "your", "r": "are", "hw": "how", "wat": "what", "wot": "what", "wht": "what",
    "wats": "whats", "whts": "whats", "pls": "please", "plz": "please", "plse": "please", "plis": "please",
    "thnx": "thanks", "thnks": "thanks", "tnx": "thanks", "thx": "thanks", "thanx": "thanks", "ty": "thanks",
    "tq": "thanks", "sum1": "someone", "sm1": "someone", "smone": "someone", "acc": "account",
    "acct": "account", "accnt": "account", "acount": "account", "accout": "account", "acoount": "account",
    "accounr": "account", "accs": "accounts", "acounts": "accounts", "tamnga": "tamanga", "tamaga": "tamanga",
    "tamanaga": "tamanga", "etumbaa": "etumba", "savngs": "savings", "savigs": "savings", "lon": "loan",
    "lones": "loans", "abt": "about", "wen": "when", "whr": "where", "wer": "where", "hv": "have",
    "cn": "can", "2day": "today", "2moro": "tomorrow", "tmrw": "tomorrow", "ppl": "people", "coz": "because",
    "bcoz": "because", "2": "to", "4": "for", "lsk": "lusaka", "brnch": "branch", "branc": "branch", "nmbr": "number", "numba": "number",
}


def normalise(text: str) -> str:
    words = _PUNCT_RE.sub(" ", (text or "").lower()).split()
    return " ".join(_SPELLING.get(w, w) for w in words)


# Greetings and politeness around a request ("hi, where is the kitwe branch
# please"). They are set aside before matching, so "hi how are you" is small
# talk and "hello i need a loan" is a loan question. A message that is ONLY a
# greeting is the greeting intent (its own phrases).
_GREETING = (r"(?:hi+|hello+|helo|hallo|hey+|hie|howdy|greetings|dear|yo|"
             r"good\s+(?:morning|afternoon|evening|day)|morning|afternoon|evening)")
# After a greeting only: "hi there", "hello sir" -- "there is an odd
# withdrawal" keeps its "there".
_ADDRESSEE = r"(?:there|sir|madam|mam|maam|boss|ba|bro|team|bot|ab\s+bank|abbank|guys)"
_POLITE = r"(?:please|pls|plz|kindly|excuse\s+me|sorry\s+to\s+bother(?:\s+you)?)"
_LEAD_SOCIAL_RE = re.compile(
    rf"^(?:(?:{_GREETING}(?:\s+{_ADDRESSEE})*|{_POLITE})\s+)+")
_TRAIL_SOCIAL_RE = re.compile(
    r"(?:\s+(?:please|pls|plz|sir|madam|mam|boss|ba|bot|team))+$")


# "tell me about tamanga", "what about the savings plan", "info on etumba":
# a lead-in before a topic. What is left is looked up as a WHOLE phrase only.
_TOPIC_LEAD_RE = re.compile(
    r"^(?:(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:tell|show)\s+me\s+(?:more\s+)?about|"
    r"(?:i\s+(?:want|would\s+like|wanna)\s+to\s+know|i\s+need\s+(?:info|information))\s+(?:more\s+)?about|"
    r"(?:more\s+)?(?:info|information|details)\s+(?:on|about)|what\s+about|how\s+about|explain|"
    r"what\s+is|what\s+s|whats|what\s+are)\s+(?:the\s+|your\s+|a\s+|an\s+)?")


def topic_of(q: str) -> str:
    """ "tell me about the tamanga plus" -> "tamanga plus"; else ""."""
    core = _TOPIC_LEAD_RE.sub("", q, count=1).strip()
    return core if core != q else ""


# "my name is mary and i want to open a savings account": the introduction
# goes, the request stays. Only with "and" or a comma after the name, so
# "i am a market trader..." keeps its meaning.
_INTRO_RE = re.compile(
    r"^(?:my\s+name\s+is|my\s+names\s+is|this\s+is|i\s+am|i'?m|im)\s+[a-z'-]+(?:\s+[a-z'-]+)?\s+and\s+")


def strip_social(q: str) -> str:
    """ "hi there how are you" -> "how are you"; "" when it was all greeting."""
    q = _LEAD_SOCIAL_RE.sub("", q + " ").strip()
    q = _INTRO_RE.sub("", q + " ").strip()
    return _TRAIL_SOCIAL_RE.sub("", q).strip()


_REDACTED_RE = re.compile(
    r"(?i)(?:\b(?:my\s+)?(?:account|acc|card|nrc|pin|password)\s*(?:number|no\.?|#)?\s*(?:is|:)?\s*)?"
    r"\[[A-Z ]*REDACTED\]")


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
        # `match: exact` intents (small talk: "how are you", "ok") answer only
        # the whole message, and stay out of the scored index so they never
        # pull a real question their way or shift its weights.
        self._exact: dict[str, str] = {}
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
                # `exact_phrases`: more whole-message wordings for any intent,
                # outside the scored index (they never shift its weights).
                exact = list(item.get("exact_phrases", []))
                if item.get("match") == "exact":
                    exact += item.get("phrases", [])
                for p in exact:
                    key = normalise(str(p))
                    if self._exact.get(key, name) != name:
                        raise ValueError(f"exact phrase {p!r} is claimed by {self._exact[key]} and {name}")
                    self._exact[key] = name
                if item.get("match") == "exact":
                    continue
                for p in item.get("phrases", []):
                    phrases.append(normalise(str(p)))
                    owners.append(name)
        if not phrases:
            raise RuntimeError(f"no intent phrases found under {config.INTENTS_DIR}")
        self._phrases = phrases
        self._owners = owners
        self._phrase_owner: dict[str, str] = {}
        for p, o in zip(phrases, owners):
            self._phrase_owner.setdefault(p, o)
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
        text = _REDACTED_RE.sub(" ", text or "")  # "my account number is [ACCOUNT REDACTED] i want a loan"
        q = normalise(drop_negated_clauses(text))
        if not q:
            return []
        if q in self._exact:
            return [(self._exact[q], 1.0)]
        core = strip_social(q)
        if core != q:
            if not core:
                return [("greeting", 1.0)] if "greeting" in self.intents else []
            if core in self._exact:
                return [(self._exact[core], 1.0)]
            if len(core.split()) >= 2:  # "good morning bank" stays as typed
                q = core
        topic = topic_of(q) if q not in self._phrase_owner else ""
        if topic:
            owner = self._exact.get(topic) or self._phrase_owner.get(topic)
            if owner:
                return [(owner, 1.0)]
        char = self._char_scores(q)
        if self.mode == "char":
            return sorted(char.items(), key=lambda kv: -kv[1])[:top_n]
        emb = self._emb_scores(q)
        exact = {n for n, sc in char.items() if sc >= 1.0}  # an exact phrase stays certain
        hybrid = {n: 0.5 * char.get(n, 0.0) + 0.5 * e for n, e in emb.items()}
        ranked = sorted(hybrid, key=lambda n: -hybrid[n])[:top_n]
        return [(n, 1.0 if n in exact else calibrated(emb[n])) for n in ranked]
