import os
import shlex
import typing as t
from abc import ABC
from functools import singledispatchmethod
from inspect import signature
from pathlib import Path
from traceback import print_stack
from types import FrameType

import dragonfly._notify as notify
from dragonfly._breakpoint.model import Breakpoint
from dragonfly._breakpoint.model import BreakpointCondition
from dragonfly._breakpoint.model import FunctionBreakpoint
from dragonfly._breakpoint.model import LineBreakpoint
from dragonfly._interface import DebuggerInterface
from dragonfly._tracing import DebuggerTracingMixin

try:
    import readline  # noqa
except ImportError:
    # The readline module is not available on Windows.
    pass


class DebuggerCommandError(Exception):
    pass


class DebuggerCommand(ABC):
    __slots__: t.List[str] = []

    __action__: str
    __require_started__: bool = False
    __require_tracing__: bool = False
    __require_frame__: bool = False
    __resume_after__: bool = False


# ---- Debugger Commands ----


class RunCommand(DebuggerCommand):
    """Start the debugger and run the target program."""

    __resume_after__ = True


class BreakpointCommand(DebuggerCommand):
    """Set a breakpoint at the given location.

    The location can be a file path and line number, e.g.

        /path/to/file.py:42

    or a module name and function name, e.g.

        module.submodule:SomeClass.func

    If no location is given, list all breakpoints.
    """

    __slots__ = ["breakpoint", "condition"]
    breakpoint: t.Optional[Breakpoint]  # noqa
    condition: t.Optional[BreakpointCondition]

    def __init__(self, loc: t.Optional[str] = None, cond_expr: t.Optional[str] = None) -> None:
        if loc is None:
            self.breakpoint = None
            return

        head, _, tail = loc.partition(":")
        if Path(head).exists():
            # Line breakpoint
            path = Path(head).resolve()
            try:
                self.breakpoint = LineBreakpoint(path, int(tail) if tail else -1)
            except ValueError as e:
                msg = f"invalid line number: {tail}"
                raise DebuggerCommandError(msg) from e
        else:
            self.breakpoint = FunctionBreakpoint(head, tail)

        self.condition = BreakpointCondition(cond_expr) if cond_expr is not None else None


class ClearCommand(DebuggerCommand):
    """Clear the given breakpoint."""

    __slots__ = ["number"]

    number: t.Optional[int]

    def __init__(self, number: t.Optional[str] = None) -> None:
        self.number = int(number) if number is not None else None
        if self.number is not None and self.number <= 0:
            msg = "invalid breakpoint number"
            raise DebuggerCommandError(msg)


class StepCommand(DebuggerCommand):
    """Step into the next instruction.

    If the next instruction is a function call, step into the function.

    If the trace-opcodes setting is enabled, step into the next opcode instead.
    """

    __require_started__ = True
    __require_tracing__ = True
    __require_frame__ = True


class NextCommand(DebuggerCommand):
    """Step over the next instruction.

    If the next instruction is a function call, step over the function.

    If the trace-opcodes setting is enabled, step over the next opcode instead.
    """

    __require_started__ = True
    __require_tracing__ = True
    __require_frame__ = True


class LineCommand(DebuggerCommand):
    """List the source code around the current line."""

    __require_started__ = True
    __require_frame__ = True


class DisassembleCommand(DebuggerCommand):
    """List the bytecode instructions around the current line."""

    __require_started__ = True
    __require_frame__ = True


class EvaluateCommand(DebuggerCommand):
    """Evaluate the given expression in the current frame."""

    __require_started__ = True
    __require_frame__ = True

    def __init__(self, *expr: str) -> None:
        self.expr = " ".join(expr)
        try:
            self._compiled = compile(self.expr, "expression", "eval")
        except Exception as e:
            msg = f"in expression '{self.expr}': {e}"
            raise DebuggerCommandError(msg) from e

    def __call__(self, frame: FrameType) -> str:
        return str(eval(self._compiled, frame.f_globals, frame.f_locals))  # noqa


class QuitCommand(DebuggerCommand):
    """Quit the debugger."""

    pass


class ContinueCommand(DebuggerCommand):
    """Continue execution until the next breakpoint."""

    __require_started__ = True
    __resume_after__ = True


class TracebackCommand(DebuggerCommand):
    """Print the current stack trace."""

    __require_started__ = True
    __require_frame__ = True


class SetCommand(DebuggerCommand):
    """Set the given setting to the given value."""

    __slots__ = ["setting", "value"]
    setting: str
    value: str

    def __init__(self, setting: str, value: str) -> None:
        self.setting = setting
        self.value = value


class HelpCommand(DebuggerCommand):
    """Show help for the given topic.

    If no topic is given, list all commands and topics.
    """

    __slots__ = ["topic"]

    def __init__(self, topic: t.Optional[str] = None) -> None:
        self.topic = topic


