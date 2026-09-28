"""A fully local voice turn: spoken question in, spoken answer out, on CPU.

Research code, not part of the app. It times each step of the pipeline the
voice research recommends, keeping the bank's safety steps in the middle:

1. listen: Gemma 4 E2B (Apache-2.0) transcribes the audio (llama-server with
   the model's audio projector, `--mmproj`);
2. safety: the transcript goes through the app's own guards.mask() and
   guards.urgent_scan(), exactly like a typed message. An urgent message
   stops here: it goes to the deterministic fraud flow, never to the model;
3. answer: the same Gemma model replies from the approved FACTS only
   (the grounded prompt from bench_llm.py);
4. speak: Piper reads the reply aloud.

Usage:
    LLAMA_SERVER=... GEMMA=.../gemma-4-E2B_q4_0-it.gguf \
    MMPROJ=.../gemma-4-E2B-it-mmproj.gguf PIPER_VOICE=.../en_US-lessac-medium.onnx \
        python research/llm-conversation/voice_loop.py question1.wav [question2.wav ...]
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import guards  # noqa: E402
from bench_llm import PORT, SYSTEM, facts_for  # noqa: E402

TRANSCRIBE = ("Transcribe the following speech segment in its original language. "
              "Only output the transcription, with no newlines.")


def post(messages: list[dict], max_tokens: int = 200) -> str:
    body = json.dumps({"messages": messages, "temperature": 0.2, "max_tokens": max_tokens,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def main() -> None:
    proc = subprocess.Popen(
        [os.environ["LLAMA_SERVER"], "-m", os.environ["GEMMA"], "--mmproj", os.environ["MMPROJ"],
         "-t", os.environ.get("LLM_THREADS", "4"), "-c", "8192", "--port", str(PORT), "--jinja"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from piper import PiperVoice
    voice = PiperVoice.load(os.environ["PIPER_VOICE"])
    try:
        for _ in range(300):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                    if json.load(r).get("status") == "ok":
                        break
            except Exception:
                time.sleep(1)
        post([{"role": "user", "content": "hello"}], 5)  # warm-up
        for path in sys.argv[1:]:
            with wave.open(path) as w:
                spoken = w.getnframes() / w.getframerate()
            audio = base64.b64encode(Path(path).read_bytes()).decode()
            t0 = time.perf_counter()
            heard = post([{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": audio, "format": "wav"}},
                {"type": "text", "text": TRANSCRIBE}]}], 100)
            t1 = time.perf_counter()
            masked, _ = guards.mask(heard)
            urgent = guards.urgent_scan(masked)
            print(f"\n{Path(path).name} ({spoken:.1f}s of speech)")
            print(f"  heard ({t1 - t0:.1f}s): {heard}")
            if urgent:
                print(f"  urgent signal ({urgent}): goes to the fraud flow, not the model")
                continue
            reply = post([{"role": "system", "content": SYSTEM.format(facts=facts_for(masked))},
                          {"role": "user", "content": masked}])
            t2 = time.perf_counter()
            out = Path(path).with_name(Path(path).stem + "-reply.wav")
            with wave.open(str(out), "wb") as w:
                voice.synthesize_wav(reply, w)
            t3 = time.perf_counter()
            print(f"  reply ({t2 - t1:.1f}s): {reply}")
            print(f"  spoken reply ({t3 - t2:.1f}s) -> {out.name}")
            print(f"  total, question end to reply audio ready: {t3 - t0:.1f}s")
    finally:
        proc.terminate()
        proc.wait(timeout=30)


if __name__ == "__main__":
    main()
