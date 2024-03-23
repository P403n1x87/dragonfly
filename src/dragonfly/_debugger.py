import gc
import sys
import typing as t
from functools import partial
from functools import singledispatchmethod
from pathlib import Path
from threading import RLock
from types import FrameType
from types import FunctionType
from types import ModuleType

from dragonfly import _notify as notify
from dragonfly._breakpoint.model import Breakpoint
from dragonfly._breakpoint.model import BreakpointCondition
from dragonfly._breakpoint.model import FunctionBreakpoint
from dragonfly._breakpoint.model import LineBreakpoint
from dragonfly._breakpoint.registry import BreakpointRegistry
from dragonfly._breakpoint.registry import BreakpointRegistryEntry
from dragonfly._commands import COMMAND_STREAM
from dragonfly._commands import DebuggerCommandHandlerMixin
from dragonfly._commands import RunCommand
from dragonfly._injection import eject_hook
from dragonfly._injection import inject_hook
from dragonfly._interface import DebuggerInterface
from dragonfly._module import CodeDiscovery
from dragonfly._module import ModuleWatchdog
from dragonfly._module import origin
from dragonfly._module import register_post_run_module_hook
from dragonfly._module import register_pre_run_module_hook
from dragonfly._settings import DragonflySettings
from dragonfly._tracing import DebuggerTracingMixin
from dragonfly._transformation import transform_code


