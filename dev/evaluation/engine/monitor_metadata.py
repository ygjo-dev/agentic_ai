"""벤치마크를 어떻게 쟀나를 적는 곳. 재현에 필요한 실행 조건 · 파일 신원 · git HEAD.

    conditions()    모델 · provider · 역할 판 · 요청 설정 · prompt · 응답 schema · menu 파일과 sha256 · 게시 자산 sha256
    functions()     기능 설명 {recipe id: menu 의 function 문장}. 화면이 기능 번호 옆에 보임
    role_label()    resolve 역할 한 줄 (계기판 check_resolve 도 이것을 씀)
    benchmark_meta  위 셋과 정답표 신원 · 문맥 · 팬 소음 억제를 모은 결과 meta 머리
    resume_identity 이어 실행할 때 같아야 하는 조건 (저장된 머리 · 지금 이 저장소)

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

KST = zoneinfo.ZoneInfo("Asia/Seoul")

# 결과 JSON 의 판. 칸의 뜻을 바꾸면 올린다.
# 3: 줄에 scope · recipe_group · outcome · oos_correct · timing.started_at, summary 에 metrics ·
#    latency · recipes, meta 에 run_id · elapsed_s · suite.name · suite.group_labels
#    뒤에 판을 안 올리고 더한 선택 칸: expected.reads · conditions.request · meta.environment ·
#    conditions.registry · meta.stopped_at · meta.resumed_at · meta.fan_quiet_mode · meta.fan_wait_s ·
#    meta.resumed_fan_quiet_mode.
#    이 칸이 없는 옛 결과도 그대로 읽힌다(이어 실행만 막힘). 옛 결과의 meta.gpu(온도 기록) · meta.cooldown(고정 쉼)은
#    더 쓰지 않는다
RESULT_VERSION = 3


def describe_role(role) -> str:
    """역할 설정 한 벌을 한 줄로. 결과 meta.role 과 계기판 표 머리가 같은 글자로 적게 한 곳에 둠."""
    return (
        f"역할 {role.role} v{role.version} · {role.model} ({role.provider}) · "
        f"prompt v{role.prompt_version} · response_schema v{role.response_schema_version}"
    )


def role_label() -> str:
    """resolve 역할 한 줄. 결과 meta.role 에 적힘.

    규칙  이 저장소의 역할 manifest 를 읽음. 창구가 같은 사본에서 떠 있을 때
          창구가 쓰는 판과 같음. /resolve 응답에는 판이 안 실림
          못 읽으면 그 까닭을 적고 재기는 멈추지 않음. 재는 것은 창구임
          부를 때 import 함. 정답표만 빌려 쓰는 자가 역할 설정까지 끌어오지 않게 하려는 것
    """
    from llm_engine.role_config import RESOLVE, get_role_config

    try:
        return describe_role(get_role_config(RESOLVE))
    except ValueError as error:
        return f"역할 {RESOLVE} 못 읽음 ({error})"


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


def _tree_record(folder: Path) -> dict:
    """실행 조건에 적을 폴더 하나. {path, sha256}. sha256 은 안의 파일 전부(상대 경로 · 바이트)를 이름 차례로 이은 것.

    규칙  경로 표기는 _file_record 와 같음. 폴더가 없으면 sha256 은 None
    """
    folder = Path(folder)
    record = _file_record(folder)
    if not folder.is_dir():
        return record
    digest = hashlib.sha256()
    for path in sorted(item for item in folder.rglob("*") if item.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {**record, "sha256": digest.hexdigest()}


def conditions() -> dict:
    """이번 평가를 잰 조건. 모델 · prompt · 응답 schema · menu 파일과 그 sha256.

    출력  {model, provider, role_version, inference, request, prompt, response_schema, menu, registry}. 파일 셋은 _file_record 꼴
          request 는 provider 가 요청마다 싣는 고정 설정(temperature · seed · …). request_settings 가 셈
          registry 는 게시 자산 뿌리(ontology · menu · recipes) 전체의 sha256 (_tree_record).
          정답표 reads · 범위 밖 결과(materialize 판정)가 recipe 의 execution 을 읽으므로 적음
          역할 설정을 못 읽으면 {error} 하나
    규칙  이 저장소의 역할 manifest 와 게시 menu 를 읽음. 창구가 같은 사본에서 떠 있을 때
          창구가 쓰는 판과 같음. /resolve 응답에는 판이 안 실림 (role_label 과 같음)
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
        "registry": _tree_record(paths.ARTIFACT_ROOT),
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
    fan_quiet_mode: bool,
    context: dict | None,
    context_label: str | None,
    materialize: bool,
    now: datetime.datetime,
    started: datetime.datetime,
) -> dict:
    """결과 meta 의 머리. 시작할 때 정해지는 칸 전부. 끝난 뒤의 칸(finished_at · stopped · environment)은 안 넣음.

    규칙  정답표 신원은 load_test_suite.identity. dataset 이 있으면 dataset_id · label 을 붙임
          conditions · functions · git HEAD 를 여기서 읽음
          fan_quiet_mode 는 첫 실행 구간에서 GPU 팬 소음 억제를 켰나(참 · 거짓). 이어 실행 구간의 값은
          run_evaluation.resume 이 resumed_fan_quiet_mode 에 따로 적음. 이어 실행 조건이 아님
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
        "role": role_label(),
        "conditions": conditions(),
        "functions": functions(),
        "fan_quiet_mode": bool(fan_quiet_mode),
        "context": {"label": context_label, "payload": context},
        "materialize": materialize,
        "materialize_now": now.isoformat() if materialize else None,
        "artifact_root": str(paths.ARTIFACT_ROOT) if paths.ARTIFACT_ROOT else None,
        "git_head": _git_head(),
        "started_at": started.isoformat(),
    }


# ================================================================ 이어 실행
# 이어 실행할 때 같아야 하는 조건. (화면 글자, 저장된 meta 에서 값을 꺼내는 경로).
# 「남은 발화를 같은 평가 계약으로 재나」만 본다. run_id · 시각 · git HEAD · 저장 자리 · GPU · 팬 소음 억제 ·
# 화면 정렬 · 필터는 안 본다 — 재는 값을 안 바꾸거나 저장된 값을 그대로 다시 쓴다.
# 팬 소음 억제는 실행 박자일 뿐이라 이어 실행 구간마다 그때 값을 쓴다 (RESUME_REPLAYED 에도 없음).
RESUME_FIELDS = (
    ("Test Suite", (("suite", "dataset_id"), ("suite", "sha256"))),
    ("Model", (("conditions", "model"), ("conditions", "provider"), ("conditions", "role_version"),
               ("conditions", "inference"))),
    ("Prompt", (("conditions", "prompt", "sha256"),)),
    ("Schema", (("conditions", "response_schema", "sha256"),)),
    ("Menu", (("conditions", "menu", "sha256"),)),
    ("Registry", (("conditions", "registry", "sha256"),)),
    ("Request settings", (("conditions", "request"),)),
    ("Evaluation version", (("result_version",),)),
)

# 이어 실행이 저장된 값을 그대로 다시 쓰는 칸. 지금 값과 맞대지 않지만 없으면 같은 실행을 못 만든다.
RESUME_REPLAYED = (
    ("suite", "selected_case_ids"),
    ("runs",),
    ("resolver",),
    ("materialize",),
    ("context", "label"),
    ("context", "payload"),
)

_MISSING = object()


def _dig(meta: dict, path: tuple):
    value = meta
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
    return value


def resume_identity(meta: dict) -> dict:
    """저장된 머리의 이어 실행 조건. {화면 글자: 값}. 값을 못 찾은 칸은 None.

    규칙  RESUME_FIELDS 차례. 칸 하나에 경로가 여럿이면 [값, …] 목록
          경로 중 하나라도 없거나 null 이거나 {error} 면 그 칸은 None (기록 없음)
    """
    shown = {}
    for label, routes in RESUME_FIELDS:
        values = [_dig(meta, route) for route in routes]
        broken = any(v is _MISSING or v is None or (isinstance(v, dict) and "error" in v) for v in values)
        shown[label] = None if broken else (values[0] if len(values) == 1 else values)
    return shown


def resume_gaps(meta: dict) -> list[str]:
    """이어 실행에 필요한데 저장된 머리에 없는 칸 이름들. 비면 다 있음.

    규칙  RESUME_FIELDS 가 None 인 칸 · RESUME_REPLAYED 경로가 없는 칸
          materialize 가 참이면 materialize_now 도 있어야 함 (부르는 순간을 같게 하려고)
          조건을 못 읽은 기록(conditions.error)도 여기 걸림
    """
    gaps = [label for label, value in resume_identity(meta).items() if value is None]
    gaps += [".".join(route) for route in RESUME_REPLAYED if _dig(meta, route) is _MISSING]
    if meta.get("materialize") and not meta.get("materialize_now"):
        gaps.append("materialize_now")
    return gaps


def current_resume_identity(meta: dict) -> dict:
    """지금 이 저장소에서 같은 기록을 이어 잴 때의 조건. resume_identity 와 같은 모양.

    규칙  정답표는 저장된 dataset_id 의 등록 파일, 없으면 저장된 suite.path 를 지금 읽어 sha256 을 셈
          모델 · prompt · schema · menu · 게시 자산 · 요청 설정은 conditions() 를 지금 읽음
          평가 판은 RESULT_VERSION
    제약  저장된 값을 여기서 고치지 않는다
    """
    suite = meta.get("suite") or {}
    path = None
    try:
        path = load_test_suite.dataset(suite.get("dataset_id"))["path"]
    except KeyError:
        path = suite.get("path")
    sha = None
    if path and Path(path).is_file():
        sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    now = {"result_version": RESULT_VERSION, "suite": {"dataset_id": suite.get("dataset_id"), "sha256": sha},
           "conditions": conditions()}
    return resume_identity(now)


def compare_resume(stored: dict, current: dict) -> list[dict]:
    """이어 실행 조건 맞대기. [{label, stored, current, same}] RESUME_FIELDS 차례.

    규칙  같은지는 값 전체로 봄 (sha256 전체 · 요청 설정 dict 전체). 한쪽이 None 이면 다름
    """
    return [
        {"label": label, "stored": stored.get(label), "current": current.get(label),
         "same": stored.get(label) is not None and stored.get(label) == current.get(label)}
        for label, _routes in RESUME_FIELDS
    ]
