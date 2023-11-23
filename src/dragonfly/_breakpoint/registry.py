import heapq
import typing as t
from dataclasses import dataclass

import dragonfly._notify as notify
from dragonfly._breakpoint.model import Breakpoint
from dragonfly._breakpoint.model import BreakpointCondition
from dragonfly._module import ModuleHookType
from dragonfly._module import TransformerType


@dataclass
class BreakpointRegistryEntry:
    breakpoint: Breakpoint  # noqa
    number: int
    condition: t.Optional[BreakpointCondition] = None
    installed: bool = False
    enabled: bool = True
    hook: t.Optional[ModuleHookType] = None
    transformer: t.Optional[TransformerType] = None


class BreakpointRegistry:
    def __init__(self) -> None:
        self._entries: t.Dict[Breakpoint, BreakpointRegistryEntry] = {}
        self._index: t.Dict[int, Breakpoint] = {}

        rn: t.List[int] = []
        heapq.heapify(rn)
        self._returned_numbers = rn

    def mark_installed(self, bp: Breakpoint) -> None:
        self._entries[bp].installed = True

    def register(
        self, bp: Breakpoint, cond: t.Optional[BreakpointCondition] = None
    ) -> t.Optional[BreakpointRegistryEntry]:
        if bp in self._entries:
            if (entry := self._entries[bp]).condition == cond:
                msg = f"breakpoint {bp} already registered"
                raise ValueError(msg)
            # The condition doesn't match, so we replace it
            entry.condition = cond
            if cond is None:
                notify.p(f"Breakpoint #{entry.number} condition removed")
            else:
                notify.p(f"Breakpoint #{entry.number} condition updated")
            return None

        number = heapq.heappop(self._returned_numbers) if self._returned_numbers else (len(self._entries) + 1)
        self._index[number] = bp
        entry = self._entries[bp] = BreakpointRegistryEntry(breakpoint=bp, number=number, condition=cond)

        return entry

    def unregister(self, number: int) -> BreakpointRegistryEntry:
        if (bp := self._index.pop(number, None)) is None:
            msg = f"no breakpoint registered with number {number}"
            raise ValueError(msg)

        heapq.heappush(self._returned_numbers, (entry := self._entries.pop(bp)).number)

        return entry

    def clear(self) -> None:
        self._entries.clear()
        self._index.clear()
        self._returned_numbers.clear()

    def __contains__(self, bp: Breakpoint) -> bool:
        return bp in self._entries

    def __getitem__(self, bp: Breakpoint) -> BreakpointRegistryEntry:
        return self._entries[bp]

    @property
    def entries(self) -> t.List[BreakpointRegistryEntry]:
        return sorted(self._entries.values(), key=lambda entry: entry.number)
