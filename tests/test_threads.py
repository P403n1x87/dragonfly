import sys

from tests.utils import TARGETS_DIR
from tests.utils import run_dfly_script


def test_threads_lock():
    target = str((TARGETS_DIR / "threads.py").resolve())
    fn = " (target)" if sys.version_info >= (3, 10) else ""
    run_dfly_script(
        ["-m", "tests.targets.threads"],
        [
            "b tests/targets/threads.py:5",
            "b tests/targets/threads.py:11",
            "r",
            "co",
            "co",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, line 5
        ᖭི༏ Breakpoint request at {target}, line 11
        ᖭི༏ Breakpoint #1 set at {target}, line 5
        Breakpoint #2 set at {target}, line 11
        Breakpoint #2 hit at {target}, line 11, in thread MainThread
        File {target}, line 11, in main
        >>>     threads = []
        ᖭི༏ Breakpoint #1 hit at {target}, line 5, in thread Thread-1{fn}
        File {target}, line 5, in target
        >>>     a = []
        ᖭི༏ Breakpoint #1 hit at {target}, line 5, in thread Thread-2{fn}
        File {target}, line 5, in target
        >>>     a = []
        ᖭི༏
        """,
    )
