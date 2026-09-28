"""Text-to-speech benchmark: can our own CPU server read the bot's answers aloud?

Research code, not part of the app or its test suite. It times two small,
commercially licensed English voices on real answers from knowledge/intents,
and prints how the phonemiser reads the words our answers are full of
(ZMW, NRC, eTumba, 08:00-15:00), which shows why the answers need a spoken
version before any voice reads them.

Models (downloaded by hand, never committed; see README.md):
- Kokoro-82M (Apache-2.0) through kokoro-onnx (MIT): KOKORO_DIR must hold
  kokoro-v1.0.onnx, kokoro-v1.0.int8.onnx (optional) and voices-v1.0.bin.
- Piper (engine GPL-3.0; the en_US-lessac-medium voice): PIPER_VOICE is the
  path to the .onnx file, with its .onnx.json next to it.

    pip install kokoro-onnx piper-tts soundfile
    KOKORO_DIR=... PIPER_VOICE=... python research/voice/bench_tts.py
"""
from __future__ import annotations

import os
import re
import time
import wave
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("TTS_OUT", Path(__file__).parent / ".out"))
THREADS = int(os.environ.get("TTS_THREADS", "4"))

# The words a banking answer is full of, as written for a screen.
TRICKY = ["ZMW 100", "5% per annum", "NRC", "TPIN", "eTumba", "Tamanga",
          "08:00-15:00", "*778#", "Monday-Friday", "Lusaka", "Kitwe", "Chipata"]

# The same, rewritten for the ear: what a `spoken:` field would hold.
SPOKEN_EXAMPLE = ("Our Savings account lets you deposit and withdraw at any time. "
                  "The minimum balance is one hundred kwacha, and it earns five percent "
                  "a year, paid monthly. There are no opening or monthly fees. To open one, "
                  "visit any branch with your N R C or passport, proof of where you live, "
                  "and your T PIN certificate.")


def answers(n: int = 5) -> list[tuple[str, str]]:
    """The first n plain answers, with [CONFIRM ...] notes and placeholders cut."""
    out = []
    for f in sorted((ROOT / "knowledge" / "intents").glob("*.yaml")):
        for it in yaml.safe_load(f.read_text(encoding="utf-8")).get("intents", []):
            a = it.get("answer")
            if not isinstance(a, str) or len(a) < 150:
                continue
            a = re.sub(r"\[CONFIRM[^\]]*\]", "", a, flags=re.S)
            a = re.sub(r"\{[a-z_]+\}", "*778#", a)
            out.append((it["intent"], " ".join(a.split())))
            if len(out) == n:
                return out
    return out


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def bench_kokoro(texts, model: str, label: str) -> None:
    import soundfile as sf
    from kokoro_onnx import Kokoro
    kdir = Path(os.environ["KOKORO_DIR"])
    t = time.perf_counter()
    k = Kokoro(str(kdir / model), str(kdir / "voices-v1.0.bin"))
    print(f"\n{label}: loaded in {time.perf_counter() - t:.1f}s")
    for name, text in texts:
        t = time.perf_counter()
        audio, sr = k.create(text, voice="af_heart", speed=1.0, lang="en-us")
        took = time.perf_counter() - t
        path = OUT / f"kokoro-{label.split()[-1]}-{name}.wav"
        sf.write(path, audio, sr)
        dur = len(audio) / sr
        print(f"  {name:28} {dur:5.1f}s of speech in {took:5.2f}s  (real-time factor {took / dur:.2f})")


def bench_piper(texts) -> None:
    from piper import PiperVoice
    t = time.perf_counter()
    voice = PiperVoice.load(os.environ["PIPER_VOICE"])
    print(f"\nPiper lessac-medium: loaded in {time.perf_counter() - t:.1f}s")
    for name, text in texts:
        path = OUT / f"piper-{name}.wav"
        t = time.perf_counter()
        with wave.open(str(path), "wb") as w:
            voice.synthesize_wav(text, w)
        took = time.perf_counter() - t
        dur = seconds(path)
        print(f"  {name:28} {dur:5.1f}s of speech in {took:5.2f}s  (real-time factor {took / dur:.2f})")


def phonemes() -> None:
    try:
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
        import espeakng_loader
        from phonemizer import phonemize
        EspeakWrapper.set_library(espeakng_loader.get_library_path())
        EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
    except ImportError:
        return
    print("\nHow the phonemiser reads screen text (IPA):")
    for w in TRICKY:
        print(f"  {w:14} -> {phonemize(w, language='en-us', backend='espeak', strip=True)}")


def main() -> None:
    os.environ.setdefault("OMP_NUM_THREADS", str(THREADS))
    OUT.mkdir(parents=True, exist_ok=True)
    texts = answers() + [("spoken_savings_example", SPOKEN_EXAMPLE)]
    print(f"{len(texts)} answers, {THREADS} CPU threads; wav files in {OUT}")
    if os.environ.get("KOKORO_DIR"):
        bench_kokoro(texts, "kokoro-v1.0.onnx", "Kokoro fp32")
        if (Path(os.environ["KOKORO_DIR"]) / "kokoro-v1.0.int8.onnx").exists():
            bench_kokoro(texts, "kokoro-v1.0.int8.onnx", "Kokoro int8")
    if os.environ.get("PIPER_VOICE"):
        bench_piper(texts)
    phonemes()


if __name__ == "__main__":
    main()
