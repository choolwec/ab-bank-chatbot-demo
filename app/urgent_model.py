"""A second, model-based urgent check (ticket N7).

The keyword rules in guards.urgent_scan() are the primary net. This is a
second one: a message whose embedding is within EMB_URGENT of one of the
exemplar fraud reports (knowledge/urgent_exemplars.yaml) is routed like a
SOFT signal -- the customer is asked "Do you want to report it as fraud?" --
even when no rule fired. Either check can trigger the fraud path; neither
can suppress the other, and this one can never start a flow by itself.

Active when the embedding model is present and verified, and
URGENT_MODEL_ENABLED isn't turned off. Without the model it simply says no.
"""

import threading

import yaml

from . import config, embedder

EXEMPLARS_FILE = config.KNOWLEDGE_DIR / "urgent_exemplars.yaml"
_lock = threading.Lock()
_vectors = None
_loaded = False


def enabled() -> bool:
    return config.flag("URGENT_MODEL_ENABLED", True)


def _exemplar_vectors():
    global _vectors, _loaded
    with _lock:
        if not _loaded:
            _loaded = True
            model = embedder.load()
            if model is not None:
                texts = yaml.safe_load(EXEMPLARS_FILE.read_text(encoding="utf-8"))["exemplars"]
                _vectors = model.embed_many([str(t) for t in texts])
        return _vectors


def similarity(text: str) -> float | None:
    """Highest similarity to any exemplar, or None without the model."""
    vectors = _exemplar_vectors()
    if vectors is None:
        return None
    model = embedder.load()
    return float((vectors @ model.embed([text])[0]).max())


# Short messages are commands and answers ("cancel", "yes", "2"), not the
# described reports the rules miss: "cancel" alone is close to the exemplar
# "cancel my card". The rules still see every message.
MIN_WORDS = 4


def flags(text: str) -> bool:
    if not enabled() or not text or len(text.split()) < MIN_WORDS:
        return False
    score = similarity(text)
    return score is not None and score >= config.EMB_URGENT
