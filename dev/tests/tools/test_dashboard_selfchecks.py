"""대상 : dev/tools/ — 계기판의 자체 검사가 커밋마다 돈다

**재는 도구가 조용히 죽은 것이 세 번이다.** check_argument 나흘
(「스물다섯째」) · check_inputs 하루(「쉰째」→「쉰아홉째」에서 살림) ·
check_resolve (「예순셋째」). 앞의 둘은 배선표가 바뀔 때 도구가 못 따라간
것이고, 셋째는 발화가 늘어(화면 다섯) 묶음이 셋이 됐는데 묶음 이름을 고르는
자리가 두 갈래에 머문 것이다. 셋 다 「판정은 다 해 놓고 표를 찍는 마지막에
죽는다」가 같다.

배선표도 발화 목록도 커밋마다 바뀌는데 계기판은 어쩌다 한 번, 그것도 서버를
띄워야 돈다. 커밋마다 도는 것은 pytest 라 그 자리에 `_selfcheck` 호출을 둔다.

서버 · Gateway · tools.json · 온톨로지를 안 부른다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import check_inputs  # noqa: E402
import check_resolve  # noqa: E402


def test_the_inputs_dashboard_can_read_the_wiring_table_even_when_it_changes():
    """스텁이 아니라 진짜 표를 읽음. 표의 모양이 바뀌면 여기서 빨간불이 남.

    `_selfcheck` 가 「TOOL_OF · STEP_OF 의 모든 줄을 빈 스키마로 한 바퀴
    읽는」 검사를 품고 있어(「쉰아홉째」) 이 한 줄이 곧 전 줄 읽기다.
    """
    check_inputs._selfcheck()


def test_the_resolve_dashboard_prints_to_the_end_however_the_groups_are_split():
    """스텁이 아니라 진짜 UTTERANCES 를 씀. 묶음 경계가 바뀌면 여기서 빨간불."""
    check_resolve._selfcheck()


def test_the_group_label_chooser_does_not_miss_the_screen_utterances():
    """「예순셋째」의 음성 대조군. 두 갈래로 되돌리면 자체 검사가 죽어야 한다.

    이것이 없으면 `_selfcheck` 가 통과해도 그것이 「이 버그를 잡아서」인지
    「아무것도 안 봐서」인지 못 가른다.
    """
    was = check_resolve._group_label
    try:
        check_resolve._group_label = (
            lambda n: check_resolve.BASELINE_LABEL
            if n <= check_resolve.BASELINE_LAST
            else check_resolve.EXTENSION_LABEL
        )
        try:
            check_resolve._selfcheck()
        except (AssertionError, KeyError):
            pass
        else:
            raise AssertionError("두 갈래로 되돌렸는데 자체 검사가 안 죽었다")
    finally:
        check_resolve._group_label = was
