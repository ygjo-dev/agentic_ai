# Menu

Static Workflow 가 실행할 수 있는 Recipe 목록이다.
사용자 요청은 여기 적힌 Recipe 중 하나로만 해석한다.

이 문서는 사람이 읽으라고 둔 사본이다.
LLM 에 Context 로 전달되는 것은 [menu.yaml](menu.yaml) 뿐이므로, 한쪽을 고치면 다른 쪽도 같이 고친다.

실행 순서(steps)는 menu 에 없다. 각 Recipe 의 실행 정의는 [../recipes/](../recipes/)`<recipe_id>.yaml` 에 있다.

## 목차

| Recipe ID | 기능 |
| --- | --- |
| recipe_001 | 말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾는다. |
| recipe_002 | 말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾고 지도 범위 안의 CCTV 목록을 조회한다. |

---

# Recipe 001

## 기능

말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾는다.

---

# Recipe 002

## 기능

말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾고 지도 범위 안의 CCTV 목록을 조회한다.
