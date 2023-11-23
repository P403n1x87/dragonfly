import atexit
import sys
import threading
import typing as t
from collections import defaultdict
from enum import Enum
from pathlib import Path
from types import CodeType
from types import FrameType

import dragonfly._notify as notify
from dragonfly._breakpoint.model import LineBreakpoint
from dragonfly._interface import DebuggerInterface
from dragonfly._module import CodeDiscovery
from dragonfly._module import ModuleWatchdog
from dragonfly._module import origin

if sys.version_info >= (3, 12):
    settrace = threading.settrace_all_threads
else:
    from dragonfly._maxilla import propagate_trace

    def settrace(f):
        # Set the trace function for future threads
        threading.settrace(f)
        # Set it for the calling thread
        sys.settrace(f)
        # Propagate it to all the other running threads
        propagate_trace()


if sys.version_info < (3, 9):

    def is_relative_to(self, *other):
        """Return True if the path is relative to another path or False."""
        try:
            self.relative_to(*other)
            return True
        except ValueError:
            return False

    Path.is_relative_to = is_relative_to

TraceFunction = t.Callable[[FrameType, str, t.Any], t.Optional["TraceFunction"]]

NotSet = object()


class TraceModeOutcome(Enum):
    DONE = 0
    CONTINUE = 1
    PROMPT = 2


TraceMode = t.Callable[[FrameType, str, t.Any], TraceModeOutcome]


def get_current_frames(frame: t.Optional[FrameType] = None) -> t.Iterator[FrameType]:
    for top_frame in [frame] if frame is not None else sys._current_frames().values():
        frame = top_frame
        while frame is not None:
            yield frame
            frame = frame.f_back


def code_for_location(source: Path, line: int) -> t.Optional[CodeType]:
    module = ModuleWatchdog.get_by_origin(source)
    if module is None:
        # Check if it is the main module
        if (module := sys.modules.get("__main__", None)) is None or origin(module) != source:
            return None

    try:
        code, _ = CodeDiscovery.from_module(module).at_line(line)
    except KeyError:
        return None

    return code


class DebuggerTracingMixin(DebuggerInterface):
    def __init__(self) -> None:
        super().__init__()

        self._traced_breakpoints: t.DefaultDict[Path, t.List[int]] = defaultdict(list)
        self._original_settrace = sys.gettrace()

        self.reset_tracing()

        @atexit.register
        def _():
            settrace(self._original_settrace)

    def reset_tracing(self) -> None:
        self._trace_mode: t.Optional[TraceMode] = None
        self._call = 0

    @property
    def tracing_required(self) -> bool:
        return bool(self._traced_breakpoints) or self._trace_mode is not None

    def set_traced_breakpoint(self, bp: LineBreakpoint, frame: t.Optional[FrameType] = None) -> None:
        if (code := code_for_location(bp.source, bp.line)) is None:
            return

        tracing_required = False
        for fr in get_current_frames(frame):
            if fr.f_code is code:
                tracing_required = True
                self._trace_frame(fr)

        if tracing_required:
            self._traced_breakpoints[bp.source].append(bp.line)

    def clear_traced_breakpoint(self, bp: LineBreakpoint) -> None:
        if bp.source not in self._traced_breakpoints:
            return

        self._traced_breakpoints[bp.source].remove(bp.line)

        if not self._traced_breakpoints[bp.source]:
            del self._traced_breakpoints[bp.source]

    def _at_traced_breakpoint(self, frame: FrameType) -> bool:
        return frame.f_lineno in self._traced_breakpoints.get(Path(frame.f_code.co_filename).resolve(), [])

    def _update_traced_breakpoints(self) -> None:
        # Remove all breakpoints that target frames no longer on the stacks.
        # We will break via bytecode next time, if needed.
        current_frames = get_current_frames()
        for source, ls in list(self._traced_breakpoints.items()):
            bp_module = ModuleWatchdog.get_by_origin(source)
            if bp_module is None:
                continue
            for line in list(ls):
                code, _ = CodeDiscovery.from_module(bp_module).at_line(line)
                if all(fr.f_code is not code for fr in current_frames):
                    ls.remove(line)
            if not ls:
                del self._traced_breakpoints[source]

    def set_tracing(self) -> None:
        # perf: set tracing only on the threads that need it
        settrace(self._trace)

    def _trace_frame(self, frame: FrameType) -> None:
        frame.f_trace = self._trace

    def set_trace_mode(self, trace_mode: TraceMode, frame: FrameType) -> None:
        self._trace_mode = trace_mode
        frame.f_trace = self._trace

    def _trace(self, frame: FrameType, event: str, arg: t.Any) -> t.Optional[TraceFunction]:
        # Do not trace the tracing function
        settrace(self._original_settrace)

        frame.f_trace_opcodes = self.settings.trace_opcodes == "1"

        try:
            # Check if we have a breakpoint at this line
            if self._at_traced_breakpoint(frame):
                self.interrupt(frame, LineBreakpoint(Path(frame.f_code.co_filename).resolve(), frame.f_lineno))
            # Otherwise, do the set trace mode, if any.
            elif self._trace_mode is not None:
                if (outcome := self._trace_mode(frame, event, arg)) is TraceModeOutcome.DONE:
                    self._trace_mode = None
                elif outcome is TraceModeOutcome.CONTINUE:
                    settrace(self._trace)
                    return self._trace
                elif outcome is TraceModeOutcome.PROMPT:
                    self.interrupt(frame)
                else:
                    msg = f"invalid trace mode outcome: {outcome}"
                    raise ValueError(msg)

            # If we still have breakpoints on live frames, continue tracing.
            if self._traced_breakpoints:
                settrace(self._trace)
                return self._trace

        finally:
            self._update_traced_breakpoints()

        return None

    def _step(self, _frame: FrameType, _event: str, _arg: t.Any) -> TraceModeOutcome:
        return TraceModeOutcome.PROMPT

    def _next(self, frame: FrameType, event: str, arg: t.Any) -> TraceModeOutcome:
        if "call" in event:
            self._call += 1

        call = self._call

        # Skip dragonfly and other irrelevant frames
        is_dfly_frame = Path(frame.f_code.co_filename).is_relative_to(Path(__file__).parent)
        is_runpy = frame.f_code.co_filename == "<frozen runpy>"
        skip = is_dfly_frame or is_runpy

        if "return" in event:
            self._call -= 1
            if self._call < 0:
                if not skip:
                    notify.return_value(arg)
                # Continue stepping from the previous frame after the return
                if frame.f_back is not None:
                    self.set_trace_mode(self._next, frame.f_back)
                self._call = 0

        return TraceModeOutcome.CONTINUE if call or skip else TraceModeOutcome.PROMPT
