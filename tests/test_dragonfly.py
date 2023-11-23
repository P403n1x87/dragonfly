from tests.utils import TARGETS_DIR
from tests.utils import run_dfly_script


def test_run_module_breakpoints():
    target = str((TARGETS_DIR / "target.py").resolve())
    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py",
            "r",
            "b tests/targets/target.py:2",
            "co",
            "n;;n;;n;;n",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, on entry
        ᖭི༏ Breakpoint #1 set at {target}, line 1
        Breakpoint #1 hit at {target}, line 1, in thread MainThread
        File {target}, line 1, in <module>
        >>> def bar():
        ᖭི༏ Breakpoint request at {target}, line 2
        Breakpoint #2 set at {target}, line 2
        ᖭི༏ Breakpoint #2 hit at {target}, line 2, in thread MainThread
        File {target}, line 2, in bar
        >>>     a = 42
        hello world
        ᖭི༏ File {target}, line 3, in bar
        >>>     print(a)
        File {target}, line 4, in bar
        >>>     return a << 2
        @return = 168
        File {target}, line 4, in bar
        >>>     return a << 2
        File {target}, line 10, in foo
        >>>     print("hello gab")
        42
        ᖭི༏ hello gab
        """,
    )


def test_run_module_breakpoints_in_running_frame():
    target = str((TARGETS_DIR / "target.py").resolve())
    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py:2",
            "r",
            "b tests/targets/target.py:3",
            "co;;co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, line 2
        ᖭི༏ Breakpoint #1 set at {target}, line 2
        Breakpoint #1 hit at {target}, line 2, in thread MainThread
        File {target}, line 2, in bar
        >>>     a = 42
        hello world
        ᖭི༏ Breakpoint request at {target}, line 3
        Breakpoint #2 set at {target}, line 3
        ᖭི༏ Breakpoint #2 hit at {target}, line 3, in thread MainThread
        File {target}, line 3, in bar
        >>>     print(a)
        42
        hello gab
        """,
    )


def test_run_module_breakpoints_in_imported_module():
    target = str((TARGETS_DIR / "target.py").resolve())
    run_dfly_script(
        ["-m", "tests.targets.importer"],
        [
            "b tests/targets/target.py:2",
            "r",
            "b tests/targets/target.py:3",
            "co;;co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, line 2
        ᖭི༏ Breakpoint #1 set at {target}, line 2
        Breakpoint #1 hit at {target}, line 2, in thread MainThread
        File {target}, line 2, in bar
        >>>     a = 42
        calling imported bar
        ᖭི༏ Breakpoint request at {target}, line 3
        Breakpoint #2 set at {target}, line 3
        ᖭི༏ Breakpoint #2 hit at {target}, line 3, in thread MainThread
        File {target}, line 3, in bar
        >>>     print(a)
        42
        called imported bar
        """,
    )


def test_run_module_breakpoints_in_imported_module_on_entry():
    target = str((TARGETS_DIR / "target.py").resolve())
    run_dfly_script(
        ["-m", "tests.targets.importer"],
        [
            "b tests/targets/target.py",
            "r",
            "b tests/targets/target.py:3",
            "co;;co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, on entry
        ᖭི༏ Breakpoint #1 set at {target}, line 1
        Breakpoint #1 hit at {target}, line 1, in thread MainThread
        File {target}, line 1, in <module>
        >>> def bar():
        ᖭི༏ Breakpoint request at {target}, line 3
        ᖭི༏ Breakpoint #2 set at {target}, line 3
        Breakpoint #2 hit at {target}, line 3, in thread MainThread
        File {target}, line 3, in bar
        >>>     print(a)
        calling imported bar
        42
        called imported bar
        """,
    )


def test_clear_breakpoints():
    target = str((TARGETS_DIR / "target.py").resolve())
    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py",
            "r",
            "b tests/targets/target.py:2",
            "cl",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, on entry
        ᖭི༏ Breakpoint #1 set at {target}, line 1
        Breakpoint #1 hit at {target}, line 1, in thread MainThread
        File {target}, line 1, in <module>
        >>> def bar():
        ᖭི༏ Breakpoint request at {target}, line 2
        Breakpoint #2 set at {target}, line 2
        ᖭི༏ Breakpoint #1 cleared at {target}, on entry
        Breakpoint #2 cleared at {target}, line 2
        ᖭི༏ hello world
        42
        hello gab
        """,
    )


def test_clear_breakpoint():
    target = str((TARGETS_DIR / "target.py").resolve())
    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py",
            "r",
            "b tests/targets/target.py:2",
            "cl 2",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, on entry
        ᖭི༏ Breakpoint #1 set at {target}, line 1
        Breakpoint #1 hit at {target}, line 1, in thread MainThread
        File {target}, line 1, in <module>
        >>> def bar():
        ᖭི༏ Breakpoint request at {target}, line 2
        Breakpoint #2 set at {target}, line 2
        ᖭི༏ Breakpoint #2 cleared at {target}, line 2
        ᖭི༏ hello world
        42
        hello gab
        """,
    )


def test_breakpoint_condition():
    target = str((TARGETS_DIR / "target.py").resolve())

    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py:3 'a == 42'",
            "b tests/targets/target.py:4 'a != 42'",
            "r",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, line 3
        ᖭི༏ Breakpoint request at {target}, line 4
        ᖭི༏ Breakpoint #1 set at {target}, line 3
        Breakpoint #2 set at {target}, line 4
        Breakpoint #1 hit at {target}, line 3, in thread MainThread
        File {target}, line 3, in bar
        >>>     print(a)
        hello world
        ᖭི༏ 42
        hello gab
        """,
    )

    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py:3 'a != 42'",
            "b tests/targets/target.py:4 'a == 42'",
            "r",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, line 3
        ᖭི༏ Breakpoint request at {target}, line 4
        ᖭི༏ Breakpoint #1 set at {target}, line 3
        Breakpoint #2 set at {target}, line 4
        Breakpoint #2 hit at {target}, line 4, in thread MainThread
        File {target}, line 4, in bar
        >>>     return a << 2
        hello world
        42
        ᖭི༏ hello gab
        """,
    )


def test_breakpoint_condition_update():
    target = str((TARGETS_DIR / "target.py").resolve())

    run_dfly_script(
        ["-m", "tests.targets.target"],
        [
            "b tests/targets/target.py:3 'a == 42'",
            "b tests/targets/target.py:3 'a != 42'",
            "b tests/targets/target.py:3",
            "r",
            "co",
        ],
        f"""\
        ᖭི༏ Breakpoint request at {target}, line 3
        ᖭི༏ Breakpoint #1 condition updated
        ᖭི༏ Breakpoint #1 condition removed
        ᖭི༏ Breakpoint #1 set at {target}, line 3
        Breakpoint #1 hit at {target}, line 3, in thread MainThread
        File {target}, line 3, in bar
        >>>     print(a)
        hello world
        ᖭི༏ 42
        hello gab
        """,
    )
