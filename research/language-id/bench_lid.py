"""Language-ID benchmark: can we tell a Zambian-language message from English?

Research code, not part of the app or its test suite. It trains a tiny
character n-gram classifier with scikit-learn (already an app dependency)
on openly licensed text and measures, on SHORT chat-style messages:

- how often a Bemba or Nyanja message is flagged as "not English", and
- how often one of our own English phrases is wrongly flagged (the costly
  mistake: an English customer told "I only understand English").

Training data (downloaded through the Hugging Face datasets-server API into
a cache dir, never committed):
- SIB-200 (Davlan/sib200, CC-BY-SA-4.0): Flores-200 sentences for eng,
  bem and nya.
- MT560 sentence pairs (michsethowusu/english-{tonga,lozi}_sentence-pairs_mt560,
  CC-BY-4.0): the Tonga and Lozi side.

Test data:
- Nyanja/English code-switched chat phrases
  (suru8-ai/chichewa_english_code_switch_dataset, Apache-2.0, 247 rows).
- Short Bemba sentences (michsethowusu/bemba-english-emotions-corpus, MIT),
  3-8 words, taken from an offset the classifier never trains on.
- English: every `phrases:` entry in knowledge/intents/*.yaml and every
  held-out text in tests/eval/heldout.yaml (in scope and out of scope).

Usage:
    python research/language-id/bench_lid.py            # cache in research/language-id/.cache
    LID_CACHE=/some/dir python research/language-id/bench_lid.py
"""
from __future__ import annotations

import json
import os
import pickle
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("LID_CACHE", Path(__file__).parent / ".cache"))
API = "https://datasets-server.huggingface.co/rows"


def _rows(dataset: str, config: str, split: str, offset: int, total: int) -> list[dict]:
    """Page through the datasets-server rows API (100 rows per call), cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"{dataset.replace('/', '__')}.{config}.{split}.{offset}.{total}.json"
    if key.exists():
        return json.loads(key.read_text(encoding="utf-8"))
    out: list[dict] = []
    while len(out) < total:
        q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": split,
                                    "offset": offset + len(out),
                                    "length": min(100, total - len(out))})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                    page = json.load(r)["rows"]
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 5:
                    raise
                time.sleep(5 * 2 ** attempt)   # the public API rate-limits
        time.sleep(1)
        if not page:
            break
        out += [p["row"] for p in page]
    key.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _text_col(row: dict, prefer: tuple[str, ...]) -> str:
    for k in prefer:
        if k in row and isinstance(row[k], str):
            return row[k]
    return next(v for v in row.values() if isinstance(v, str))


def training_data() -> tuple[list[str], list[str]]:
    X, y = [], []
    for lang, cfg in (("eng", "eng_Latn"), ("bem", "bem_Latn"), ("nya", "nya_Latn")):
        for split, n in (("train", 701), ("validation", 99)):
            for row in _rows("Davlan/sib200", cfg, split, 0, n):
                X.append(row["text"])
                y.append(lang)
    for lang, name in (("toi", "tonga"), ("loz", "lozi")):
        rows = _rows(f"michsethowusu/english-{name}_sentence-pairs_mt560", "default", "train", 0, 800)
        for row in rows:
            other = [k for k in row if k.lower() not in ("eng", "english", "en") and isinstance(row[k], str)]
            X.append(row[other[0]] if other else _text_col(row, ()))
            y.append(lang)
    return X, y


def english_tests() -> list[str]:
    texts = []
    for f in sorted((ROOT / "knowledge" / "intents").glob("*.yaml")):
        for it in yaml.safe_load(f.read_text(encoding="utf-8")).get("intents", []):
            texts += [str(p) for p in it.get("phrases", []) or []]
    held = yaml.safe_load((ROOT / "tests" / "eval" / "heldout.yaml").read_text(encoding="utf-8"))
    for section in ("in_scope", "out_of_scope"):
        texts += [(i["text"] if isinstance(i, dict) else str(i)) for i in held.get(section, [])]
    return texts


# Phrases in our intent files that are deliberately Bemba/Nyanja greetings or
# thanks: they are *meant* to be recognised, so they are not English errors.
LOCAL_BY_DESIGN = re.compile(r"(?i)\b(bwanji|shani|mulishani|zikomo|natotela|mwaiseni|inde)\b")


# Brand, product and place names are language-neutral: "check etumba balance"
# is English, but "etumba" alone reads as Bantu to a character model. They are
# blanked before classifying (variant "names blanked" below).
NEUTRAL = {"ab", "etumba", "e-tumba", "tumba", "yaka", "tamanga", "kwacha", "zmw", "k",
           "zamtel", "airtel", "mtn", "zesco", "nrc", "atm", "pin", "zambia", "zambian"}


def neutral_words() -> set[str]:
    words = set(NEUTRAL)
    data = json.loads((ROOT / "knowledge" / "branches.json").read_text(encoding="utf-8"))
    for b in data.get("branches", []):
        for k in ("name", "town", "city", "province"):
            if isinstance(b.get(k), str):
                words |= {w.lower() for w in re.findall(r"[A-Za-z-]+", b[k])}
    words -= {"branch", "road", "street", "the", "and", "of", "main", "centre", "center"}
    return words


def blank(texts: list[str], words: set[str]) -> list[str]:
    return [re.sub(r"[A-Za-z-]+", lambda m: "" if m.group(0).lower() in words else m.group(0), t)
            for t in texts]


def local_tests() -> dict[str, list[str]]:
    nya = [r["phrase"].strip() for r in
           _rows("suru8-ai/chichewa_english_code_switch_dataset", "default", "train", 0, 247)]
    bem_raw = _rows("michsethowusu/bemba-english-emotions-corpus", "default", "train", 50_000, 1500)
    bem = [r["Bemba"].strip() for r in bem_raw if 3 <= len(r["Bemba"].split()) <= 8][:300]
    return {"nya (code-switched chat)": nya, "bem (short sentences)": bem}


def matcher_today(local: dict[str, list[str]], p_not_english) -> None:
    """What the live character matcher does with these messages now, and how
    many of its "did you mean" guesses the proposed rule (P >= 0.7, 3+ words) would replace
    with an honest "I understand English best" reply. Direct answers are left
    alone: "Ndikufuna to talk to agent" -> human_handoff is right."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app import config, matcher
    m = matcher.Matcher(use_embeddings=False)
    print("\nCurrent matcher (character mode) on local-language messages:")
    print("| set | direct answer | did you mean | fallback | did-you-means the rule would replace |")
    print("|---|---|---|---|---|")
    for k, texts in local.items():
        probs = p_not_english(texts)
        counts = {"direct": 0, "dym": 0, "fallback": 0}
        replaced = 0
        examples = []
        for t, p in zip(texts, probs):
            top = m.match(t, 1)
            score = top[0][1] if top else 0.0
            kind = ("direct" if score >= config.HIGH_CONFIDENCE else
                    "dym" if score >= config.MEDIUM_CONFIDENCE else "fallback")
            counts[kind] += 1
            if kind == "dym" and p >= 0.7 and len(t.split()) >= 3:
                replaced += 1
            if kind == "direct" and len(examples) < 6:
                examples.append(f"{top[0][0]} <- {t}")
        print(f"| {k} | {counts['direct']} | {counts['dym']} | {counts['fallback']} | "
              f"{replaced} of {counts['dym']} |")
        for e in examples:
            print(f"    direct: {e}")


