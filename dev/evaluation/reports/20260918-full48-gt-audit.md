# FULL48 GT AUDIT — 2026-09-18

repo `/home/ubuntu/source/agentic_ai` · branch `feature/mcp-expansion` · start HEAD `03ea2fc` (clean)

## 1. Scoring rule (unchanged)

`dev/evaluation/runner.spoken_fields` / `check_resolve._spoken_value_verdict`:

- GT `expected.spoken` has the key → scored (`_value_mark(actual) == _value_mark(expected)`)
- key absent → not scored, whatever the model returns
- key present with `null` → `null` is the correct answer (“don't invent it”)
- list values compare as comma-joined (`[15, 30, 60]` → `15,30,60`)

This rule was not changed.

## 2. Audit basis — what "consumed" means

The spoken refs were extracted from every expected Recipe.execution with a generic walker
(`dev/evaluation/spoken_audit.py`, which has no per-case code). The materializer semantics
(`execution/workflow_materializer.py`) decide how each ref is used:

| ref form | materializer behaviour | GT consequence |
|---|---|---|
| `{from: spoken.argument}` (required) | `spoken_needed: true` → empty argument ⇒ `MISSING_ARGUMENT`, nothing is called; value passed to the tool verbatim | score the exact value when the utterance names it |
| `{from: spoken.argument, if_endswith/unless_endswith: 선}` | condition picks `railwayName` vs `stationName` (recipe_003) | same argument; the condition follows from its shape |
| `{from: spoken.<name>, default, map}` | `null`/empty ⇒ default; value not in the map ⇒ **silently falls back to the default** | score the level/mode/minutes when spoken, `null` when not spoken (an invented value replaces the default and changes the call) |

Spoken refs found across all 39 recipes: **`argument`, `admin_level`, `travel_mode`, `minutes`**. No other name exists.

| field | recipes that read it | how |
|---|---|---|
| argument | 001 002 003 004 005 008 010 012 014 015 016 033 034 036 038 040 042 045 049 052 058 059 060 061 062 | required (003: conditional on the `선` suffix) |
| admin_level | 005 018 024 033 034 054 055 058 059 | default 시군구, map 시도/시군구/읍면동 → sido/sigungu/emd |
| travel_mode | 061 063 | default 대중교통, map 도보/자전거/승용차/대중교통 → WALK/BICYCLE/CAR/TRANSIT |
| minutes | 061 063 | default [30] → cutoffs_minutes |

Context-only recipes (019 020 021 022 026 027 029 031 056) read **no** spoken field, so nothing is scored there, even though the Resolve schema always returns all four fields.

## 3. Sources for tool semantics (read-only)

- `KRRI_Ontology_Registry/recipes/*.yaml` execution blocks (published wiring)
- `execution/workflow_materializer.py` — `materialize` (MISSING_ARGUMENT), `_bound` (default/map/fallback, endswith conditions)
- `dev/tools/probe_out/tools.json` — Gateway inputSchema descriptions (e.g. searchAssemblyPledgeDistricts.query example "철도"; searchDistricts.query "선거구명 또는 검색어"; getDistrict.name "선거구명. 예: 서울 강서갑")
- `dev/tools/probe_out/*.json` live probes: getDistrict(name=충북 청주서원) 1건 · getAssemblyDistrict(name=청주시 흥덕구) 1건 · searchDistricts query=충북 8 = sido=충북 8 · searchAssemblyPledgeDistricts(query=철도) 206 · population.searchStatistics(query=청주시) 4 (four 구)
- the GT's own measured comments (`ev.searchStations(query=탄방동)` 11건, getSectionGeometry(충북선) 1건, geocode 의왕역, 충청북도 sido 43, ...)
- `KRRI_ASAP/ASAP-orchestrator/plugins/show-facility/plugin.md` (READ-ONLY): facilityName is a free string with no alias table

## 4. Decisions

**argument**: added wherever the recipe reads it and the utterance names the value unambiguously. The value is what the user said, with particles stripped (부산역이 → 부산역), not the model output.
- `#7 철도`, not 철도 공약: the tool's query field matches pledge text, and its own example value is "철도".
- `#10 충북 청주서원`, `#11 청주시 흥덕구`: both names resolve to one district in live probes.
- `#4 오송 테스트트랙 교량`: the full noun phrase. The frontend matching can't be verified, as the GT comment already says.
- `#37 조치원역`: recipe_062 reads argument as the destination. The origin comes from context.

**admin_level**: scored on every case whose recipe reads it (14 cases).
- The utterance names an admin unit or an explicit level word → that level. `#5 논산→시군구` (new) and `#13 「무슨 구」→시군구` (new) follow the existing `#21 전주시`, `#22 군산시`, `#27 오송읍`, `#29 충청북도`, `#30 「동」` and `#48 「읍면동」`.
- A POI or deixis with no level word → `null`. New: `#12 동대구역`, `#28 부산역 주변`, `#35 여기 연령대별`, `#36 여기 인구 변화`. Existing: `#41`, `#47`.

**travel_mode / minutes**: the 6 existing cases (24 25 26 38 39 40) were re-verified against the 061/063 map keys and the list shape. All KEEP.

**Not added**: argument on context recipes (the model often emits "여기", which nothing reads). admin_level on 008/012/015/016/052, which don't wire a layer. travel_mode on #37, which recipe_062 doesn't wire.

**REMOVE / CHANGE**: none. Every existing GT key is read by its recipe, and every existing value matched the execution meaning.

## 5. Expected Recipe audit

PASS 45 · QUESTION 3 · WRONG 0. No recipe_id changed.

| case | question |
|---|---|
| 10 충북 청주서원 선거구 정보 줘 → 015 | 016 also fits: 「정보」 doesn't say whether 당선인·공약 should be included (existing mark 겹침) |
| 20 탄방동 충전소 비었는지 알려줘 → 052 | 060 also fits: 탄방동 is both an address keyword (052) and a place that could be geocoded (060) |
| 31 여기 CCTV 띄워줘 → 019 | 026 also fits: 「여기」 doesn't say point vs screen (existing comment: 함께 걸림 026) |

## 6. Unresolved audit issues

1. **#9 argument (REVIEW, not scored)**: knowledge.query accepts both 「철도안전법」 and 「철도안전법 조문」, and the tool description doesn't separate them. A human needs to decide.
2. **admin_level 시군구 vs null are execution-equivalent** in #5, #13, #21 and #22, because the default is 시군구. The GT follows the pre-existing convention (named unit → its level), so a model `null` there is counted as an input miss even though the tool call would be identical. A human may want to relax this.
3. **Tool semantics caveat (not a GT issue)**: in cities with 일반구, the sigungu layer at a geocoded point returns the 구, not the city (the #29 comment documents 청주시 상당구). So #21 전주시 returns 완산구/덕진구, not 전주시. `population.searchStatistics(query=청주시)` (#8) returns 4 구 rows.
4. **Stale mark**: `marks: 26: "겹침" # 026` was left behind when the 2026-09-08 correction renumbered the cases. It belongs to case 31 (여기 CCTV, 함께 걸림 026), not case 26 (의왕역 자전거). Cases 20, 23 and 46 also carry 「함께 걸림」 comments without a mark. These are display-only and out of scope, so unchanged.
5. **Materializer map fallback**: an unmapped admin_level or travel_mode string (e.g. "시") silently executes as the default. The GT still counts it as an extraction miss, which is correct.

## 7. Coverage before / after

| | before | after |
|---|---|---|
| GT spoken cases | 14 | 38 |
| GT spoken fields | 20 | 55 |
| argument | 0 / 30 | 29 / 30 (#9 REVIEW) |
| admin_level | 8 / 14 | 14 / 14 |
| travel_mode | 6 / 6 | 6 / 6 |
| minutes | 6 / 6 | 6 / 6 |

Denominator: the cases whose expected recipe's execution reads that field (not the four-field schema × 48).
Actions: ADD 35 fields (argument 29 + admin_level 6) · KEEP 20 · CHANGE 0 · REMOVE 0 · REVIEW 1.
Per case: 31 gained fields (1–8, 10–29, 35, 36, 37) · 7 kept existing fields unchanged (30, 38, 39, 40, 41, 47, 48) · 9 read no spoken field (31–34, 42–46) · 1 unresolved (#9). Total 48.

## 8. Full48 on the new GT (1 run)

Selection 48/48 · argument 29/29 · admin_level 14/14 · travel_mode 6/6 · minutes 6/6 → fields 55/55, cases 38/38 · Joint 48/48 · Error 0 · READY 48.

Comparison: the old GT scored 20 expected values in 14 cases (14/14). The new GT scores 55 values in 38 cases. Resolve v1 met all 35 newly checked values, including every argument. **No failures.** The GT was fixed before the run (the result's suite sha256 equals the committed file), so this is not a GT fitted to model output. It is one run, and the burst/thermal caveats from earlier sessions still apply to single runs.

GPU: max 66°C, 1 pause, no thermal throttle, cooldown to 57°C at the end.

## 9. Files

- `dev/evaluation/resolve_regression.yaml` — +68 lines (59 GT lines + 9 comment lines). No utterance, recipe_id, mark or existing value touched.
- `dev/evaluation/spoken_audit.py` — new generic audit helper (CLI + `_selfcheck`)
- `dev/tests/tools/test_dashboard_selfchecks.py` — +1 test that calls `spoken_audit._selfcheck`
- Protected files unchanged: KRRI_Ontology_Registry/**, llm_engine/roles/resolve/**, orchestrator/resolve_service.py, execution/workflow_materializer.py
- KRRI_ASAP was read only. Its 5 pre-existing dirty entries have mtimes of 2026-09-09 or earlier.
