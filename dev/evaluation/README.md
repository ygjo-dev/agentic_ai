# dev/evaluation

발화 해석(Resolve)을 정답표로 재는 벤치마크.

```
run_evaluation.py              main. 벤치마크 한 번을 돌린다 (화면 테스트 탭도 이것을 부른다)
                               /resolve 부르기 · 지도 문맥의 원본
engine/                        안쪽 일
  load_test_suite.py             정답표 목록 · 읽기 · 구조 검사 · 신원(sha256)
  score.py                       채점 규칙의 원본. 네 칸 판정 · 값 대조 · failure_stage · 합계 · 지표
  manage_benchmark.py            저장 · 목록 · 불러오기 · 도중에 끝난 것 복구
  monitor_metadata.py            실행 조건 (모델 · 역할 · 요청 설정 · prompt/schema/menu sha256 · git HEAD)
  monitor_gpu.py                 GPU 이름 · VRAM, 사무실 조용 정책(박자만)
inputs/test_suites/            정답표 (Test Suite). v1 = FULL48 회귀 기준선, v2 = 203 발화
outputs/official_benchmark/    골라서 남긴 기준 벤치마크. Git 이 추적한다
outputs/local_benchmark/       보통 실행. Git 이 무시한다. 새 실행은 여기로 간다
```

계기판 `dev/tools/check_resolve.py` 는 여기의 공개 함수를 가져다 쓴다. 이 폴더는 check_resolve 를 import 하지 않는다.

```
python dev/evaluation/run_evaluation.py --suite dev/evaluation/inputs/test_suites/test_suite_v2.yaml --gpu gate
```

창구(8000)와 LLM 이 떠 있어야 한다.

## run_id

```
YYYYMMDD-HHMMSS-test_suite_vN      20260921-132500-test_suite_v2
같은 이름이 있으면 -2, -3, …       official · local 두 자리를 통틀어 본다. 무작위 글자는 안 붙인다
```

official · local 은 보관 갈래다. run_id 에 들어가지 않는다. 기준으로 남기려면 local 폴더를
run_id 그대로 `outputs/official_benchmark/` 로 옮겨 커밋한다.

## 파일

```
도는 동안      meta.json + cases.jsonl     발화 하나가 끝날 때마다 한 줄. 죽어도 끝난 줄이 남는다
끝나면         run.json 하나               잴 것을 다 잰 때만. run.json 을 다 쓴 뒤에 나머지 둘을 지운다
멈춤          meta.json + cases.jsonl     중지 · ServerDown · StopRun · 끊김. meta.json 에 까닭(stopped)을 적는다
도중에 죽음    meta.json + cases.jsonl     목록에 「중단됨」으로 나오고 그 줄들로 다시 세워 읽는다
```

run.json 이 있으면 끝난 기록이다. 남은 meta.json · cases.jsonl 은 안 읽는다.
멈춘 기록에 run.json 을 쓰지 않는다.

## 중지 · 이어 실행

- `run(..., should_stop=)` 은 Resolve 를 부르기 바로 앞에서만 본다. 이미 부른 발화는 끝까지 기다려 남긴다
- `resume(kind, run_id)` 는 끝나지 않은 local 기록을 같은 run_id · 같은 폴더에서 잇는다.
  잴 것은 계획(selected_case_ids × runs) 중 (case_id, run) 이 아직 없는 것뿐이다. 다 재면 그 폴더에 run.json
- 정답표 · 문맥 · materialize 부르는 순간 · 쉼 설정은 저장된 머리를 그대로 쓴다
- `resume_check` 가 같아야 할 조건을 맞댄다 (`monitor_metadata.RESUME_FIELDS`):
  정답표 sha256 · 모델 · prompt · 응답 schema · menu · 게시 자산 · 요청 설정 · 결과 판.
  git HEAD · 시각 · 저장 자리 · GPU · 화면 정렬은 안 본다. 저장된 머리에 칸이 없으면 짐작하지 않고 막는다
사람이 읽는 보고서 형식은 아직 정하지 않았다. 요약 글 · 표 · 그림 파일을 만들지 않는다.

## 불러오기 · 화면 표

- 목록은 official · local 을 합쳐 시작 시각 최근 것이 앞. 불러올 때는 (kind, run_id) 를 함께 넘긴다
- 같은 run_id 가 두 자리에 다 있으면 틀린 상태로 알리고 어느 쪽도 골라 주지 않는다
- 테스트 세트를 고르면 그 발화 전부가 「대기」 줄로 바로 보인다. LLM 은 안 부른다
- 새로 실행 · 이어 실행은 줄을 덧붙이지 않고 같은 case_id 의 줄을 결과로 바꾼다
- 저장한 기록을 불러오면 그 테스트 세트의 같은 표에 결과를 얹는다
