import typing as t
from types import CodeType

import dragonfly._notify as notify
from dragonfly._breakpoint.model import LineBreakpoint
from dragonfly._breakpoint.registry import BreakpointRegistryEntry
from dragonfly._injection import inject_hook
from dragonfly._maxilla import replace_in_tuple
from dragonfly._module import ModuleHookType
from dragonfly._module import ModuleWatchdog
from dragonfly._module import collect_code_objects
from dragonfly._module import get_lines


def transform_code(
    trap: t.Callable[[LineBreakpoint], None],
    entry: BreakpointRegistryEntry,
    hook: t.Optional[ModuleHookType],
    module_code: CodeType,
) -> CodeType:
    bp = entry.breakpoint
    assert isinstance(bp, LineBreakpoint), "transforming with line breakpoint"

    transformed = False

    if bp.line == -1:
        for line in get_lines(module_code):
            try:
                module_code = inject_hook(module_code, trap, line, bp)
                transformed = True
                break
            except Exception:
                pass
        else:
            notify.dfly(f"error setting breakpoint on {bp.source}, at entry")
    else:
        line = bp.line
        try:
            module_code = inject_hook(module_code, trap, bp.line, bp)
            transformed = True
        except Exception:
            # The breakpoint is likely not on the module code object. We
            # check whether the breakpoint is on a function in the module
            # because it might be called as part of the module execution.
            for code, parent_code in collect_code_objects(module_code):
                if code is module_code:
                    # We already tried this
                    continue
                try:
                    new_code = inject_hook(code, trap, bp.line, bp)
                    replace_in_tuple(parent_code.co_consts, code, new_code)
                    transformed = True
                    break
                except Exception:
                    pass
            else:
                notify.dfly(f"error setting breakpoint on {bp.source}, line {bp.line}")

    if transformed:
        notify.bp_set(entry, line)
        entry.installed = True
        if hook is not None:
            ModuleWatchdog.unregister_origin_hook(bp.source, hook)

    return module_code
