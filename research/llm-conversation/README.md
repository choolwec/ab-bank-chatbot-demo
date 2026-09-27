# Local conversation model benchmark

Research code, not part of the app or its test suite. Findings are in
`docs/local-conversation-research.md`.

- `bench_llm.py`: plays 11 scripted conversations (13 turns) against each
  GGUF model through llama.cpp's `llama-server`, giving the model only the
  approved answers the current matcher retrieves. It checks every reply for
  invented numbers, answers to questions it should decline, leaked
  instructions and requests for secrets. Replies go to `.out/` (git-ignored).
- `voice_loop.py`: a spoken question, transcribed by Gemma 4 E2B's audio
  input, checked by `guards.mask()` and `guards.urgent_scan()`, answered from
  approved facts, and spoken by Piper.

```
# llama.cpp built from source: cmake -B build && cmake --build build -j4 --target llama-server
# models: google/gemma-4-E2B-it-qat-q4_0-gguf (+ gemma-4-E2B-it-mmproj.gguf for audio),
#         unsloth/Qwen3.5-2B-GGUF, unsloth/Qwen3.5-4B-GGUF, ibm-granite/granite-4.2-3b-GGUF
LLAMA_SERVER=.../llama-server MODELS_DIR=.../ggufs python research/llm-conversation/bench_llm.py
```

## Results (27/09/2026, 4 CPU threads, Q4 quantisation)

| Model | Size | First word | Full reply | Invented numbers | Should-decline answered | Leaked rules |
|---|---|---|---|---|---|---|
| Qwen3.5 2B | 1.3 GB | 2.5 s | 6.7 s | 0 / 13 | 0 / 4 | 0 |
| Granite 4.2 3B | 2.2 GB | 3.3 s | 9.7 s | 2 / 13 | 0 / 4 | 1 |
| Qwen3.5 4B | 2.7 GB | 6.0 s | 14.1 s | 0 / 13 | 0 / 4 | 0 |
| Gemma 4 E2B | 3.3 GB | 4.2 s | 6.7 s | 0 / 13 | 0 / 4 | 0 |
| Gemma 4 E4B | 5.2 GB | 8.6 s | 13.3 s | 0 / 13 | 0 / 4 | 0 |

The automatic checks miss misleading wording that uses only approved numbers
(Qwen3.5 4B: "approximately 16%" for a 9.3–16% range), so the replies were
also read by hand.
