import sys
import typing as t
from pathlib import Path
from subprocess import STDOUT
from subprocess import CalledProcessError
from subprocess import check_output
from textwrap import dedent

TEST_DIR = Path(__file__).parent
TARGETS_DIR = TEST_DIR / "targets"


def dfly(cmd: t.List[str], script: t.List[str]) -> str:
    try:
        return check_output(
            ("dfly", *cmd),
            input="\n".join(script).encode("utf-8"),
            timeout=10,
            stderr=STDOUT,
        ).decode("utf-8")
    except CalledProcessError as e:
        print(e.output.decode("utf-8"))
        raise


def run_dfly_script(args: t.List[str], script: t.List[str], expected_output: str) -> None:
    out = dfly([sys.executable, *args], script)
    exp = dedent(expected_output).strip()
    assert out.strip() == exp, f"Expected:\n{exp}\nGot:\n{out}"
