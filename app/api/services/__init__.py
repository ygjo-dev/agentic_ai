"""도메인 모듈을 호출해 API 가 쓸 형태(DTO)로 바꾸는 계층.

부르는 쪽으로 나뉜다.

    streamlit/  Streamlit 화면만 쓰는 것 (screen_service · node_service)
    bridge/     KRRI_ASAP 웹과 Streamlit 을 잇는 것 (recent_service)

KRRI_ASAP 웹만 쓰는 폴더는 없다. 그쪽이 부르는 것은 `/chat/stream` 하나이고
그 알맹이는 execution/ 에 있다.
"""
