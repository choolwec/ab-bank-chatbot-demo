"""Current matcher vs small local models on phrasings the bot has never seen.

    python research/matcher-benchmark/bench_matcher.py            # current matcher only
    MINILM_DIR=/path/to/all-MiniLM-L6-v2 python research/...      # + small-model variants

MINILM_DIR must contain tokenizer.json and onnx/model.onnx (sentence-transformers
all-MiniLM-L6-v2 exported to ONNX). The model variants also need
`pip install onnxruntime tokenizers` — research-only deps, deliberately not in
requirements.txt. Reads knowledge/intents/*.yaml through app.matcher; writes
nothing. See README.md in this folder for results and caveats.
"""

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(HERE), str(ROOT)]

from app import config  # noqa: E402
from app.matcher import Matcher  # noqa: E402
import yaml  # noqa: E402

# The held-out set moved to tests/eval/heldout.yaml (ticket E3), where the
# CI evaluation gates read it too.
_HELDOUT = yaml.safe_load((ROOT / "tests" / "eval" / "heldout.yaml").read_text(encoding="utf-8"))
IN_SCOPE = [(c["text"], c["intent"]) for c in _HELDOUT["in_scope"]]
OUT_OF_SCOPE = [c["text"] for c in _HELDOUT["out_of_scope"]]

matcher = Matcher()
intents = sorted(set(matcher._owners))


def top(scores):
    name = max(scores, key=scores.get)
    return name, scores[name]


def current(text):
    return top(dict(matcher.match(text, top_n=len(intents))))


def operating_point(ins, oos, thr):
    """(answered right, answered wrong, OOS answered) at confidence >= thr."""
    right = sum(p == g and s >= thr for (p, s), g in ins) / len(ins)
    wrong = sum(p != g and s >= thr for (p, s), g in ins) / len(ins)
    oos_hit = sum(s >= thr for _, s in oos) / len(oos)
    return right, wrong, oos_hit


def evaluate(fn):
    return [(fn(t), g) for t, g in IN_SCOPE], [fn(t) for t in OUT_OF_SCOPE]


systems = {"current (tfidf+fuzzy)": current}

model_dir = os.environ.get("MINILM_DIR")
if model_dir:
    import numpy as np
    import onnxruntime as ort
    from sklearn.linear_model import LogisticRegression
    from tokenizers import Tokenizer

    mdir = pathlib.Path(model_dir)
    tok = Tokenizer.from_file(str(mdir / "tokenizer.json"))
    tok.enable_truncation(max_length=128)
    tok.enable_padding()
    sess = ort.InferenceSession(str(mdir / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"])
    input_names = {i.name for i in sess.get_inputs()}

    def embed(texts):
        enc = tok.encode_batch([t.lower() for t in texts])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        tokens = sess.run(None, feeds)[0]
        m = mask[..., None].astype(np.float32)
        vec = (tokens * m).sum(1) / np.clip(m.sum(1), 1e-9, None)  # mean pooling
        return vec / np.linalg.norm(vec, axis=1, keepdims=True)

    a, b, c = embed(["i lost my card", "my bank card is missing", "what time do you open"])
    print(f"model sanity check: sim(paraphrase)={a @ b:.2f} sim(unrelated)={a @ c:.2f}")

    P = embed(matcher._phrases)
    owner_idx = {n: [i for i, o in enumerate(matcher._owners) if o == n] for n in intents}
    clf = LogisticRegression(C=10.0, max_iter=5000).fit(P, matcher._owners)

    def emb_scores(text):
        sims = P @ embed([text])[0]
        return {n: float(sims[ix].max()) for n, ix in owner_idx.items()}

    def hybrid_scores(text):
        e = emb_scores(text)
        c = dict(matcher.match(text, top_n=len(intents)))
        return {n: 0.5 * e[n] + 0.5 * c.get(n, 0.0) for n in intents}, e

    def gated(text):
        # rank with both scorers; decide answer-vs-abstain on the embedding score
        h, e = hybrid_scores(text)
        name = max(h, key=h.get)
        return name, e[name]

    def supervised(text):
        p = clf.predict_proba(embed([text]))[0]
        return top(dict(zip(clf.classes_, map(float, p))))

    systems.update({
        "MiniLM embeddings": lambda t: top(emb_scores(t)),
        "hybrid 50/50": lambda t: top(hybrid_scores(t)[0]),
        "hybrid rank + embed gate": gated,
        "supervised head (LR)": supervised,
    })

print(f"\n{len(IN_SCOPE)} in-scope phrasings, {len(OUT_OF_SCOPE)} out-of-scope\n")
print(f"{'system':26s} {'top-1':>6s} {'ms/q':>5s} | at <=10% OOS answered: {'right':>6s} {'WRONG':>6s} {'OOS':>5s}")
results = {}
for name, fn in systems.items():
    t0 = time.perf_counter()
    ins, oos = evaluate(fn)
    ms = (time.perf_counter() - t0) / (len(IN_SCOPE) + len(OUT_OF_SCOPE)) * 1000
    results[name] = (ins, oos)
    acc = sum(p == g for (p, _), g in ins) / len(ins)
    thr = sorted(s for _, s in oos)[int(0.9 * len(oos))] + 1e-6  # lets <=10% of OOS through
    r, w, f = operating_point(ins, oos, thr)
    print(f"{name:26s} {acc:6.1%} {ms:5.1f} | thr={thr:4.2f}              {r:6.1%} {w:6.1%} {f:5.1%}")

ins, oos = results["current (tfidf+fuzzy)"]
print(f"\ncurrent matcher at production thresholds:")
for thr, label in ((config.HIGH_CONFIDENCE, "direct answer"), (config.MEDIUM_CONFIDENCE, "did-you-mean")):
    r, w, f = operating_point(ins, oos, thr)
    print(f"  >= {thr:.2f} {label:13s}  right {r:6.1%}  wrong {w:6.1%}  OOS let through {f:6.1%}")
print("\nout-of-scope questions it answers DIRECTLY today:")
for text, (pred, score) in zip(OUT_OF_SCOPE, oos):
    if score >= config.HIGH_CONFIDENCE:
        print(f"  {score:.2f}  {text!r} -> {pred}")