class DebuggerCommandHandlerMixin(DebuggerTracingMixin, DebuggerInterface):
    @singledispatchmethod
    def handle(self, _cmd: DebuggerCommand, _frame: t.Optional[FrameType]) -> None:
        raise NotImplementedError()

    @handle.register
    def _(self, cmd: RunCommand, _frame: t.Optional[FrameType]) -> None:
        cmd.__resume_after__ = not self.started
        self.start()

    @handle.register
    def _(self, cmd: BreakpointCommand, frame: t.Optional[FrameType]) -> None:
        if cmd.breakpoint is not None:
            self.set_breakpoint(cmd.breakpoint, cmd.condition, frame)
            return

        if not (entries := self.registry.entries):
            notify.dfly("no breakpoints set")
            return

        for e in entries:
            notify.p(f"#{e.number}: {e.breakpoint}")

    @handle.register
    def _(self, cmd: ClearCommand, _frame: t.Optional[FrameType]) -> None:
        if cmd.number is None:
            self.clear_breakpoints()
            return

        self.clear_breakpoint(cmd.number)

    @handle.register
    def _(self, _cmd: StepCommand, frame: FrameType) -> None:
        self.set_trace_mode(self._step, frame)

    @handle.register
    def _(self, _cmd: NextCommand, frame: FrameType) -> None:
        self.set_trace_mode(self._next, frame)

    @handle.register
    def _(self, _cmd: LineCommand, frame: FrameType) -> None:
        notify.list_lines(frame)

    @handle.register
    def _(self, _cmd: DisassembleCommand, frame: FrameType) -> None:
        notify.list_instrs(frame)
        notify.list_stack(frame)

    @handle.register
    def _(self, cmd: EvaluateCommand, frame: FrameType) -> None:
        try:
            notify.p(cmd(frame))
        except Exception as e:
            notify.dfly(f"error evaluating expression: {e}")

    @handle.register
    def _(self, _cmd: QuitCommand, _frame: t.Optional[FrameType]) -> None:
        if self.started:
            msg = "dragonfly: target still running, quit anyway? [y/N] "
            if input(msg).lower() not in ("y", "yes"):
                return
        os._exit(0)

    @handle.register
    def _(self, _cmd: ContinueCommand, _frame: t.Optional[FrameType]) -> None:
        pass

    @handle.register
    def _(self, _cmd: TracebackCommand, frame: t.Optional[FrameType]) -> None:
        print_stack(frame)

    @handle.register
    def _(self, cmd: SetCommand, _frame: t.Optional[FrameType]) -> None:
        try:
            self.settings.set(cmd.setting, cmd.value)
        except ValueError as e:
            notify.dfly(f"error setting {cmd.setting}: {e}")

    @handle.register
    def _(self, cmd: HelpCommand, _frame: t.Optional[FrameType]) -> None:
        if cmd.topic is None:
            commands = sorted(_COMMANDS.items(), key=lambda x: x[0])

            notify.d(
                """\
                dragonfly commands:

                    NOTE: commands are matched by prefix to allow for short forms.

                """
            )

            for a, c in commands:
                notify.p(f"    {a:16s}{t.cast(str, c.__doc__).splitlines()[0]}\n")
        else:
            notify.p("\n" + t.cast(str, _COMMANDS[cmd.topic].__doc__))


# Update the commands with their action names and create a mapping for easy
# lookup.

for c in DebuggerCommand.__subclasses__():
    c.__action__ = c.__name__[: -len("command")].lower()


_COMMANDS = {c.__action__: c for c in DebuggerCommand.__subclasses__()}
# Define aliases
_COMMANDS.update({"where": TracebackCommand, "tb": TracebackCommand})


def _command_stream() -> t.Iterable[DebuggerCommand]:
    while True:
        try:
            for c in (_.strip() for _ in input("ᖭི༏ ").strip().split(";;") if _):
                action, _, argstr = c.partition(" ")
                if not (matches := [(cls, name) for name, cls in _COMMANDS.items() if name.startswith(action)]):
                    notify.dfly(f"unknown command: {action}")
                elif len(matches) > 1:
                    notify.dfly(f"ambiguous command '{action}': matches {', '.join(_[1] for _ in matches)}")
                else:
                    ((cmd, _),) = matches
                    try:
                        yield cmd(*(args := shlex.split(argstr)))
                    except TypeError:
                        notify.dfly(
                            f"wrong number of arguments for command {cmd.__action__}: "
                            f"expected {len(signature(cmd.__init__).parameters)-1}, given {len(args)}"
                        )
                    except Exception as e:
                        if isinstance(e, DebuggerCommandError):
                            notify.dfly(f"{cmd.__action__} command error: {e}")
                        else:
                            raise

        except EOFError:
            break


COMMAND_STREAM = _command_stream()