BLANK = os.environ.get("LID_BLANK_NAMES", "1") == "1"


def main() -> None:
    X, y = training_data()
    clf = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 4), lowercase=True,
                        sublinear_tf=True, min_df=2),
        LogisticRegression(max_iter=2000, C=5.0, class_weight="balanced"),
    )
    t = time.perf_counter()
    clf.fit(X, y)
    print(f"trained on {len(X)} sentences in {time.perf_counter() - t:.1f}s; "
          f"model {len(pickle.dumps(clf)) / 1e6:.1f} MB pickled")
    eng_idx = list(clf.classes_).index("eng")

    eng = [e for e in english_tests() if not LOCAL_BY_DESIGN.search(e)]
    local = local_tests()

    words = neutral_words()

    def p_not_english(texts: list[str]) -> list[float]:
        texts = blank(texts, words) if BLANK else texts
        return [1 - p[eng_idx] if t.strip() else 0.0
                for t, p in zip(texts, clf.predict_proba(texts))]

    t = time.perf_counter()
    pe = p_not_english(eng)
    per_msg_ms = (time.perf_counter() - t) / len(eng) * 1000
    pl = {k: p_not_english(v) for k, v in local.items()}

    print(f"\nEnglish tests: {len(eng)} phrases; "
          + ", ".join(f"{k}: {len(v)}" for k, v in local.items()))
    print(f"latency ~{per_msg_ms:.2f} ms/message (batched)\n")
    print("| rule: flag when P(not English) >= | min words | English wrongly flagged | "
          + " | ".join(f"{k} flagged" for k in local) + " |")
    print("|---|---|---|" + "---|" * len(local))
    for thr in (0.5, 0.7, 0.9):
        for min_words in (1, 3):
            def flagged(texts, probs):
                return sum(1 for s, p in zip(texts, probs) if p >= thr and len(s.split()) >= min_words)
            fe = flagged(eng, pe)
            cells = [f"{flagged(v, pl[k]) / len(v):.1%}" for k, v in local.items()]
            print(f"| {thr} | {min_words} | {fe} / {len(eng)} ({fe / len(eng):.1%}) | " + " | ".join(cells) + " |")

    matcher_today(local, p_not_english)

    thr = 0.7
    worst = sorted(((p, s) for s, p in zip(eng, pe) if p >= thr and len(s.split()) >= 3), reverse=True)
    print(f"\nEnglish phrases flagged at {thr} (3+ words):")
    for p, s in worst[:15]:
        print(f"  {p:.2f}  {s}")
    for k, v in local.items():
        missed = [(p, s) for s, p in zip(v, pl[k]) if p < thr and len(s.split()) >= 3]
        print(f"\n{k}: sample missed at {thr} (3+ words):")
        for p, s in missed[:8]:
            print(f"  {p:.2f}  {s}")


if __name__ == "__main__":
    main()
