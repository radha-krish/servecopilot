# gold_v1 hand check

For each case open the issue and PR(s). Fill in:
- **Fixes?** yes / partly / no: does the PR actually fix this issue?
- **Component?** yes / no: is the component label right?

| # | Issue | Fixing PR(s) | Component | Fixes? | Component? | Notes |
|---|---|---|---|---|---|---|
| 1 | [#14991](https://github.com/vllm-project/vllm/issues/14991) [Bug]: Docker image in trunk cannot find libpython.so | [#15377](https://github.com/vllm-project/vllm/pull/15377) Revert "[CI/Build] Use uv python for docker rather than ppa: | build_ci | yes | yes | Revert of the Docker uv-python change; PR closes this and 3 other reports |
| 2 | [#15269](https://github.com/vllm-project/vllm/issues/15269) [Bug]: RuntimeError at vllm startup, V0 engine, Llama 3.1, "The size o | [#15308](https://github.com/vllm-project/vllm/pull/15308) [Bugfix] LoRA V0 - Fix case where `max_num_seqs` is between  | layers_quant | yes | no | PR reproduces the exact tensor-size error. Label wrong: LoRA bug filed under layers_quant (mapping choice) |
| 3 | [#15384](https://github.com/vllm-project/vllm/issues/15384) [Feature]: Request for Support of Dense and Sparse Features in bge-m3  | [#14526](https://github.com/vllm-project/vllm/pull/14526) Support bge-m3 sparse embeddings and colbert embeddings | models | yes | yes | Feature request; PR opened before the issue but explicitly fixes it. Tie layers vs models broken toward models |
| 4 | [#15677](https://github.com/vllm-project/vllm/issues/15677) [Bug]: v0.8.2 generates incomplete sequences for Qwen2-VL-7B under spe | [#16229](https://github.com/vllm-project/vllm/pull/16229) [Bugfix] Merge MM embeddings by index instead of token IDs | models | yes | yes | PR fixes MM-embedding merge when the model generates placeholder tokens; lists this issue first |
| 5 | [#15987](https://github.com/vllm-project/vllm/issues/15987) [Bug]: EADDRINUSE (-98) error when setting up NCCL communicator | [#15988](https://github.com/vllm-project/vllm/pull/15988) Use custom address for listening socket | distributed_kv | yes | yes | TCPStore now listens on a custom address instead of 0.0.0.0 |
| 6 | [#16150](https://github.com/vllm-project/vllm/issues/16150) [Bug]: Error When Launching Llama-4-Scout-17B-16E-Instruct Without `-- | [#16491](https://github.com/vllm-project/vllm/pull/16491) Fix vLLM x torch.compile config caching | config | yes | yes | Root cause: torch.compile cache ignored override_generation_config; PR explains it for this issue |
| 7 | [#17585](https://github.com/vllm-project/vllm/issues/17585) [Bug]: Mistral tool parser & streaming: corrupt tool_calls completions | [#19425](https://github.com/vllm-project/vllm/pull/19425) [Bugfix] Mistral tool parser streaming update | frontend | yes | yes | Mistral tool-parser streaming rewrite; same symptom (missing chars in streamed tool_calls) |
| 8 | [#19139](https://github.com/vllm-project/vllm/issues/19139) [Bug]: Error when loading model(gemma-3-4b) merged after DeepSpeed tra | [#19151](https://github.com/vllm-project/vllm/pull/19151) [Bugfix] Update multimodel models mapping to fit new checkpo | models | yes | yes | New checkpoint weight names after Transformers 4.52; gemma3_mm in the touched models |
| 9 | [#23355](https://github.com/vllm-project/vllm/issues/23355) [Feature]: Support pipeline parallelism for AIDC-AI/Ovis2.5-9B | [#23405](https://github.com/vllm-project/vllm/pull/23405) [Model] Add Ovis2.5 PP support | models | yes | yes | Adds PP support for Ovis2.5, exactly the request |
| 10 | [#24523](https://github.com/vllm-project/vllm/issues/24523) [Bug]: Unclear error message when `--num-redundant-experts` provided w | [#24524](https://github.com/vllm-project/vllm/pull/24524) [Bugfix] Improve EPLB config validation error message | config | yes | yes | Clearer EPLB validation message, exactly the request |
| 11 | [#26577](https://github.com/vllm-project/vllm/issues/26577) [CI Failure]: entrypoints/openai/test_run_batch.py::test_completions - | [#26578](https://github.com/vllm-project/vllm/pull/26578) [CI] fix test_run_batch.py::test_completions - AssertionErro | tests | yes | yes | CI failure fixed by a test-only change; 'tests' is right here |
| 12 | [#27524](https://github.com/vllm-project/vllm/issues/27524) [Bug]: CPU build failed to run with OneDNN linear for fp16 model | [#27526](https://github.com/vllm-project/vllm/pull/27526) [Bugfix][CPU] Fallback oneDNN linear to torch linear to fix  | layers_quant | yes | yes | Falls back to torch linear for fp16 on CPU |
| 13 | [#29297](https://github.com/vllm-project/vllm/issues/29297) [Bug]: What should the image embedding input be like? I have tested wi | [#29480](https://github.com/vllm-project/vllm/pull/29480) [Bugfix] Fix handling of image embeds in models | models | partly | yes | Issue is a usage question with 4 cases; PR fixes the 3D-embedding bug (cases 2-3), case 4 was user error |
| 14 | [#32791](https://github.com/vllm-project/vllm/issues/32791) [Bug]: chat.completions returns content: null for GPT-OSS multi-turn w | [#34454](https://github.com/vllm-project/vllm/pull/34454) [Bugfix]: Fix structured output in multi-turn gpt-oss | tests | yes | no | PR fixes gptoss reasoning parser. Label 'tests' wrong: vllm/reasoning unmapped -> fell back to tests |
| 15 | [#34034](https://github.com/vllm-project/vllm/issues/34034) [Bug]: vLLM-compile should not execute the decoder forward pass during | [#35472](https://github.com/vllm-project/vllm/pull/35472) [torch.compile] Stop lazily compiling | tests | yes | no | PR makes torch.compile eager. Label 'tests' wrong: vllm/compilation unmapped -> fell back to tests |
| 16 | [#36105](https://github.com/vllm-project/vllm/issues/36105) [ROCm][v0.16.0] Qwen3-VL-30B-A3B-Instruct-FP8 fails to start with NotI | [#38086](https://github.com/vllm-project/vllm/pull/38086) [ROCm] Enable VLLM triton FP8 moe for gfx1201, tuned for Qwe | layers_quant | yes | yes | PR enables Triton FP8 MoE on gfx12xx and names this error; GPU model not visible in the issue |
| 17 | [#39472](https://github.com/vllm-project/vllm/issues/39472) [Bug]: Missing `soundfile` dependency breaks audio transcription | [#39473](https://github.com/vllm-project/vllm/pull/39473) fix: handle ImportError in load_audio | models | yes | yes | ImportError handled so pyav fallback runs; vllm/multimodal is grouped under models by design |
| 18 | [#51868](https://github.com/vllm-project/vllm/issues/51868) [Feature][DSpark]: Enable varlen for Nemotron-H (Mamba) | [#53036](https://github.com/vllm-project/vllm/pull/53036) [Attention][Spec Decode] Enable varlen Mamba2 decode for ada | attention | yes | yes | Wires varlen Mamba2 decode, exactly the request; mamba2 backend lives under v1/attention |
| 19 | [#58567](https://github.com/vllm-project/vllm/issues/58567) [ROCm][Perf][GLM-5.3-Flash]: Remove cpy after _rocm_sparse_attn_prefil | [#58569](https://github.com/vllm-project/vllm/pull/58569) [ROCm][Perf][GLM-5.3-Flash] Remove redundant copy after ragg | attention | yes | yes | Removes the extra copy, exactly the request |
| 20 | [#61603](https://github.com/vllm-project/vllm/issues/61603) [Bug]: NemotronH/Mamba2: _chunk_scan_fwd_kernel nondeterministically e | [#61718](https://github.com/vllm-project/vllm/pull/61718) [Bugfix] Fix NaN output of the Mamba2 chunk scan kernel on s | layers_quant | yes | yes | Drops the racy autotune configs that emit NaN on sm90 |

## Result

- Fixes = no: 0 / 20 → link noise ≈ 0 % (95% CI roughly 0–16 %)
- Fixes = partly: 1 / 20 (case 13)
- Component wrong: 3 / 20 = 15 % (cases 2, 14, 15); 2 of 3 from one bug: unmapped code dirs fell back to `tests`

Checked by Claude (model), from issue text, PR description and changed files in the database. GitHub comment threads were not read.

## Fix applied after this check

The first check (above) was done on the labels *before* this fix.

- Tests/docs only decide the component when a PR touches nothing else; unmapped code now counts as `other` instead of falling back to `tests` (cases 14, 15).
- New `compile` component (`vllm/compilation`); `vllm/reasoning` → frontend.
- `layers_quant` renamed `layers` (it holds LoRA, MoE and Mamba ops, case 2).
- Effect on gold_v1: same 250 issues, 14 labels changed (11 `tests` → `other`, 2 → `compile`, 1 → `frontend`).

## Fresh component check (20 new cases, seed 8, after the fix)

The rules were tuned on the first 20 cases, so re-checking those would be biased. Component labels only, from PR title and code files.

| # | Issue | Label | Right? | Notes |
|---|---|---|---|---|
| 1 | #14888 | kernels | yes | Defensive triton import (triton_utils) |
| 2 | #15359 | build_ci | yes | Dockerfile revert |
| 3 | #16414 | worker | yes | Token index overflow in model runner |
| 4 | #17655 | frontend | yes | serving_chat streaming |
| 5 | #18112 | other | yes | Test-utility model name; `other` is honest |
| 6 | #19432 | worker | yes | zip(strict=) in model runner |
| 7 | #20051 | models | yes | Cross-encoder model conversion |
| 8 | #20461 | frontend | **no** | Real fix is the ClassifierPooler activation (layers/models); 3 entrypoint files outvoted it |
| 9 | #21219 | frontend | yes | CLI arg middleware |
| 10 | #27210 | scheduler | yes (ambiguous) | Spec decode + structured output; tie scheduler vs decoding |
| 11 | #27571 | models | yes | qwen3_next |
| 12 | #29403 | models | yes | model_loader (grouped under models) |
| 13 | #29657 | scheduler | yes | Spec-decode uniform decode in scheduler |
| 14 | #33050 | distributed_kv | yes | NIXL connector |
| 15 | #33132 | build_ci | yes | transformers v5 bump |
| 16 | #34380 | worker | **no** | MTP / spec decode fix spread over 4 areas; worker won 2–1–1–1 |
| 17 | #35195 | build_ci | yes | CI config revert |
| 18 | #44154 | decoding | yes | Logits processor validation |
| 19 | #47971 | scheduler | yes | Chunked prefill for pooling |
| 20 | #54907 | models | yes | DCP prefill kernel in vllm/models |

- Component wrong: 2 / 20 = 10 % (95 % CI roughly 3–30 %), plus 1 ambiguous.
- Pattern: the majority vote fails on fixes that span several areas.
