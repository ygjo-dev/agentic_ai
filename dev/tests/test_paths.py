"""대상 : paths.py — 게시 자산을 어디서 읽나

게시 자산(온톨로지 · menu · recipe)은 KRRI_Ontology_Registry 짜임새의 한 뿌리에서 온다.
기본 뿌리는 이 저장소 안의 KRRI_Ontology_Registry 이고, AGENTIC_ARTIFACT_ROOT 에 적으면
같은 짜임새의 바깥 폴더다.

paths 는 import 할 때 한 번 정하므로 따로 띄운 python 으로 본다. 이 프로세스의 paths 를
다시 읽으면 뒤의 시험이 다른 자산을 읽게 된다.
"""

import json
import os
import subprocess
import sys

import paths

NAMES = ("ARTIFACT_ROOT", "ONTOLOGY_PATH", "MENU_YAML_PATH", "RECIPES_DIR")


def paths_in_child(root):
    """root 를 AGENTIC_ARTIFACT_ROOT 로 두고 띄운 python 이 본 경로. root 가 None 이면 값을 지움."""
    env = dict(os.environ)
    env.pop(paths.ARTIFACT_ROOT_ENV, None)
    if root is not None:
        env[paths.ARTIFACT_ROOT_ENV] = root
    code = f"import json, paths; print(json.dumps({{n: str(getattr(paths, n)) for n in {NAMES!r}}}))"
    return subprocess.run(
        [sys.executable, "-c", code], cwd=paths.REPO_ROOT, env=env, capture_output=True, text=True
    )


def test_without_an_artifact_root_the_registry_in_this_repository_is_read():
    """값을 안 적은 배포는 저장소 안의 KRRI_Ontology_Registry 를 읽는다."""
    done = paths_in_child(None)
    registry = paths.REPO_ROOT / "KRRI_Ontology_Registry"

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "ARTIFACT_ROOT": str(registry),
        "ONTOLOGY_PATH": str(registry / "ontology" / "ontology.yaml"),
        "MENU_YAML_PATH": str(registry / "menu" / "menu.yaml"),
        "RECIPES_DIR": str(registry / "recipes"),
    }


def test_an_artifact_root_moves_the_ontology_the_menu_and_the_recipes_together(tmp_path):
    """셋이 한 뿌리에서 와야 함. 하나만 옮겨지면 menu 에 없는 recipe 를 고르거나 온톨로지에 없는 노드를 실행함."""
    root = tmp_path.resolve()

    done = paths_in_child(str(root))

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "ARTIFACT_ROOT": str(root),
        "ONTOLOGY_PATH": str(root / "ontology" / "ontology.yaml"),
        "MENU_YAML_PATH": str(root / "menu" / "menu.yaml"),
        "RECIPES_DIR": str(root / "recipes"),
    }


def test_an_artifact_root_that_is_not_a_folder_stops_instead_of_falling_back(tmp_path):
    """틀린 값에 저장소 안 Registry 로 돌아가면 어느 자산으로 해석했는지 아무도 모름."""
    done = paths_in_child(str(tmp_path / "없는_폴더"))

    assert done.returncode != 0
    assert "ArtifactRootError" in done.stderr


def test_there_is_no_second_menu_document():
    """menu 는 menu.yaml 하나다. 사람이 읽을 사본을 따로 두면 둘이 어긋난다."""
    assert not hasattr(paths, "MENU_MD_PATH")
    assert not (paths.MENU_DIR / "menu.md").exists()
