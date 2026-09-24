"""Local sentence embeddings for the matcher (ticket N3).

all-MiniLM-L6-v2 (Apache-2.0, 22M parameters) run on CPU with onnxruntime
(MIT) and tokenizers (Apache-2.0): mean pooling over tokens, L2-normalised.
Nothing leaves the machine -- this is a local, non-generative model (Tier 2
in the excellence plan), not an LLM.

load() returns None -- and the matcher keeps its character scoring -- when
the files are missing, a sha256 doesn't match config.EMBED_MODEL_SHA256, or
the runtime isn't installed. A wrong hash is logged as an error: the app
never runs a model it can't verify.
"""

import hashlib
import logging
import threading

from . import config

log = logging.getLogger("abz.embedder")
MAX_TOKENS = 128
_lock = threading.Lock()
_cached = None
_attempted = False


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(model_dir=None) -> bool:
    model_dir = model_dir or config.EMBED_MODEL_DIR
    for rel, expected in config.EMBED_MODEL_SHA256.items():
        path = model_dir / rel
        if not path.exists():
            return False
        if _sha256(path) != expected:
            log.error("embedding model file %s failed its sha256 check: refusing to use it", rel)
            return False
    return True


class Embedder:
    def __init__(self, model_dir) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._np = np
        self._tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tok.enable_truncation(max_length=MAX_TOKENS)
        self._tok.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self._sess = ort.InferenceSession(
            str(model_dir / "onnx" / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._sess.get_inputs()}
        self._run_lock = threading.Lock()

    def embed_many(self, texts: list[str], batch: int = 32):
        """Embed a long list in small batches: one huge batch pads every
        phrase to the longest, which doubled the start-up time."""
        np = self._np
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return np.vstack([self.embed(texts[i:i + batch]) for i in range(0, len(texts), batch)])

    def embed(self, texts: list[str]):
        np = self._np
        enc = self._tok.encode_batch([t.lower() for t in texts])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)
        with self._run_lock:
            tokens = self._sess.run(None, feeds)[0]
        m = mask[..., None].astype(np.float32)
        vec = (tokens * m).sum(1) / np.clip(m.sum(1), 1e-9, None)  # mean pooling
        return vec / np.clip(np.linalg.norm(vec, axis=1, keepdims=True), 1e-9, None)


def load(model_dir=None):
    """The shared Embedder, or None if it can't be used safely."""
    global _cached, _attempted
    with _lock:
        if _attempted and model_dir is None:
            return _cached
        directory = model_dir or config.EMBED_MODEL_DIR
        embedder = None
        if verify(directory):
            try:
                embedder = Embedder(directory)
            except Exception:  # runtime missing or model unreadable
                log.exception("embedding model could not be loaded")
        if model_dir is None:
            _cached, _attempted = embedder, True
        return embedder


def available() -> bool:
    return load() is not None
