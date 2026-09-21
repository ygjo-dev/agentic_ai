"""벤치마크를 어떻게 쟀나를 적는 곳. 재현에 필요한 실행 조건 · 파일 신원 · git HEAD.

    conditions()    모델 · provider · 역할 판 · 요청 설정 · prompt · 응답 schema · menu 파일과 sha256
    functions()     기능 설명 {recipe id: menu 의 function 문장}. 화면이 기능 번호 옆에 보임
    benchmark_meta  위 둘과 정답표 신원 · 문맥 · 쉼 설정을 모은 결과 meta 머리

실행 하드웨어(GPU 이름 · VRAM)는 monitor_gpu.environment 가 적는다.
**판정에는 안 섞인다.** 여기서 Resolve 를 부르지 않고 채점하지 않는다.
git 은 HEAD 를 읽기만 한다.
"""

import datetime
import hashlib
import json
import subprocess
import sys
import zoneinfo
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dev.evaluation.engine import load_test_suite  # noqa: E402
from dev.tools import check_resolve  # noqa: E402

KST = zoneinfo.ZoneInfo("Asia/Seoul")

# 결과 JSON 의 판. 칸의 뜻을 바꾸면 올린다.
# 3: 줄에 scope · recipe_group · outcome · oos_correct · timing.started_at, summary 에 metrics ·
#    latency · recipes, meta 에 run_id · elapsed_s · suite.name · suite.group_labels
#    뒤에 판을 안 올리고 더한 선택 칸: expected.reads · conditions.request · meta.environment.
#    이 칸이 없는 옛 결과도 그대로 읽힌다. 옛 결과의 meta.gpu(온도 기록)는 더 쓰지 않는다
RESULT_VERSION = 3


