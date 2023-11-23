import typing as t
from abc import ABC
from abc import abstractmethod
from types import FrameType

from dragonfly._breakpoint.model import Breakpoint
from dragonfly._breakpoint.model import BreakpointCondition
from dragonfly._breakpoint.model import LineBreakpoint
from dragonfly._breakpoint.registry import BreakpointRegistry
from dragonfly._settings import DragonflySettings


class DebuggerInterface(ABC):
    @property
    def started(self) -> bool:  # type: ignore[empty-body]
        ...

    @property
    def settings(self) -> DragonflySettings:  # type: ignore[empty-body]
        ...

    @property
    def registry(self) -> BreakpointRegistry:  # type: ignore[empty-body]
        ...

    @abstractmethod
    def set_breakpoint(
        self,
        bp: Breakpoint,
        cond: t.Optional[BreakpointCondition],
        frame: t.Optional[FrameType] = None,
    ) -> None: ...

    @abstractmethod
    def clear_breakpoint(self, number: int) -> None: ...

    @abstractmethod
    def clear_breakpoints(self) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def interrupt(self, frame: t.Optional[FrameType] = None, bp: t.Optional[LineBreakpoint] = None) -> None: ...
