"""온톨로지 → 그래프 좌표와 화면이 받을 모형.

**여기서 그림이 나오지 않는다.** 화면 그래프는 vis-network 가 그리고 Graphviz 는
좌표만 낸다. 브라우저 없이 도는 코드만 여기 있다 — subprocess 로 Graphviz 를
부르고 좌표 파일을 쓰므로 서버 일이다.

  dot.py           Graphviz 가 배치를 잴 DOT 문자열. 색의 단일 출처이기도 하다
  graphviz.py      neato 실행과 DOT 배치 파싱 (좌표 · 노드 상자)
  layout_store.py  좌표 저장 · 회전 · 증분 배치
  focus.py         경로 · 칩 데이터 (순수 함수)
  build.py         /render 응답 조립. vis-network 가 받을 모형

`ontology.graph` 와 이름이 같지만 namespace 가 다르다 — 그것은 도메인이고
여기는 화면이 받을 모양이다. 실제로 import 가 부딪히는 자리는 없다.

이 패키지는 ontology 를 import 하지 않는다. 도메인 데이터는 screen_service 가
읽어서 넘겨준다.

**`api` 의 하위가 아니라 형제다.** 시연을 위한 것이라 통째로 갈릴 수 있는
자리이고, `api` 안에 두면 리뷰할 때 라우팅 코드와 섞여 읽힌다. `ui` 로 내릴
수도 없다 — 프로세스를 띄우고 좌표 파일을 쓰므로 내리면 프론트엔드에 Graphviz
설치가 요구사항으로 남는다.
"""
