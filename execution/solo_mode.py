"""★ 임시 · 보도자료용. 독파모 단독 모드 — 온톨로지를 통째로 건너뛴다.

**이 파일 전체가 임시다** (2026-09-03). 보도자료 그림 2의 왼쪽 칸(독파모
단독)을 저쪽 화면에서 찍으려고 둔 것이다. 같은 UI 에서 왼쪽은 모델만,
오른쪽은 모델 + ASAP 이 보이게 하는 것이 목적이다.

**환경변수 하나로 켜고 끈다. 기본은 꺼짐이다.** 꺼져 있으면 이 파일의
`enabled()` 한 줄 말고는 아무것도 안 불린다 — 지금 도는 것이 글자 하나
안 바뀐다.

**걷을 때는 이 파일을 지우고 execute_service.chat 맨 앞의 세 줄을 지운다.**
그 둘이 전부다. 임시 자리를 한 자리에 모아 둔 까닭이 그것이다 (execute_service
의 HIDDEN_NODES · PALETTE_CUTOFFS · RADIUS_CIRCLE_* 옆에 이 파일을 가리키는
주석 한 줄이 있다).

**끼우는 자리가 execute_service.chat() 맨 앞인 까닭.** resolve 를 부르기
전에 가로채야 「요청 이해」 단계 이벤트도 안 나간다. run 에서 가로채면
발화 해석 단계가 이미 화면에 그려진 뒤다 — 왼쪽 칸에 생성과정이 하나도
없어야 한다.

**저쪽(KRRI_ASAP)은 안 고친다.** 저쪽 화면은 우리가 주는 answer 와 commands 를
그대로 그리는 껍데기다.
"""

import json
import os
import re
import urllib.request

# 켜는 환경변수. 값이 아래 참 낱말이면 켜진다.
#
# **없거나 다른 값이면 꺼짐이다.** 시연 장비에서 실수로 켜져 있는 것이
# 꺼져 있는 것보다 훨씬 나쁘다 — 켜져 있으면 답이 조용히 모델 것으로 바뀌고
# 화면만 봐서는 온톨로지를 탄 답인지 아닌지 구별이 안 된다.
ENV_FLAG = "SOLO_MODE"
TRUE_WORDS = {"1", "true", "on", "yes"}

