"""온톨로지를 SVG 로 그린다.

브라우저 없이 도는 코드만 여기 있다. subprocess 로 Graphviz 를 부르고 좌표
파일을 쓰므로 서버 일이다 — 프론트엔드가 프로세스를 띄우고 있을 이유가 없다.

  dot.py           DOT 문자열. 색 · 굵기 · 길이의 단일 출처
  graphviz.py      dot / neato 실행과 SVG 후처리
  layout_store.py  좌표 저장 · 회전 · 증분 배치
  focus.py         경로 좁히기와 칩 데이터 (순수 함수)
  build.py         변형 조립과 캐시

이 패키지는 ontology 를 import 하지 않는다. 도메인 데이터는 graph_service 가
읽어서 넘겨준다 — 저장소가 그래프 DB 로 바뀌어도 여기는 그대로다.
"""
