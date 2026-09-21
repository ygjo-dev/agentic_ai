# Test Suite v2 — live run (exactly one)

| item | value |
|---|---|
| Test Run id | `20260918-161110-test_suite_v2-e2cf28` (auto-saved at `dev/tools/sweep_out/test_runs/…`; a copy is in `saved_test_run/`) |
| suite | test_suite_v2 · version 2 · sha256 `50244e5bb343…` · 219 cases (195 in-scope + 24 OOS) |
| command | `python dev/evaluation/runner.py --suite dev/evaluation/test_suite_v2.yaml --gpu gate` (context both, materialize on, auto-save) |
| model | solar-open2-250b · vllm · resolve role v1 · prompt v1 · schema v1 · inference timeout 180 (git_head at run 2010a92 + uncommitted evaluation code; Resolve untouched) |
| start / end | 2026-09-18 16:11:10 → 16:33:43 KST |
| elapsed | 1353.2 s (22 min 33 s). 635 s of that was thermal pauses and 5 s rests; the pure resolve time was 353.2 s |
| LLM calls / retries | 219 / 0 |
| latency (resolve_s) | min 1.066 · median 1.637 · p95 1.882 · max 2.182 s |
| stopped | none |

## Metrics

| metric | result |
|---|---|
| Selection (in-scope HIT) | **184/195 (94.4%)**. NEAR 10 (CLARIFY that includes the right recipe) · MISS 1 · UNATTACHED 0 |
| Semantic fields | **187/190 (98.4%)** |
| Semantic cases | 147/150 |
| Joint (in-scope passed) | **181/195 (92.8%)** |
| OOS | **15/24 (62.5%)**: unsupported 7/8 · ambiguous 2/8 · insufficient 6/8 |
| Errors | 0 |
| Workflow readiness (in-scope READY) | 185/195. The 10 not ready are the 10 in-scope CLARIFYs (NOT_SELECTED). Every in-scope SELECT reached READY |
| failure stages | function 11 · input 3 · scope 9 · error 0 → 23 failed / 219 |

By group:

| group | Selection | fields | passed |
|---|---|---|---|
| 말한 것 (spoken) | 110/120 | 117/120 cases | 107/120 |
| 찍은 지점 (picked point) | 45/45 | 25/25 | 45/45 |
| 보이는 범위 (view extent) | 29/30 | 5/5 | 29/30 |
| 범위 밖 (OOS) | – | – | 15/24 |

## GPU (office quiet gate, dev/evaluation/gpu.POLICY)

- 4× NVIDIA RTX PRO 6000 Blackwell Max-Q. Start: util 0%, 37°C (gate passed immediately).
- Max 70°C. That is the end-of-run sample, right after the last call (util 99%). During the run, 15 readings were ≥66°C (the highest was 67) and each triggered a pause.
- 14 pauses, 635.4 s paused in total. Max fan 39% (recorded only).
- End 70°C → cooled to 57°C in 4 samples (the gate's end cooldown).
- Thermal throttling: **none observed** (`hw/sw_thermal_slowdown` "Not Active" on all 120 samples).
