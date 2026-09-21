# Test Suite v2 — canonical run for the 203-case suite (2026-09-21)

The first live run of Test Suite v2 after its Out-of-Scope definition was narrowed
(219 → 203 cases, `d24553c`). **This is the baseline the corrected suite is read against.**

Exactly one run. Resolve was not tuned, no ground truth was edited after seeing results,
and nothing was rerun to improve a score.

## Evaluation assets — where they live now

```
dev/evaluation/
  test_suites/test_suite_v1.yaml   FULL48, the frozen anchor (suite version 1, 48 cases)
  test_suites/test_suite_v2.yaml   the broader suite       (suite version 2, 203 cases)
  test_runs/<run_id>/              every saved Test Run, version-controlled
  reports/                         this file and its siblings
```

The two suites are separate datasets and are never combined into one percentage.
FULL48 kept its bytes through the rename — sha256
`1bd40444b9f0daf28a977e4337938bb5af07dab7a7fac9b14787ab27a442670a`, unchanged.

| suite | dataset id | version | cases | in-scope | out-of-scope |
|---|---|---|---|---|---|
| FULL48 | `test_suite_v1` | 1 | 48 | 48 | – |
| Test Suite v2 | `test_suite_v2` | 2 | 203 | 195 (39 recipes × 5) | 8 |

Out-of-scope means one thing only: **none of the 39 supported functions may be selected**.
Every out-of-scope case expects `NO_MATCH`; the loader rejects any other expected outcome.

## The run

| item | value |
|---|---|
| Test Run id | `20260921-090538-test_suite_v2-87532e` |
| saved at | `dev/evaluation/test_runs/20260921-090538-test_suite_v2-87532e/` (in Git) |
| command | `python dev/evaluation/runner.py --suite dev/evaluation/test_suites/test_suite_v2.yaml --gpu gate` |
| suite checksum | sha256 `e032664fd667c15873ba58705e0c66d75518588601f2e340effa410aca5e2db7` · 203 cases |
| model | `solar-open2-250b` |
| provider | vllm · resolve role v1 · prompt v1 (`85ed04e9358d…`) · response schema v1 (`22a9a42f1aff…`) |
| menu | `KRRI_Ontology_Registry/menu/menu.yaml` `83fdaf1b84d9…` |
| temperature | 0 |
| seed | 0 |
| max_tokens | 1024 |
| reasoning effort | none |
| inference timeout | 180 s |
| context / materialize | both / on |
| start → end | 2026-09-21 09:05:38 → 09:31:37 KST |
| elapsed | 1559.0 s (25 min 59 s); 327.0 s of that was inference, the rest the office quiet gate |
| LLM calls / retries | 203 / 0 |
| code at run | `d24553c` plus this task's uncommitted evaluation and UI changes. Resolve untouched |
| hardware | 4 × NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition · 97 887 MiB (95.6 GiB) each |

Inference latency (one `/resolve` call): **median 1.628 s · p95 1.863 s · max 3.275 s**
(min 1.061 s). No GPU thermal metric is recorded in the run — the quiet gate paces the calls
and writes nothing into the result.

## Scores

| metric | result |
|---|---|
| Selection (in-scope, exact function) | **184 / 195 (94.4 %)** — NEAR 10, MISS 1, UNATTACHED 0 |
| Semantic extraction, fields | **187 / 190 (98.4 %)** |
| Semantic extraction, cases | 147 / 150 (98.0 %) |
| Joint (in-scope: right function **and** right inputs) | **181 / 195 (92.8 %)** |
| Out-of-scope (NO_MATCH) | **7 / 8 (87.5 %)** |
| Whole suite passed | 188 / 203 (92.6 %) |
| Errors | **0** |

By group:

| group | cases | Selection | semantic cases | passed |
|---|---|---|---|---|
| 말한 것 (spoken) | 120 | 110/120 | 117/120 | 107/120 |
| 찍은 지점 (picked point) | 45 | 45/45 | 25/25 | 45/45 |
| 보이는 범위 (view extent) | 30 | 29/30 | 5/5 | 29/30 |
| 범위 밖 (out of scope) | 8 | – | – | 7/8 |

