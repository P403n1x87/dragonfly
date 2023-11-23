from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from types import CodeType


@dataclass(frozen=True)
class Breakpoint:
    """Abstract debugger breakpoint."""


@dataclass(frozen=True)
class LineBreakpoint(Breakpoint):
    """Line breakpoint."""

    source: Path
    line: int

    def __str__(self) -> str:
        return f"{self.source}:{self.line}" if self.line > 0 else str(self.source)


@dataclass(frozen=True)
class FunctionBreakpoint(Breakpoint):
    """Function breakpoint."""

    module: str
    function: str

    def __str__(self) -> str:
        return f"{self.module}:{self.function}"


@dataclass
class BreakpointCondition:
    """Breakpoint condition."""

    expr: str
    code: CodeType = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.code = compile(self.expr, "<breakpoint-condition>", "eval")

    def __call__(self, _locals):
        return bool(eval(self.code, globals(), _locals))  # noqa
