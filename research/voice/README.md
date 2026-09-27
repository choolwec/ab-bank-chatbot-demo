# Text-to-speech benchmark

Research code, not part of the app or its test suite. It times small,
commercially licensed voices reading real answers from `knowledge/intents/`
on CPU, and prints how the pronunciation step reads banking text. The findings
and recommendations are in `docs/voice-chat-research.md`.

```
pip install kokoro-onnx piper-tts soundfile pyyaml
# Kokoro files: https://github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0)
# Piper voice:  https://huggingface.co/rhasspy/piper-voices (en/en_US/lessac/medium)
KOKORO_DIR=/path/to/kokoro PIPER_VOICE=/path/to/en_US-lessac-medium.onnx \
  python research/voice/bench_tts.py
```

Audio goes to `.out/` (git-ignored). Chatterbox was timed separately with
CPU-only PyTorch and `chatterbox-tts` 0.1.7: `ChatterboxTTS.from_pretrained("cpu")`
then `generate(text, audio_prompt_path=<reference wav>)`. The reference was a
synthetic Piper clip, never a real person's voice.

## Results (27/09/2026, 4 CPU threads, no GPU)

| Voice | Size | Real-time factor | A 20 s answer takes |
|---|---|---|---|
| Piper en_US-lessac-medium | 63 MB | 0.03 | 0.6 s |
| Kokoro-82M fp32 ONNX | 326 MB | 0.23 | 4.6 s |
| Kokoro-82M int8 ONNX | 92 MB | 1.3 | 27 s |
| Chatterbox (cloning) | ~3 GB | 3.7 (7.2 on the first, warm-up call) | ~29 s for 8 s |

The Perth watermark detector read 1.0 on Chatterbox output and 0.0 on Piper
output.