The result also carries workflow readiness (185/195 in-scope READY; the 10 that are not ready
are the 10 in-scope CLARIFYs, which select nothing). It is data only — the test screen does not
show it, because what that screen measures is function selection and input extraction.

## Failures — 15, classified

The runner assigns exactly one stage per case: function selection 11 · input extraction 3 ·
out-of-scope handling 1 · runtime error 0.

| class | count | cases |
|---|---|---|
| Menu boundary — two recipes plausibly cover the utterance; the model asked back with the right one among the candidates | 9 | 46, 47, 49, 53, 82, 85, 99, 114 (CLARIFY) · 48 (picked the overlapping 016) |
| Wrong function — the utterance is not ambiguous, yet the model asked back (the pairs 061/063 and 026/056 are not a known menu overlap) | 2 | 119, 191 |
| Input extraction | 3 | 59, 96, 97 |
| Out-of-scope handling | 1 | 199 |
| Evaluator / runtime error | 0 | – |

| case | utterance | expected | actual |
|---|---|---|---|
| 46 | 서울 종로 선거구 조회해줘 | 015 | CLARIFY [015, 016] |
| 47 | 경기 수원시갑 선거구 알려줘 | 015 | CLARIFY [015, 016] |
| 48 | 부산 해운대구을 지역구 정보 찾아줘 | 015 | SELECT 016 |
| 49 | 인천 연수구갑 선거구 하나만 보여줘 | 015 | CLARIFY [015, 016] |
| 53 | 대전 유성구 지역구 의원이랑 공약 다 보여줘 | 016 | CLARIFY [016, 042] |
| 59 | 경복궁 일대 동 경계 보여줘 | 033 · admin_level 읍면동 | SELECT 033 · admin_level null |
| 82 | 청주역 지역구 공약 중에 교통 분야만 보여줘 | 042 | CLARIFY [010, 042] |
| 85 | 강릉역 선거구 의원 공약 목록 줘 | 042 | CLARIFY [016, 042] |
| 96 | 환경부 충전소 충전기 몇 대 비었어 | 052 · argument 환경부 | SELECT 052 · argument 환경부 충전소 |
| 97 | 이마트 충전소에 빈 충전기 있는지 알려줘 | 052 · argument 이마트 | SELECT 052 · argument 이마트 충전소 |
| 99 | GS칼텍스 전기차 충전소 지금 쓸 수 있는지 봐줘 | 052 | CLARIFY [052, 060] |
| 114 | 강남역 부근 전기차 충전소 빈 충전기 몇 대야 | 060 | CLARIFY [052, 060] |
| 119 | 대전역 도달권 지도에 그려줘 | 061 | CLARIFY [061, 063] |
| 191 | 지금 보이는 곳 충전소 빈 충전기 알려줘 | 056 | CLARIFY [026, 056] |
| 199 | 이번 달 철도 사고 보고서 써줘 | NO_MATCH | SELECT 014 |

These are measurements, not defects that were fixed. The open human decisions they point at are
the 015/016, 052/060 and 061/063 menu boundaries, and the convention for
「keyword + category noun」 arguments (96, 97).

## Against the previous run

`20260918-161110-test_suite_v2-e2cf28` measured the **219-case** suite under the old
out-of-scope definition and stays in the repository unchanged. Its numbers are not restated
under the 203-case definition. The in-scope part is directly comparable and is identical:

| | 0918 run (219 cases) | this run (203 cases) |
|---|---|---|
| Selection | 184/195 | 184/195 |
| Semantic fields | 187/190 | 187/190 |
| Joint | 181/195 | 181/195 |
| Out-of-scope | 15/24 (old definition) | 7/8 (NO_MATCH only) |
| Errors | 0 | 0 |
| latency median / p95 | 1.637 / 1.882 s | 1.628 / 1.863 s |

The 14 in-scope failures are the same 14 cases. The out-of-scope figure is not comparable:
16 of the old 24 cases (the CLARIFY / MISSING_ARGUMENT ones) were removed from the suite
because they measure asking-back behaviour, not「no supported function exists」.

## Tests at the time of the run

`pytest`: 476 passed, 1 failed. The one failure is the known environmental graphviz difference
`test_dense_graph_would_move_if_overlap_removal_were_used`, which also failed before this work.
No new regressions.
