# dev/evaluation

발화 해석(Resolve)을 정답표로 재는 벤치마크.

```
run_evaluation.py              main. 벤치마크 한 번을 돌린다 (화면 테스트 탭도 이것을 부른다)
engine/                        안쪽 일
  load_test_suite.py             정답표 목록 · 읽기 · 구조 검사 · 신원(sha256)
  score.py                       Resolve 출력 채점 · failure_stage · 합계 · 지표 · 요약 글
  manage_benchmark.py            저장 · 목록 · 불러오기 · 도중에 끝난 것 복구
  monitor_metadata.py            실행 조건 (모델 · 요청 설정 · prompt/schema/menu sha256 · git HEAD)
  monitor_gpu.py                 GPU 이름 · VRAM, 사무실 조용 정책(박자만)
inputs/test_suites/            정답표 (Test Suite). v1 = FULL48 회귀 기준선, v2 = 203 발화
outputs/official_benchmark/    골라서 남긴 기준 벤치마크. Git 이 추적한다
outputs/local_benchmark/       보통 실행. Git 이 무시한다. 새 실행은 여기로 간다
```

흐름

```
Test Suite → run_evaluation → Resolve → score → benchmark output
```

```
python dev/evaluation/run_evaluation.py --suite dev/evaluation/inputs/test_suites/test_suite_v2.yaml --gpu gate
```

창구(8000)와 LLM 이 떠 있어야 한다. local 실행을 기준으로 남기려면 그 폴더를
`outputs/official_benchmark/` 로 옮겨 커밋한다.
