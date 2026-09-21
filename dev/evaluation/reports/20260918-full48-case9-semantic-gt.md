# FULL48 #9 — semantic GT cleanup (2026-09-18)

start HEAD `f3e020e` → final `2010a92` "문서 검색 발화의 semantic 정답을 명확히 한다" · tree clean · PUSH none

## What the audit had left open

The 2026-09-18 GT audit (see `20260918-full48-gt-audit.md`) could not fill `expected.spoken.argument`
for case #9. The utterance was "철도안전법 조문 문서에서 찾아줘" and `knowledge.query`'s `query`
accepts both "철도안전법" and "철도안전법 조문"; the tool description does not separate them.
The audit recorded it as a human decision, not as a model error.

## The decision

A human settled it the same day and edited the utterance, which is why the old and the new
measurement of this line are not comparable — the utterance itself changed.

| | before | after |
|---|---|---|
| utterance | 철도안전법 조문 문서에서 찾아줘 | 문서에서 철도안전법 관련 내용 찾아줘 |
| expected.recipe_ids | `[recipe_014]` | `[recipe_014]` (unchanged) |
| expected.spoken | *(absent)* | `argument: "철도안전법"` |

Reasoning recorded in the suite file: 「문서에서」 and 「관련 내용 찾아줘」 carry the
document-search intent, so the thing being searched for is 「철도안전법」 alone — 「조문」 does
not belong in `argument`. The other 47 cases are byte-identical.

## Coverage change

| | before | after |
|---|---|---|
| scored semantic cases | 38 | 39 |
| scored semantic fields | 55 | 56 |
| argument | 29/30 keys present | 30/30 |

## Live measurement (FULL48 × 1, suite sha equal to the committed GT)

model solar-open2-250b · vllm · resolve role v1 · prompt v1 · schema v1 · context both · materialize on

| metric | result |
|---|---|
| Selection | 48/48 |
| Semantic fields | 56/56 (argument 30/30 · admin_level 14/14 · travel_mode 6/6 · minutes 6/6) |
| Semantic cases | 39/39 |
| Joint | 48/48 |
| Errors | 0 |
| LLM calls / retries | 48 / 0 |
| latency (resolve_s) | min 1.33 · median 1.64 · max 1.96 · total 79.7 s |

Failed cases: none.

Tests: `spoken_audit` / `runner` / `check_resolve` selfchecks OK · targeted 39 passed ·
full 435 passed with the one known graphviz failure · new regressions 0.

Resolve v1 stayed frozen — no prompt, schema or model change was made in response to anything here.
