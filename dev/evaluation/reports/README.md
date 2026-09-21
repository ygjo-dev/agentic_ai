# 평가 보고서

여기는 **평가의 저장소 기록**이다. 정답표를 왜 그렇게 적었나, 한 번 재서 무엇이 나왔나,
무엇이 사람이 정할 자리로 남았나. 그 자리의 원천이 이 폴더다.

    dev/evaluation/test_suites/   무엇이 정답인가 (Test Suite)
    dev/evaluation/test_runs/     언제 어느 모델로 재서 무엇이 나왔나 (Test Run)
    dev/evaluation/reports/       그것을 사람이 읽는 글로 적은 것  ← 여기

`/home/ubuntu/claude_handoff/` 는 모바일로 옮기기 위한 편의 보관소로 남아 있다. 평가의
source of truth 는 여기다 — 그쪽은 기계에 있고 저장소에 없다.

## 있는 것

| 파일 | 무엇 |
|---|---|
| `test-run-schema.md` | Test Run 결과 한 벌(result_version 3)의 칸과 낱말. 판을 올릴 때 함께 고친다 |
| `20260918-full48-gt-audit.md` | FULL48 정답표 감사. 무엇을 채점하고 무엇을 안 채점하나를 execution 에서 다시 끌어냄 |
| `20260918-full48-gt-audit-table.md` | 위 감사의 발화별 표 |
| `20260918-full48-gt-audit-run.txt` | 새 정답표로 잰 FULL48 실측 한 장 |
| `20260918-full48-case9-semantic-gt.md` | 감사가 사람에게 남긴 #9 를 사람이 정한 기록 |
| `20260918-test-suite-v2-initial.md` | 테스트 세트 v2 를 만든 기록 (그때는 219 발화) |
| `20260918-test-suite-v2-initial-live-run.md` | 그 첫 실측 한 번 |
| `20260918-test-suite-v2-initial-failures.md` | 그 실패 23 건의 갈래 |
| `20260918-test-suite-v2-oos-ui-cleanup.md` | 범위 밖의 뜻을 하나로 좁혀 219 → 203 으로 줄인 기록 |
| `20260921-test-suite-v2-canonical-run.md` | 203 발화 정답표의 기준 실측 |

## 규칙

- **옛 보고서를 새 정의로 고쳐 쓰지 않는다.** 219 발화로 잰 글은 219 발화로 잰 글이다.
  뒤에 정의가 바뀌었으면 새 글을 더한다. 그래야 두 값이 왜 다른지가 남는다
- 안에 적힌 경로 · 이름은 **그때의 것**이다 (`resolve_regression.yaml` ·
  `dev/tools/sweep_out/test_runs/` · dataset id `resolve_regression`). 2026-09-21 에
  `dev/evaluation/test_suites/test_suite_v1.yaml` · `dev/evaluation/test_runs/` ·
  `test_suite_v1` 로 갈렸다. 글은 안 고친다
- 큰 raw 덤프(전체 diff · 응답 JSON 전문 · GPU 로그)는 안 담는다. diff 는 git 이 들고 있고
  결과 한 벌은 `../test_runs/` 에 있다