class Debugger(DebuggerCommandHandlerMixin, DebuggerTracingMixin, DebuggerInterface):
    def __init__(self) -> None:
        super().__init__()
        ModuleWatchdog.install()

        self._started = False
        self._run_module = False
        self._settings = DragonflySettings()
        self._registry = BreakpointRegistry()
        self._interrupt_lock = RLock()

        @register_pre_run_module_hook
        def _(_: ModuleType) -> None:
            self._run_module = True

        @register_post_run_module_hook
        def _(_: ModuleType) -> None:
            self._run_module = False

    def _require_started(self) -> bool:
        if not self._started:
            notify.dfly("target not running")
        return self._started

    def _trap(self, bp: LineBreakpoint) -> None:
        if bp in self._registry:
            # Interrupt only if the breakpoint is still registered
            self.interrupt(bp=bp)

    # --- Breakpoint Injection ---

    @singledispatchmethod
    def _inject_breakpoint(self, bp: Breakpoint, frame: t.Optional[FrameType]) -> None:
        raise NotImplementedError()

    @_inject_breakpoint.register
    def _(self, bp: LineBreakpoint, frame: t.Optional[FrameType], module: ModuleType):
        if bp.line == -1:
            # We can only set a breakpoint on module entry via a transformation
            # function.
            notify.bp_error(bp, "invalid line number")
            return

        # Discover all the function objects that are on the breakpoint line.
        # Inject the debugger trap in them.
        discovery = CodeDiscovery.from_module(module)
        try:
            code, _ = discovery.at_line(bp.line)
        except KeyError:
            notify.bp_error(bp, "invalid line number")
            return

        # Set a traced breakpoint if needed. Call this before replacing the code
        # object, otherwise the matching against the stack frames will fail.
        self.set_traced_breakpoint(bp, frame)

        new_code = inject_hook(code, self._trap, bp.line, bp)
        discovery.replace(code, new_code)
        self._registry.mark_installed(bp)
        notify.bp_set(self._registry[bp])

        # Update all the functions that refer to the code object.
        for f in (_ for _ in gc.get_referrers(code) if isinstance(_, FunctionType) and _.__code__ is code):
            f.__code__ = new_code

    @_inject_breakpoint.register
    def _(self, bp: FunctionBreakpoint, frame: t.Optional[FrameType], module: ModuleType):
        current = module
        for attr in bp.function.split("."):
            # TODO: Handle special cases such as <locals>
            if not hasattr(current, attr):
                notify.bp_error(bp, f"function {bp.function} not found")
                return
            current = getattr(current, attr)

        if not isinstance(current, FunctionType) or not hasattr(current, "__code__"):
            notify.bp_error(bp, "not a function we can set a breakpoint on")
            return

        # We convert a function breakpoint to the equivalent line breakpoint on
        # function entry.
        code = t.cast(FunctionType, current).__code__

        # Replace the function breakpoint with the equivalent line breakpoint.
        self._registry[bp].breakpoint = (
            line_bp := LineBreakpoint(Path(code.co_filename).resolve(), code.co_firstlineno)
        )

        # Inject the equivalent line breakpoint.
        self._inject_breakpoint(line_bp, frame, module)

    def _eject_breakpoint(self, entry: BreakpointRegistryEntry) -> None:
        if isinstance(bp := entry.breakpoint, LineBreakpoint):
            self.clear_traced_breakpoint(bp)

            if entry.installed and bp.line >= 0:
                # A breakpoint on module entry is unlikely to be hit multiple times.
                # We don't bother to eject it. We use the registry to avoid stopping
                # unnecessarily.
                if (module := ModuleWatchdog.get_by_origin(bp.source)) is None:
                    notify.dfly(f"error clearing breakpoint at {bp.source}, line {bp.line}: module not found")
                    return
                discovery = CodeDiscovery.from_module(module)
                try:
                    code, _ = discovery.at_line(bp.line)
                except KeyError:
                    notify.dfly(f"error clearing breakpoint at {bp.source}, line {bp.line}: invalid line number")
                    return

                new_code = eject_hook(code, self._trap, bp.line, bp)
                discovery.replace(code, new_code)

                # Update all the functions that refer to the code object.
                for f in (_ for _ in gc.get_referrers(code) if isinstance(_, FunctionType) and _.__code__ is code):
                    f.__code__ = new_code

            if entry.hook is not None:
                ModuleWatchdog.unregister_origin_hook(bp.source, entry.hook)

            if entry.transformer is not None:
                ModuleWatchdog.unregister_transformer(bp.source, entry.transformer)

        notify.bp_clear(entry)

    @singledispatchmethod
    def set_breakpoint(  # type: ignore[override]
        self,
        bp: Breakpoint,
        cond: t.Optional[BreakpointCondition],
        frame: t.Optional[FrameType] = None,
    ) -> None:
        raise NotImplementedError()

    @set_breakpoint.register
    def _(
        self,
        bp: LineBreakpoint,
        cond: t.Optional[BreakpointCondition],
        frame: t.Optional[FrameType] = None,
    ) -> None:
        try:
            entry = self._registry.register(bp, cond)
        except ValueError:
            notify.dfly("breakpoint already set")
            return
        if entry is None:
            # The entry has been updated with a new condition. No need to
            # register a new hook.
            return

        notify.request(bp)

        # If we are targeting the run module, we need to set the breakpoint
        # straight-away. There is no need of registering a post-import hook.
        if self._run_module and bp.source == origin(module := sys.modules["__main__"]):
            self._inject_breakpoint(bp, frame, module)
            return

        import_hook = None

        if bp.line > 0:
            # perf: register a single hook per source.
            entry.hook = import_hook = partial(self._inject_breakpoint, bp, frame)
            ModuleWatchdog.register_origin_hook(bp.source, import_hook)

        if not self._started:
            # perf: register a single transformer for all the breakpoints.
            entry.transformer = transformer = partial(transform_code, self._trap, entry, import_hook)
            ModuleWatchdog.register_transformer(bp.source, transformer)

    @set_breakpoint.register
    def _(
        self,
        bp: FunctionBreakpoint,
        cond: t.Optional[BreakpointCondition],
        frame: t.Optional[FrameType] = None,
    ) -> None:
        try:
            entry = self._registry.register(bp, cond)
        except ValueError:
            notify.dfly("breakpoint already set")
            return

        if entry is None:
            return None

        notify.request(bp)
        ModuleWatchdog.register_module_hook(bp.module, partial(self._inject_breakpoint, bp, frame))

    def clear_breakpoint(self, number: int) -> None:
        self._eject_breakpoint(self._registry.unregister(number))

    def clear_breakpoints(self) -> None:
        for e in self._registry.entries:
            self._eject_breakpoint(e)
        self._registry.clear()

    def start(self) -> None:
        if self._started:
            notify.dfly("target already running")
            return
        self._started = True

    @property
    def started(self) -> bool:
        return self._started

    @property
    def settings(self) -> DragonflySettings:
        return self._settings

    @property
    def registry(self) -> BreakpointRegistry:
        return self._registry

    def interrupt(self, frame: t.Optional[FrameType] = None, bp: t.Optional[LineBreakpoint] = None) -> None:
        with self._interrupt_lock:
            if bp is not None and bp in self._registry:
                current_frame = sys._getframe(2) if frame is None else frame
                entry = self._registry[bp]

                if entry.condition is not None and not entry.condition(current_frame.f_locals):
                    # The condition didn't match, so we don't interrupt.
                    return

                notify.hit(entry, current_frame.f_lineno)

            self._prompt(frame)

    def run(self) -> None:
        self.handle(RunCommand(), None)

    def _prompt(self, frame: t.Optional[FrameType] = None) -> None:
        self.reset_tracing()

        if frame is None:
            # Skip self
            current_frame: t.Optional[FrameType] = sys._getframe()
            while current_frame is not None and current_frame.f_code.co_filename == __file__:
                current_frame = current_frame.f_back
        else:
            current_frame = frame

        if self._started and current_frame is not None:
            notify.frame(current_frame)

        try:
            for cmd in COMMAND_STREAM:
                if cmd.__require_started__ and not self._require_started():
                    continue

                self.handle(cmd, current_frame if cmd.__require_frame__ else frame)

                if cmd.__require_tracing__:
                    return

                if cmd.__resume_after__:
                    break
        finally:
            if self.tracing_required:
                self.set_tracing()
