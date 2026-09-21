# Test Run schema (runner result_version 3)

## Terminology

| term | meaning | where | UI (Korean) |
|---|---|---|---|
| **Test Suite** | a static, version-controlled set of case definitions | `dev/evaluation/*.yaml`, read only by `dev/evaluation/suite.py` | 테스트 세트 |
| **FULL48** | the frozen regression anchor for Resolve v1 (suite version 1, 48 cases, unchanged) | `resolve_regression.yaml`, dataset id `resolve_regression` | FULL48 회귀 테스트 |
| **Test Suite v2** | the broader generalization suite: ≥5 utterances per accepted recipe plus Out-of-Scope (suite version 2) | `test_suite_v2.yaml`, dataset id `test_suite_v2` | 테스트 세트 v2 |
| **Test Run** | one execution of one suite under one model/config/time, i.e. what `runner.run()` returns | `dev/tools/sweep_out/test_runs/<run_id>/` (gitignored) | 실행 기록 |
| **Case Result** | the result for one utterance within one run, i.e. one element of `cases` | `run.json › cases[]`, `cases.jsonl` line | 발화 결과 |
| in-scope / out-of-scope | a case with an expected recipe / a case with an expected outcome instead | `row.scope` | 범위 안 / 범위 밖 |

Metric names:

| name | UI label | definition |
|---|---|---|
| Selection | 기능 선택 | in-scope HIT / in-scope runs. HIT means `{recipe_id} ∪ candidates == expected recipe set` (`check_resolve._grade`, unchanged) |
| Semantic (fields) | 인자 추출 | scored spoken fields correct / scored spoken fields |
| Semantic (cases) | (report only) | cases with every scored field correct / cases with ≥1 scored field |
| Joint | 발화 성공 | in-scope cases passed (selection and all scored fields) / in-scope runs |
| OOS | 범위 밖 처리 | out-of-scope cases whose outcome is in `expected.outcomes` / out-of-scope runs |
| READY | 실행 준비 | in-scope rows whose materialize status is READY / in-scope rows materialized |

Suites are never combined into one percentage, and in-scope and OOS results are never merged into one percentage.

## Suite format (version 2 additions)

```yaml
version: 2
name: "test_suite_v2"
groups: [spoken, picked_point, view_extent, out_of_scope]   # order enforced
cases:
  - id: 1                       # in-scope, same as FULL48
    group: spoken
    utterance: "부산역 좌표 알려줘"
    enabled: true
    expected:
      recipe_ids: [recipe_001]
      spoken: {argument: "부산역"}       # only fields the recipe's execution reads
  - id: 196                     # out-of-scope
    group: out_of_scope
    utterance: "내일 청주 날씨 어때"
    enabled: true
    expected:
      category: unsupported     # unsupported | ambiguous | insufficient
      outcomes: [NO_MATCH]      # subset of NO_MATCH, CLARIFY, MISSING_ARGUMENT
```

Outcome names are the runtime's own, not new ones: `NO_MATCH` and `CLARIFY` come from the resolve response schema's status enum, and `MISSING_ARGUMENT` is the `workflow_materializer` verdict. `spoken_audit.integrity` checks that each one exists at those sources.
`outcome = status` if status ≠ SELECT; otherwise it is the materialize status (READY, MISSING_ARGUMENT, …).

## Storage layout

```
dev/tools/sweep_out/test_runs/<YYYYMMDD-HHMMSS>-<suite name>-<6 hex>/
  meta.json     {"meta": head, "summary": null} at start → {"meta", "summary"} at finish (list_runs reads only this)
  cases.jsonl   one Case Result per line, appended and flushed after each case (survives crashes)
  run.json      the full result at finish (identical to runner.run's return value)
  summary.md    human-readable summary and failed-case list
```

`test_runs.load_run(run)` returns `run.json` if it exists. Otherwise it rebuilds the run from `meta.json` and `cases.jsonl`: it recounts with `runner.summarize` and sets `meta.stopped = "incomplete: …"`. The UI renders both cases through the same code path.

## `meta`

| field | note |
|---|---|
| result_version | 3 |
| run_id | unique; also the folder name |
| suite | path · name · version · sha256 · case_count · group_labels · selected_case_ids · dataset_id · label |
| runs · resolver · role | as before |
| conditions | model · provider · role_version · **inference** (e.g. timeout) · prompt/response_schema/menu {path, sha256} |
| functions | recipe id → menu function sentence |
| cooldown · context · materialize · materialize_now · artifact_root · git_head | as before |
| started_at · finished_at · **elapsed_s** | KST ISO |
| stopped | null · `ServerDown: …` · `StopRun: …` (GPU gate) · `interrupted` · (loaded partial) `incomplete: …` |
| **gpu** | null (no monitor) or {available, gpus[{index,name}], start_temp, max_temp, end_temp, max_util, max_fan, pauses, pause_seconds, thermal_throttle (null if unobservable), samples, gate, policy, notes, log[]} |
| saved_to | folder (present in the returned object only, not in run.json) |

## `summary`

`{groups: {label: tally}, total: tally, metrics, latency, recipes}`

- tally: runs · in_scope_runs · HIT/NEAR/MISS/UNATTACHED (sum = in_scope_runs) · spoken_hits/spoken_runs · field_hits/field_runs · passed · in_scope_passed · oos_runs · oos_passed · oos_categories{cat:{runs,passed}} · failure_stages{function,input,scope,error} (passed + sum = runs) · materialize{status:n} · in_scope_ready · in_scope_materialized · errors
- metrics: selection · semantic_fields · semantic_cases · joint · oos · ready, each {correct, total}
- latency: {count, min, median, p95 (nearest-rank), max, total} of `timing.resolve_s`
- recipes: {expected recipe: {runs, passed, hit}}, in-scope only

## `cases[]` (Case Result)

case_id · group · group_label · **scope** · **recipe_group** · utterance · run ·
expected {recipe_ids, spoken, (OOS) category, outcomes} ·
actual {status, recipe_id, candidate_recipe_ids, found_recipe_ids, spoken{…all non-selection fields}, reason} ·
grade (in-scope) · recipe_correct (in-scope) · spoken_fields[{name, expected, actual, correct}] · spoken_correct ·
**outcome** · **oos_correct** · passed · failure_stage (function | input | scope | error) ·
materialize {status, recipe_id, missing, workflow, nodes, commands} · timing {**started_at**, resolve_s, materialize_s} · error

## How to run and load

```
python dev/evaluation/runner.py                                   # FULL48, GPU record, auto-save
python dev/evaluation/runner.py --suite dev/evaluation/test_suite_v2.yaml --gpu gate
python dev/evaluation/runner.py --no-save --gpu off               # nothing saved, no telemetry
python dev/evaluation/spoken_audit.py --suite dev/evaluation/test_suite_v2.yaml   # GT audit table
```

```python
from dev.evaluation import test_runs
test_runs.list_runs()              # newest first
test_runs.load_run(run_id)         # same shape as runner.run()
```

UI test tab: 테스트 세트 picker → 테스트 실행 runs through `runner.run_dataset`, which auto-saves with the GPU gate. The 실행 기록 picker loads a saved run into the same view.

GPU gate (`dev/evaluation/gpu.POLICY`): start when util ≤5% and temp ≤58°C · every 3 calls sleep 5 s and check · pause at ≥66°C, resume at ≤58°C · on thermal throttle, cool down and StopRun · at the end, if >62°C, cool down to ≤58°C · each wait is capped at 1800 s. Nothing is ever written to the GPU (no fan, power or clock changes).
