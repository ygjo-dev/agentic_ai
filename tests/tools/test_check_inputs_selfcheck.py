"""check_inputs 의 자체 검사가 커밋마다 돈다.

재는 도구가 조용히 죽은 것이 두 번이다 — check_argument 나흘(「스물다섯째」),
check_inputs 하루(「쉰째」). 둘 다 배선표(step_service)가 바뀔 때 도구가 못
따라간 것이고, 표는 커밋마다 바뀌는데 도구는 어쩌다 한 번 돈다. 커밋마다
도는 것은 pytest 라 그 자리에 _selfcheck 호출 하나를 둔다.

_selfcheck 자체가 「TOOL_OF · STEP_OF 의 모든 줄을 빈 스키마로 한 바퀴 읽는」
검사를 품고 있어(「쉰아홉째」), 이 한 줄이 곧 전 줄 읽기다. 서버도 Gateway 도
tools.json 도 안 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import check_inputs  # noqa: E402


def test_배선표가_바뀌어도_계기판이_읽을_수_있다():
    """스텁이 아니라 진짜 표를 읽음. 표의 모양이 바뀌면 여기서 빨간불이 남."""
    check_inputs._selfcheck()
