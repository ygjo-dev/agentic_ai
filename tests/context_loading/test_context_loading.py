"""Static Workflow 의 Context(menu.yaml) 로딩 검증."""

from conftest import MENU_YAML_PATH, menu_was_read
from workflows.static.menu.load import load_menu


def test_load_static_context(read_file_paths):
    """Static Workflow 는 Context 로 실제 menu.yaml 원문을 사용해야 한다.
    LLM 은 여기서 호출하지 않는다. Context 로딩은 LLM 호출보다 먼저 일어난다.
    """
    read_file_paths.clear()

    menu = load_menu()

    assert menu_was_read(read_file_paths), (
        "load_menu() 가 실제 menu.yaml 을 읽지 않았다.\n"
        f"  기대한 파일 : {MENU_YAML_PATH}"
    )
    assert isinstance(menu, str)
    assert menu.strip() != ""