# 부를 모델. 독파모(solar-open-100b) 다.
#
# ★ 62GB 라 첫 호출이 몇 분 걸린다. 그래서 타임아웃이 900초다 — 저쪽 화면이
# 먼저 끊으면 왼쪽 칸을 못 찍는다.
MODEL = os.environ.get("SOLO_MODE_MODEL", "solar-open-100b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
TIMEOUT = 900.0

# 모델에 주는 지시. 두 마디다.
#
# **길게 쓰지 않는다.** 이 그림의 요지는 「모델만 쓰면 이런 답이 나온다」이므로
# 지시로 답을 다듬으면 그림이 거짓말이 된다. 한국어와 「사고 과정 금지」
# 둘만 말한다.
SYS = "반드시 한국어로만 답한다. 사고 과정을 쓰지 말고 최종 답만 낸다."

# raw 프롬프트의 토막들.
#
# ★ **/api/chat 을 안 쓴다** (2026-09-02 실측). ollama 의 /api/chat 은
# 사고 과정이 끝없이 나온다. reasoning_effort 기본이 "high" 인데 ollama 가
# 그 값을 템플릿에 안 넘긴다 — `/set parameter` · `options` · `think: false`
# 셋 다 안 먹었다. /api/generate 에 raw 프롬프트를 직접 짜 넣으면 된다.
BEGIN = "<|begin|>"
CONTENT = "<|content|>"
END = "<|end|>"
# 마지막 줄의 **빈 think 블록**이 사고 단계를 건너뛰게 한다. 이 한 토막이
# 이 방법의 전부다.
TAIL = f"{BEGIN}assistant<|think|>{END}{BEGIN}assistant"

# 응답 앞에 사고 과정이 그래도 붙어 나올 때 자르는 자리.
#
# 실측한 예 — 영어 사고가 길게 이어지다 `<|end|>assistant` 뒤에 한국어 답이
# 온다. **마지막** 그것 뒤만 취하고, 없으면 통째로 쓴다.
THINK_CUT = f"{END}assistant"

# 화면을 옮길 곳 — 의왕역.
UIWANG_LON = 126.9482
UIWANG_LAT = 37.3201
# flyTo 는 bbox 를 받는다 (vendor_to_be_deleted/asap/command_renderer 의
# _point_focus_command 와 같은 모양 · 같은 값이다).
FLY_DELTA = 0.02
FLY_DURATION = 2.0

# 지울 레이어 여섯.
#
# ★ **여섯을 다 지운다.** 오른쪽 칸(모델 + ASAP)을 찍은 뒤 왼쪽을 찍으면
# 앞 도형이 지도에 그대로 남는다. 하나라도 빠뜨리면 「모델은 지도를 못
# 그린다」는 답 옆에 도형이 남아 앞뒤가 안 맞는다.
#
# `shadow-hull` 은 지금 아무도 안 내는 이름이다 — 볼록 껍질을 그리던 시절의
# 자리이고, 옛 화면이 그것을 들고 있을 수 있어 함께 지운다.
CLEARED_LAYERS = [
    "r5-isochrone-polygons",
    "r5-isochrone-lines",
    "r5-isochrone-points",
    "r5-isochrone-origin",
    "shadow-hull",
    "radius-circle",
]

# 저장해 둔 답 둘. ★ **지금은 아무도 안 본다** (2026-09-03).
#
# `reply` 가 발화마다 독파모를 실제로 부른다. 아래 `SAVED` 를 읽는 자리가
# 없다.
#
# **왜 안 쓰기로 했나 — 촬영 중에 띄어쓰기 하나로 어긋났다.** 발화가
# 「보여 줘」와 「보여줘」로 갈려 저장된 답이 안 걸렸다. 저장해 둔 답이
# 걸리느냐 마느냐로 답이 통째로 갈리는데, **화면만 봐서는 어느 쪽이
# 나왔는지 알 수 없다** — 촬영장에서 가장 나쁜 성질이다. 늘 부르면 늘
# 같은 성질의 답이 나온다.
#
# **그래도 지우지 않는다.** 2026-09-03 에 solar-open-100b 가 **실제로 낸
# 답이라 기록이 된다.** 줄바꿈 · 번호 · 기호 · 이모지까지 그대로다.
# 다시 쓸 일이 있으면 `reply` 의 한 줄로 되살아난다 —
# `answer = SAVED.get(_key(text)) or _ask(text)`.
#
# ★ 첫 답에 사실과 다른 것이 있다 (수원역 15분 · 안양역 10분 · 303번 버스).
# **고치지 않는다 — 그것이 이 그림의 요지다.** 모델만 쓰면 그럴듯한 틀린
# 수가 나오고, ASAP 을 붙이면 실제 도달권이 나온다는 것을 나란히 놓는 그림이다.
REACH_QUESTION = "의왕역에서 30분 안에 갈 수 있는 곳을 보여 줘"
MAP_QUESTION = "의왕역 주변 지도로 그려서 보여 줘"

REACH_ANSWER = """의왕역에서 30분 이내에 도착 가능한 주요 장소를 안내해 드리겠습니다. 대중교통 기준 이동 시간은 다음과 같습니다.

### 1. **수원역 (약 15분, 지하철 + 버스)**
   - **경로**: 의왕역 → 1호선 탑승 → 수원역 하차 → 도보 이동
   - **특징**: 수원역 주변 쇼핑, 맛집, 문화시설이 풍부하며, 수원 화성 관광도 가능합니다.

### 2. **안양역 (약 10분, 지하철)**
   - **경로**: 의왕역 → 1호선 탑승 → 안양역 하차
   - **특징**: 안양시청, 안양예술공원, 평촌 중앙공원 등 접근 가능하며, 번화가와 근접합니다.

### 3. **의왕 백운호수 (약 10분, 버스)**
   - **경로**: 의왕역 → 303번 버스 탑승 → 백운호수 정류장 하차
   - **특징**: 자연 경관이 아름다운 호수로, 산책로와 카페가 많으며 계절별 풍경이 독특합니다.

### 4. **의왕 레일파크 (약 10분, 버스)**
   - **경로**: 의왕역 → 303번 또는 307번 버스 → 레일파크 정류장 하차
   - **특징**: 철도 테마 공원으로, 철도 박물관, 체험시설, 전망대가 있어 가족 단위 방문객에게 적합합니다.

### 5. **의왕 부곡체육공원 (약 10분, 버스)**
   - **경로**: 의왕역 → 303번 버스 → 부곡체육공원 정류장 하차
   - **특징**: 축구장, 배드민턴장 등 스포츠 시설이 잘 갖춰져 있으며, 주말에는 지역 주민들이 많이 이용합니다.

### 📌 이동 팁
- **지하철**: 1호선을 타면 **수원**, **안양**, **서울** 등 주요 도시까지 빠르게 이동 가능합니다.
- **버스**: 303번 버스는 의왕역 정류장에서 바로 승차 가능하며, 백운호수·레일파크·부곡체육공원으로 연결됩니다.
- **도보**: 의왕역 주변(약 5분 거리)에는 편의점과 소규모 상점이 밀집해 있습니다.

추가로 특정 장소(예: 카페, 관광지)에 대한 정보가 필요하시면 알려주세요! 😊"""

MAP_ANSWER = """죄송하지만 저는 지도를 직접 그려서 보여드릴 수 없습니다. 대신 의왕역 주변을 설명드릴게요. 의왕역 주변에는 버스정류장, 편의점, 카페, 식당 등이 가까이 있어 이동이 편리합니다. 1호선을 이용하면 수원역, 안양역 등 주요 도심으로 빠르게 갈 수 있어요. 또한 303번 버스는 백운호수, 레일파크, 부곡체육공원 등 주요 관광지로 연결해 줍니다. 구글 지도나 네이버 지도 같은 온라인 지도 서비스를 이용하면 실시간 교통 정보와 주변 시설 위치를 확인할 수 있습니다. 공식 철도청 홈페이지에서도 역 주변 교통 안내와 관광 정보를 제공하고 있으니 참고해 보세요. 궁금하신 구체적인 장소나 교통편이 있으면 추가로 알려드릴게요."""

SAVED = {
    REACH_QUESTION: REACH_ANSWER,
    MAP_QUESTION: MAP_ANSWER,
}

# 켜져 있는 동안의 주고받기. 다음 요청에 앞 대화로 실린다.
#
# **둘째 발화가 첫 답을 알고 있어야 자연스럽다.** 「지도로 그려서 보여 줘」는
# 앞의 「30분 안에 갈 수 있는 곳」을 받는 말이라 앞 대화가 없으면 무엇의
# 지도인지 모른다.
#
# ★ **프로세스가 살아 있는 동안만이다.** execute_service.chat 이 상태를 안
# 두는 자리인 것을 알고 있고(그 docstring 의 제약), 이것은 그 규칙을 어기는
# 임시 자리다 — 스위치와 함께 걷힌다.
_HISTORY: list[tuple[str, str]] = []


def enabled() -> bool:
    """단독 모드가 켜져 있는가.

    입력  없음. 환경변수 SOLO_MODE 를 본다
    출력  참이면 켜짐
    규칙  값이 TRUE_WORDS 에 있을 때만 참. 대소문자는 안 본다
    제약  값을 캐두지 않는다.
          띄운 채로 껐다 켤 수 있어야 한다 (저쪽 화면을 다시 안 띄우려는 것)
    """
    return os.environ.get(ENV_FLAG, "").strip().lower() in TRUE_WORDS


def forget() -> None:
    """앞 대화를 잊는다. 사진을 다시 찍기 전에 부른다."""
    _HISTORY.clear()


def reply(text: str) -> tuple[str, list[dict]]:
    """발화 한 건에 단독 모드의 답과 지도 명령.

    입력  발화
    출력  (답 문자열, 지도 명령 목록)
    규칙  발화가 무엇이든 독파모를 실제로 부름. 저장해 둔 답을 안 봄
          지도 명령은 무엇을 물었든 같음 — 레이어 여섯을 지우고 의왕역으로 옮김
          주고받기를 기억해 둠. 다음 요청에 앞 대화로 실림
    제약  폴리곤을 그리지 않는다.
          모델이 「지도를 못 그린다」고 답하므로 도형이 있으면 앞뒤가 안 맞는다
          저장해 둔 답으로 갈아치우지 않는다.
          걸리느냐 마느냐가 띄어쓰기 하나로 갈리는데 화면만 봐서는 어느
          쪽이 나왔는지 알 수 없다 (위 SAVED 주석)
    """
    answer = _ask(text)
    _HISTORY.append((text, answer))
    return answer, commands()


def commands() -> list[dict]:
    """단독 모드의 지도 명령. 지우고 옮기기만 한다."""
    cleared = [
        {"op": "map.clear", "args": {"layerId": layer}} for layer in CLEARED_LAYERS
    ]
    return cleared + [
        {
            "op": "view.camera.flyTo",
            "args": {
                "bbox": [
                    [UIWANG_LON - FLY_DELTA, UIWANG_LAT - FLY_DELTA],
                    [UIWANG_LON + FLY_DELTA, UIWANG_LAT + FLY_DELTA],
                ],
                "duration": FLY_DURATION,
            },
        }
    ]


def _key(text: str) -> str:
    """★ **안 쓴다.** 저장한 발화와 견줄 꼴. 앞뒤 공백과 겹공백만 고른다.

    `SAVED` 와 함께 서 있고 부르는 자리가 없다. 저장한 답을 되살릴 때
    `reply` 가 다시 부르는 짝이라 함께 남긴다 (위 SAVED 주석).

    ★ 저장한 문자열 자체는 안 건드린다. 견줄 때만 공백을 고른다 —
    다만 이것으로도 「보여 줘」와 「보여줘」는 못 맞춘다. 겹공백은 고르지만
    없는 공백을 만들어 내지는 않는다. 촬영 중에 어긋난 자리가 그것이다.
    """
    return re.sub(r"\s+", " ", text or "").strip()


def _ask(text: str) -> str:
    """독파모를 raw 프롬프트로 부른다.

    입력  발화
    출력  사고 과정을 걷어낸 답
    규칙  /api/generate 에 raw 로 보냄. 앞 대화를 함께 실음
    제약  형식(format)을 안 준다.
          이 그림은 모델이 자기 말로 답하는 모습이라 JSON 틀을 씌우면 안 된다
    """
    body = json.dumps(
        {"model": MODEL, "raw": True, "stream": False, "prompt": _prompt(text)}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{HOST}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = json.loads(response.read().decode("utf-8"))["response"]
    return _clean(raw)


def _prompt(text: str) -> str:
    """raw 프롬프트 한 벌. 실측해 둔 모양 그대로다."""
    parts = [f"{BEGIN}system{CONTENT}## System Prompt\n\n{SYS}{END}"]
    for asked, answered in _HISTORY:
        parts.append(f"{BEGIN}user{CONTENT}{asked}{END}")
        parts.append(f"{BEGIN}assistant{CONTENT}{answered}{END}")
    parts.append(f"{BEGIN}user{CONTENT}{text}{END}")
    parts.append(TAIL)
    return "".join(parts)


def _clean(raw: str) -> str:
    """사고 과정과 남은 표식을 걷는다.

    입력  /api/generate 가 준 response 문자열
    출력  화면에 그대로 나갈 답
    규칙  마지막 THINK_CUT 뒤만 취함. 없으면 통째로 씀
          남은 <|content|> · <|end|> 를 지움
    """
    text = raw.rsplit(THINK_CUT, 1)[-1] if THINK_CUT in raw else raw
    return text.replace(CONTENT, "").replace(END, "").strip()
