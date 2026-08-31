"""wiring.yaml 을 판 것이 배선표가 되는가.

**1-a 의 증거는 대보는 것이었다.** 배선을 코드에서 데이터로 뺐는데, 뺀 것이
같은 것인지는 줄 수로는 알 수 없어 코드에 표를 한 벌 남겨 두고 dict 를 통째로
맞댔다 — 키도 값도 차례도 같았다. 1-b 에서 코드 표를 지우면서 그 시험 셋도
함께 지웠다. 대볼 것이 없어졌다. 남은 아홉은 로더가 지켜야 할 것을 잰다.

판정(check_resolve)은 안 잰다. 배선은 프롬프트에 안 실리고 이번 변경은 같은
dict 를 다른 데서 만들 뿐이다. dict 가 같다는 것이 판정을 재는 것보다 강한
증거이고, 판정을 재면 LLM 잡음만 얹는다.

**「계기판이 조용히 죽는다」가 세 번 났다.** 그래서 같은지만 보지 않고, 파일이
없거나 깨졌을 때 빈 표로 도는 대신 터지는지도 본다. 계기판 넷이
TOOL_OF · STEP_OF 를 import 해서 곧장 읽으므로 빈 표는 「배선 0줄」이라는
멀쩡해 보이는 출력이 된다.

서버도 LLM 도 안 부른다. wiring.yaml 만 읽는다.
"""

import pytest

import paths
from demo.api.services import step_service


@pytest.fixture(autouse=True)
def restore_tables():
    """가짜 파일을 물린 시험이 진짜 표를 두고 가지 않게.

    표는 모듈 하나에 하나뿐이고 계기판 넷이 그것을 import 해 쥔다. 갈아
    끼우지 않고 비웠다 채우는 방식이라 시험이 얹은 것도 그대로 남는다 —
    monkeypatch 가 되돌리는 것은 paths.WIRING_PATH 뿐이다.
    """
    tool_of = dict(step_service.TOOL_OF)
    step_of = dict(step_service.STEP_OF)
    mtime = step_service._wiring_mtime
    yield
    step_service.TOOL_OF.clear()
    step_service.TOOL_OF.update(tool_of)
    step_service.STEP_OF.clear()
    step_service.STEP_OF.update(step_of)
    step_service._wiring_mtime = mtime


def test_arg_field_is_a_pair_not_a_list():
    """arg_field 는 짝이다.

    YAML 은 목록으로만 적을 수 있어 로더가 튜플로 바꾼다. 목록으로 남으면
    _by_argument 는 그대로 돌지만 짝으로 푸는 자리가 조용히 어긋난다.
    """
    wiring = step_service.STEP_OF[("get_railway_lines", "place_name")]
    assert wiring["arg_field"] == (step_service.RAILWAY_LINE_SUFFIX, "railwayName")
    assert isinstance(wiring["arg_field"], tuple)


def test_names_in_yaml_become_values_from_code():
    """<이름> 이 코드의 값으로 바뀐다.

    값의 원천은 코드에 남겼다. RADIUS_METERS 는 demo/ui/config.py 도 쓰고
    POINT_RADIUS_TO_BBOX 는 vendor 어댑터의 이름이라 YAML 에 값을 옮기면
    원천이 둘이 된다.
    """
    wiring = step_service.STEP_OF[("search_ev_stations", "map_extent")]
    assert wiring["input"]["radiusMeters"] == step_service.RADIUS_METERS
    assert wiring["adapter"] == step_service.POINT_RADIUS_TO_BBOX


