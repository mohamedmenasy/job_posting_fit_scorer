import pathlib
import re

APP = pathlib.Path(__file__).parents[2] / "app"


def test_only_typesafe_evaluator_imports_sdk():
    hits = [p.relative_to(APP).as_posix() for p in APP.rglob("*.py")
            if re.search(r"^\s*(from|import) (typesafe_sdk|httpx2)", p.read_text(), re.M)]
    assert hits == ["semantic/typesafe_evaluator.py"]


def test_scoring_is_pure():
    for p in (APP / "scoring").rglob("*.py"):
        assert not re.search(r"^\s*(from|import) (app\.(db|models|repo|semantic|pipeline|api)|sqlalchemy|httpx|typesafe_sdk)",
                             p.read_text(), re.M), p