def _file_record(path: Path) -> dict:
    """실행 조건에 적을 파일 하나. {path, sha256}.

    규칙  저장소 안이면 저장소 뿌리에서의 상대 경로, 밖이면 절대 경로
          파일이 없으면 sha256 은 None
    """
    path = Path(path)
    try:
        shown = str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        shown = str(path)
    return {"path": shown, "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def conditions() -> dict:
    """이번 평가를 잰 조건. 모델 · prompt · 응답 schema · menu 파일과 그 sha256.

    출력  {model, provider, role_version, inference, request, prompt, response_schema, menu}. 파일 셋은 _file_record 꼴
          request 는 provider 가 요청마다 싣는 고정 설정(temperature · seed · …). request_settings 가 셈
          역할 설정을 못 읽으면 {error} 하나
    규칙  이 저장소의 역할 manifest 와 게시 menu 를 읽음. 창구가 같은 사본에서 떠 있을 때
          창구가 쓰는 판과 같음. /resolve 응답에는 판이 안 실림 (_role_label 과 같음)
          prompt · schema 경로는 역할 이름과 판 번호가 정함. role_config 의 규칙 그대로
    제약  못 읽었다고 평가를 멈추지 않는다. 재는 것은 창구임
    """
    import paths
    from llm_engine.role_config import RESOLVE, get_role_config

    try:
        role = get_role_config(RESOLVE)
    except ValueError as error:
        return {"error": f"역할 {RESOLVE} 못 읽음 ({error})"}
    role_dir = paths.ROLES_DIR / RESOLVE
    return {
        "model": role.model,
        "provider": role.provider,
        "role_version": role.version,
        "inference": dict(role.inference),
        "request": request_settings(role),
        "prompt": _file_record(role_dir / "prompts" / f"v{role.prompt_version}.yaml"),
        "response_schema": _file_record(role_dir / "response_schemas" / f"v{role.response_schema_version}.yaml"),
        "menu": _file_record(paths.MENU_YAML_PATH),
    }


# provider 요청 본문에서 설정이 아닌 칸. 모델 이름 · 발화 · 응답 형식이다.
_REQUEST_PAYLOAD_KEYS = ("model", "messages", "prompt", "response_format", "format", "stream")


class _Captured(Exception):
    """request_settings 가 요청을 가로챘다. 밖으로 안 나감."""


def request_settings(role) -> dict:
    """provider 가 이 역할로 부를 때 실제로 싣는 고정 설정. {temperature, seed, …}.

    규칙  get_llm_for(role) 로 진짜 provider 를 만들고 generate 를 한 번 부르되, 나가는 HTTP 요청
          (urllib.request.urlopen)을 가로채 본문만 읽음. 아무 데도 안 보냄
          본문에서 _REQUEST_PAYLOAD_KEYS 를 뺀 칸. 중첩 options(Ollama)는 펼쳐 붙임
          provider 를 못 만들거나(주소 없음 등) 모양이 다르면 {error}
    제약  값을 여기 적지 않는다. temperature 는 provider 코드가 정하고 그것을 읽을 뿐임.
          llm_engine 을 고치지 않는다
    """
    from unittest import mock

    from llm_engine.llm_selector import get_llm_for

    seen = {}

    def capture(request, *args, **kwargs):
        seen["body"] = json.loads(request.data.decode("utf-8"))
        raise _Captured

    try:
        llm = get_llm_for(role)
        with mock.patch("urllib.request.urlopen", capture):
            llm.generate("", {"type": "object"})
    except _Captured:
        pass
    except Exception as error:  # noqa: BLE001 — 기록을 못 해도 평가는 돈다.
        return {"error": f"{type(error).__name__}: {error}"}
    body = seen.get("body")
    if not isinstance(body, dict):
        return {"error": "요청 본문을 못 읽음"}
    settings = {key: value for key, value in body.items() if key not in _REQUEST_PAYLOAD_KEYS and key != "options"}
    settings.update(body.get("options") or {})
    return settings


def functions() -> dict[str, str]:
    """기능 설명. {recipe id: menu 의 function 문장}.

    규칙  게시 menu(paths.MENU_YAML_PATH) 원문 그대로. 결과를 읽는 쪽이 기능 번호 옆에 보일 글자
          menu 를 못 읽으면 빈 dict. 평가를 멈추지 않음
    제약  문장을 다듬거나 줄이지 않는다
    """
    import paths
    import yaml

    try:
        menu = yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {
        recipe_id: entry.get("function") or ""
        for recipe_id, entry in (menu.get("recipes") or {}).items()
        if isinstance(entry, dict)
    }


def _git_head() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def benchmark_meta(
    *,
    run_id: str,
    suite: dict,
    suite_path: Path,
    cases: list[dict],
    dataset: dict | None,
    runs: int,
    resolver: str,
    cooldown_every: int,
    cooldown_seconds: float,
    context: dict | None,
    context_label: str | None,
    materialize: bool,
    now: datetime.datetime,
    started: datetime.datetime,
) -> dict:
    """결과 meta 의 머리. 시작할 때 정해지는 칸 전부. 끝난 뒤의 칸(finished_at · stopped · environment)은 안 넣음.

    규칙  정답표 신원은 load_test_suite.identity. dataset 이 있으면 dataset_id · label 을 붙임
          conditions · functions · git HEAD 를 여기서 읽음
    """
    import paths

    return {
        "result_version": RESULT_VERSION,
        "run_id": run_id,
        "suite": {
            "path": str(suite_path),
            **load_test_suite.identity(suite, suite_path),
            "group_labels": list(load_test_suite.group_labels(suite)),
            "selected_case_ids": [case["id"] for case in cases],
            **({"dataset_id": dataset["id"], "label": dataset["label"]} if dataset else {}),
        },
        "runs": runs,
        "resolver": resolver,
        "role": check_resolve._role_label(),
        "conditions": conditions(),
        "functions": functions(),
        "cooldown": {"every": cooldown_every, "seconds": cooldown_seconds},
        "context": {"label": context_label, "payload": context},
        "materialize": materialize,
        "materialize_now": now.isoformat() if materialize else None,
        "artifact_root": str(paths.ARTIFACT_ROOT) if paths.ARTIFACT_ROOT else None,
        "git_head": _git_head(),
        "started_at": started.isoformat(),
    }
