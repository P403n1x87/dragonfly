import dis
import linecache
import logging
import os
import threading
import typing as t
from functools import singledispatch
from textwrap import dedent
from textwrap import wrap
from types import FrameType

from dragonfly._breakpoint.model import Breakpoint
from dragonfly._breakpoint.model import FunctionBreakpoint
from dragonfly._breakpoint.model import LineBreakpoint
from dragonfly._breakpoint.registry import BreakpointRegistryEntry
from dragonfly._maxilla import get_stack

logging.basicConfig(level=logging.INFO, format="%(message)s")

log = logging.root


def _bp(
    entry: BreakpointRegistryEntry, verb: str, line: t.Optional[int] = None, thread: t.Optional[threading.Thread] = None
) -> None:
    bp = entry.breakpoint
    thread_info = f", in thread {thread.name}" if thread is not None else ""

    if isinstance(bp, LineBreakpoint):
        bp_line = line if line is not None else bp.line
        if bp_line == -1:
            log.info("Breakpoint #%d %s at %s, on entry%s", entry.number, verb, bp.source, thread_info)
        else:
            log.info("Breakpoint #%d %s at %s, line %d%s", entry.number, verb, bp.source, bp_line, thread_info)

    elif isinstance(bp, FunctionBreakpoint):
        log.info(
            "Breakpoint #%d %s on function %s, in module %d%s", entry.number, verb, bp.function, bp.module, thread_info
        )


def hit(entry: BreakpointRegistryEntry, line: t.Optional[int] = None) -> None:
    _bp(entry, "hit", line, threading.current_thread())


def bp_set(entry: BreakpointRegistryEntry, line: t.Optional[int] = None) -> None:
    _bp(entry, "set", line)


def bp_clear(entry: BreakpointRegistryEntry) -> None:
    _bp(entry, "cleared")


@singledispatch
def bp_error(_bp: Breakpoint, _msg: str) -> None: ...


@bp_error.register
def _(bp: LineBreakpoint, msg: str) -> None:
    if bp.line == -1:
        dfly(f"error setting breakpoint at {bp.source}, on entry: {msg}")
    else:
        dfly(f"error setting breakpoint at {bp.source}, line {bp.line}: {msg}")


@bp_error.register
def _(bp: FunctionBreakpoint, msg: str) -> None:
    dfly(f"error setting breakpoint on {bp.function}, in module {bp.module}: {msg}")


@singledispatch
def request(_bp: Breakpoint) -> None: ...


@request.register
def _(bp: LineBreakpoint) -> None:
    if bp.line == -1:
        log.info("Breakpoint request at %s, on entry", bp.source)
    else:
        log.info("Breakpoint request at %s, line %d", bp.source, bp.line)


@request.register
def _(bp: FunctionBreakpoint) -> None:
    log.info("Breakpoint request for function %s, in module %s", bp.function, bp.module)


def dfly(message: str) -> None:
    log.error("dragonfly: %s", message)


def frame(frame: FrameType) -> None:
    code = frame.f_code
    log.info(
        "File %s, line %s, in %s",
        code.co_filename,
        frame.f_lineno and str(frame.f_lineno) or f"<unknown> (lasti {frame.f_lasti})",
        code.co_name,
    )

    current_line = linecache.getline(code.co_filename, frame.f_lineno)
    if current_line != "":
        log.info(">>> %s", current_line.strip("\n"))


def list_lines(frame: FrameType, before: int = 5, after: int = 5) -> None:
    if frame.f_lineno is None:
        log.info("<unknown current line location>")
        return

    code = frame.f_code
    start = max(1, frame.f_lineno - before)
    end = frame.f_lineno + after
    for i in range(start, end + 1):
        marker = "-->" if i == frame.f_lineno else "   "
        line = linecache.getline(code.co_filename, i)
        if line == "":
            break
        line = line.strip("\n")
        log.info(f"{i:4} {marker} {line}")


def list_instrs(frame: FrameType, before: int = 5, after: int = 5) -> None:
    instrs = list(dis.get_instructions(frame.f_code))

    index = -1
    for i, instr in enumerate(instrs):
        if instr.offset >= frame.f_lasti:
            index = i + (instr.offset > frame.f_lasti)
            break

    start = max(0, index - before)
    end = index + after

    w, _ = os.get_terminal_size()

    for i in range(start, end + 1):
        try:
            ins = instrs[i]
        except IndexError:
            continue
        marker = "-->" if i == index else "   "
        iarg = f"{ins.arg} ({ins.argval})" if ins.argval is not None else ""
        lineno = f"{ins.starts_line:4d}" if ins.starts_line is not None else " " * 4
        if ins.starts_line is not None and start < i < end:
            log.info("")
        log.info(f"{lineno} {marker} {ins.offset:6d} {ins.opname:30s}{iarg[:w-34]}")


def list_stack(frame: FrameType) -> None:
    if (n := (stack := get_stack(frame)).pop(-1)) == 0:
        log.info("< Empty stack >")
        return

    if n < 0:
        log.info("< Invalid stack size! >")
        return

    for i in range(n):
        prefix = f"TOS-{n-1-i}"
        log.info("%8s = %s", prefix, stack.get(i, "NULL"))


def return_value(value: t.Any) -> None:
    log.info("@return = %s", value)


def p(msg):
    log.info(msg)


def d(msg):
    log.info(dedent(msg))


def w(msg, indent=None):
    for _ in wrap(msg, initial_indent=" " * (indent or 0), subsequent_indent=" " * (indent or 0)):
        log.info(_)
