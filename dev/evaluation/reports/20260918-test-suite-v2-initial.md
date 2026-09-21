# Test Suite v2 — implementation report (2026-09-18)

- start HEAD `2010a92` (clean) → final `4f9540d` "테스트 스위트 v2와 실행 기록 기능을 추가한다" · working tree clean · PUSH none
- Resolve v1 frozen and untouched. FULL48, Registry, llm_engine, orchestrator and execution: **unchanged** since 2010a92. KRRI_ASAP `311187e`, not touched (its 5 dirty entries predate this session)

## Reviewer requirements → implementation

| # | requirement | done |
|---|---|---|
| 1 | 5+ utterances per Static Workflow Recipe | `test_suite_v2.yaml`: 39/39 recipes × 5 = 195 in-scope. Lexical, syntactic and register variation. No FULL48, menu-example or prompt-example text, recipe ids or tool names (enforced by `spoken_audit.integrity`) |
| 2 | Out-of-Scope | 24 cases: unsupported 8 → NO_MATCH · ambiguous 8 → CLARIFY · insufficient 8 → CLARIFY or MISSING_ARGUMENT. The outcome names are the runtime's own (schema status enum + materializer verdict, checked). Reported separately (`metrics.oos`, `oos_categories`, failure stage `scope`) |
| 3 | Terminology | Test Suite / Test Run / Case Result / FULL48 / Test Suite v2, defined once in the `test_runs.py` header, `suite.py` DATASETS and RUN_SCHEMA.md. UI labels: 테스트 세트 / 실행 기록 / 발화 결과 |
| 4 | GPU / temp / start time / case latency | `gpu.py` GpuMonitor (optional; nvidia-smi absent → available false) + office quiet gate. meta.gpu {start, max, end temp, pauses, throttle, log} · started_at, finished_at, elapsed_s · per-case timing.started_at and resolve_s · summary.latency (min, median, p95, max) |
| 5 | Automatic Test Run save/load | `test_runs.py`: one folder per run. cases.jsonl is streamed, so a crash keeps the finished cases. run.json and summary.md are written at finish. `list_runs`, `load_run`. The CLI and UI save automatically. Round trip is tested and recounted metrics match |
| 6 | Visualization | Existing Streamlit test tab extended with no new framework: 실행 기록 picker (loads through the same render path), run overview strip, per-recipe results (expanded when anything failed), recipe/OOS filter, 범위 밖 처리 stage filter, failures-first selection. Case detail shows accepted vs actual outcome, workflow readiness and latency |

Data model: **Test Suite** (static YAML, version 1 or 2) → **Test Run** (`runner.run` result, result_version 3, saved folder) → **Case Result** (`cases[]` row). FULL48 and v2 are separate datasets and are never combined into one percentage.

## Files

| file | change |
|---|---|
| dev/evaluation/test_suite_v2.yaml | new, 219 cases |
| dev/evaluation/suite.py | version 2, out_of_scope group, OOS_CATEGORIES/OUTCOMES, identity, label_of, in_scope. v1 rules unchanged |
| dev/evaluation/spoken_audit.py | integrity() for both suites; OOS skipped in audit |
| dev/evaluation/runner.py | result v3: scope, outcome, OOS verdict, metrics, latency, recipes, run_id, elapsed, inference, monitor/save hooks, StopRun, context_payload, CLI --gpu/--no-save |
| dev/evaluation/gpu.py | new: telemetry + quiet gate |
| dev/evaluation/test_runs.py | new: Recorder, list_runs, load_run, summary_text |
| app/ui/components/testing_panel.py | the UI changes above |
| dev/tests/tools/test_dashboard_selfchecks.py | +10 tests (v2 coverage, FULL48 anchor, loader rejects bad OOS, OOS verdict/metrics, save/load round trip, interrupted run, GPU optional, quiet-gate pause, throttle stop) + 1 expectation updated (`scope` stage) |
| dev/tests/app/ui/test_testing_panel.py | +4 tests (OOS detail, overview, recipe/OOS filter, saved run loads with no LLM call) |
| CLAUDE.md | one line: when reviving a recipe, add ≥5 v2 utterances (enforced) |

## Tests

# targeted
60 passed in 3.82s
# full
FAILED dev/tests/app/ui/graph/test_layout_invariants.py::test_dense_graph_would_move_if_overlap_removal_were_used
1 failed, 448 passed, 1 warning in 9.57s
# baseline (2010a92): 435 passed, 1 known graphviz failure. now: +13 new tests; same single known failure; new regressions 0

## Live v2 run (exactly one) — see LIVE_RUN_SUMMARY.md / FAILURE_ANALYSIS.md

Selection 184/195 · Semantic 187/190 fields (147/150 cases) · Joint 181/195 · OOS 15/24 · Errors 0 · READY 185/195.
23 failures: boundary 9 · wrong recipe 2 · extraction 3 · OOS handling 8 · GT/design question 1 · evaluator/runtime error 0.
Latency: median 1.64 s, p95 1.88 s. GPU: max 70°C (end sample), 14 pauses, no throttling. Elapsed 22 min 33 s.

UI smoke: the real saved run was loaded through the 실행 기록 picker (AppTest). 219 rows, overview complete, 40 per-recipe entries (9 with failures), OOS filter shows 24, no exceptions.

## Not done / open

- The GPU sample every 3 calls can miss short spikes: the end sample read 70°C, above the 66°C pause line.
- The Streamlit server on 8501 was not restarted (it does not reload imported modules). The UI was verified through AppTest.
- Open human decisions: whether #211 belongs in ambiguous; the convention for "keyword + category noun" arguments (#96/#97); the 015/016 and 052/060 menu boundaries.