def test_unknown_name_raises(tmp_path, monkeypatch):
    """모르는 이름은 조용히 안 넘어간다.

    그대로 두면 "<RADIUS_METRES>" 라는 문자열이 도구에 실려 나가고, 0건이
    오지 오류가 오지 않는다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(
        "tool_of: {}\n"
        "step_of:\n"
        "  find_cctv:\n"
        "    point:\n"
        '      input: {radiusMeters: "<RADIUS_METRES>"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(ValueError, match="RADIUS_METRES"):
        step_service._load_wiring()


def test_unknown_wiring_field_raises(tmp_path, monkeypatch):
    """모르는 칸 이름도 터진다.

    input_frist 같은 오타가 넘어가면 화면 문맥에서 시작하는 자리가 소리 없이
    사라진다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(
        "tool_of: {}\n"
        "step_of:\n"
        "  find_cctv:\n"
        "    point:\n"
        "      input: {lon: 1}\n"
        "      input_frist: {lon: 2}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(ValueError, match="input_frist"):
        step_service._load_wiring()


def test_missing_file_raises(tmp_path, monkeypatch):
    """파일이 없으면 빈 표로 돌지 않고 터진다."""
    monkeypatch.setattr(paths, "WIRING_PATH", tmp_path / "없다.yaml")

    with pytest.raises(FileNotFoundError):
        step_service._load_wiring()


def test_broken_yaml_raises(tmp_path, monkeypatch):
    """문법이 깨져도 터진다."""
    path = tmp_path / "wiring.yaml"
    path.write_text("tool_of: {\n  깨진다\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(Exception):
        step_service._load_wiring()


def test_unknown_section_raises(tmp_path, monkeypatch):
    """모르는 절도 터진다. 오타 난 절은 조용히 빈 표가 된다."""
    path = tmp_path / "wiring.yaml"
    path.write_text("tool_of: {}\nstep_of: {}\ntool_off: {}\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(ValueError, match="tool_off"):
        step_service._load_wiring()


def test_a_broken_file_does_not_empty_the_tables(tmp_path, monkeypatch):
    """터져도 반만 바뀐 표가 남지 않는다.

    두 표를 다 만든 뒤에 갈아 넣는다. 빈 표보다 반쪽 표가 나쁘다 — 계기판이
    「배선 3줄」처럼 멀쩡한 모양으로 틀린 수를 찍는다.
    """
    before_tool = dict(step_service.TOOL_OF)
    before_step = dict(step_service.STEP_OF)

    path = tmp_path / "wiring.yaml"
    path.write_text("tool_of: {}\nstep_of: {깨진다\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(Exception):
        step_service._load_wiring()

    assert step_service.TOOL_OF == before_tool
    assert step_service.STEP_OF == before_step


def test_reload_reads_again_when_mtime_changes(tmp_path, monkeypatch):
    """mtime 이 바뀌면 다시 읽는다. 안 바뀌면 안 읽는다.

    등록 화면이 wiring.yaml 을 쓰면 서버를 안 내리고 반영되어야 한다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(
        "tool_of:\n"
        "  n:\n"
        "    server_id: s\n"
        "    tool: t\n"
        "    headline: 하나\n"
        "step_of:\n"
        "  n:\n"
        "    k:\n"
        "      input: {query: '@arg'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WIRING_PATH", path)
    monkeypatch.setattr(step_service, "_wiring_mtime", None)

    step_service.reload_wiring()
    assert step_service.TOOL_OF["n"]["headline"] == "하나"

    # 파일을 안 건드리면 다시 안 판다. 손으로 얹은 줄이 살아 있으면 안 판 것이다.
    step_service.TOOL_OF["표시"] = "안 판다"
    step_service.reload_wiring()
    assert "표시" in step_service.TOOL_OF

    stat = path.stat()
    path.write_text(
        "tool_of:\n"
        "  n:\n"
        "    server_id: s\n"
        "    tool: t\n"
        "    headline: 둘\n"
        "step_of:\n"
        "  n:\n"
        "    k:\n"
        "      input: {query: '@arg'}\n",
        encoding="utf-8",
    )
    if path.stat().st_mtime_ns == stat.st_mtime_ns:  # 시계가 굵은 파일시스템
        import os

        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    step_service.reload_wiring()
    assert step_service.TOOL_OF["n"]["headline"] == "둘"
    assert "표시" not in step_service.TOOL_OF
