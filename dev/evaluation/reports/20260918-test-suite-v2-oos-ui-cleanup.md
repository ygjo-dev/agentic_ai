# Test Suite v2 — semantics + Streamlit UI cleanup (2026-09-18)

start `4f9540d` → final `d24553c` "테스트 범위와 평가 화면의 의미를 정리한다" · tree clean · PUSH none · no live benchmark run

## Suite
- The OOS definition is now "no supported function may be chosen", so the only correct outcome is NO_MATCH.
- v2 went from 219 to **203** cases: 195 in-scope (39 recipes × 5, min 5) and **8 OOS** (unsupported, NO_MATCH).
- Removed: 8 ambiguous (CLARIFY expected) and 8 insufficient (CLARIFY/MISSING_ARGUMENT expected), 16 in total. They were ids 204–219.
- Enforced by: the loader (`OOS_OUTCOMES = ("NO_MATCH",)`, rejects CLARIFY/MISSING_ARGUMENT), `spoken_audit.integrity` (every OOS is `[NO_MATCH]`), and tests.
- FULL48 is unchanged.

## Metadata (new runs; result_version stays 3, optional fields)
- `conditions.request`: the provider's actual request settings, currently `{temperature: 0, seed: 0, max_tokens: 1024, reasoning_effort: "none"}`. They are read by building the real provider and intercepting its outgoing request, not hardcoded. llm_engine is untouched.
- `meta.environment`: `{available, gpus: [{index, name, memory_total_mib}]}`. No temperatures. The GPU gate still paces calls but records nothing in the result.
- `expected.reads`: the fields the expected recipe's execution reads. This drives the "사용 안 함" vs "없음" display.
- Old runs such as `20260918-161110-test_suite_v2-e2cf28` load unchanged. Their historical OOS verdicts are not rescored. `meta.gpu` is ignored. Temperature and GPU show "기록 없음".

## UI
- Top: 테스트 세트 · 시작 시간 · 소요 시간 · 추론 지연시간 (Median / P95 / Max, stacked) · 발화 (전체 / 성공 / 실패 / 오류) · 모델 설정 (모델, Temperature) · 실행 환경 (GPU, VRAM). No evaluation metrics.
- Lower "전체 결과": 전체 · 성공 % · 실패 % · 오류 · 기능 선택 실패 · 인자 추출 실패 · 범위 밖 처리 실패. Each cause card says "실패 원인 · 먼저 걸린 것", because the runner assigns exactly one stage per case. There is no sum line.
- Removed from the whole test tab: 실행 준비 / READY (workflow readiness) · 처리 결과 · 발화 성공 · 채점 제외 · 걸린 시간 · 실행 조건 · 응답 시간 · all °C and thermal info.
- Renamed: 응답 시간 → 추론 지연시간, 실행 조건 → 모델 설정 (collapsible: 모델, provider, Temperature, Seed, Max tokens, Reasoning effort, 호출 상한, files, run id).
- Field display: "사용 안 함" means the expected recipe doesn't read the field (both columns). "없음" means it reads the field and the value is null.
- 기능별 결과: exactly that title, supported recipes only (OOS excluded), numeric ascending by recipe number.
- Candidate chips: `title=` tooltip with the menu function sentence from `meta.functions`, i.e. `runner.functions()` = the published menu.yaml. There is no new mapping.

## Verification
- Targeted 69 passed. Full 457 passed, 1 failed (the known graphviz test).
- AppTest smoke with the real old saved run: 219 rows, expanders ['모델 설정', '기능별 결과'], no retired words.
- `run_dataset` with a fake resolver shows Temperature 0 and GPU "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition × 4", 장당 95.6 GiB.
- Protected areas unchanged: llm_engine, orchestrator, execution, Registry, FULL48. KRRI_ASAP is at 311187e with no changes from this work.
