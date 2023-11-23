import abc
import runpy
import sys
import typing as t
from collections import defaultdict
from collections import deque
from dis import findlinestarts
from importlib.abc import Loader
from importlib.machinery import ModuleSpec
from importlib.util import find_spec
from pathlib import Path
from types import CodeType
from types import ModuleType
from weakref import WeakValueDictionary as WVDict

from dragonfly._maxilla import replace_in_tuple

ModuleHookType = t.Callable[[ModuleType], None]
TransformerType = t.Callable[[CodeType], CodeType]
PreExecHookType = t.Callable[[t.Any, ModuleType], None]
PreExecHookCond = t.Union[str, t.Callable[[str], bool]]


_run_code = runpy._run_code  # type: ignore[attr-defined]

_post_run_module_hooks: t.List[ModuleHookType] = []
_pre_run_module_hooks: t.List[ModuleHookType] = []
_run_module_transformers: t.List[TransformerType] = []


def get_argument_value(args: t.Tuple[t.Any, ...], kwargs: t.Dict[str, t.Any], index: int, name: str) -> t.Any:
    try:
        return args[index]
    except IndexError:
        try:
            return kwargs[name]
        except KeyError as e:
            msg = f"Argument {name} not found"
            raise ValueError(msg) from e


def collect_code_objects(code: CodeType) -> t.Iterator[t.Tuple[CodeType, CodeType]]:
    q = deque([code])
    while q:
        c = q.popleft()
        for next_code in (_ for _ in c.co_consts if isinstance(_, CodeType)):
            q.append(next_code)
            yield (next_code, c)


def get_lines(code: CodeType) -> t.Iterator[int]:
    yield from (ln for _, ln in findlinestarts(code) if ln > 0)


def _wrapped_run_code(*args: t.Any, **kwargs: t.Any) -> t.Dict[str, t.Any]:
    # DEV: If we are calling this wrapper then _run_code must have been set to
    # the original runpy._run_code.
    code = get_argument_value(args, kwargs, 0, "code")
    mod_name = get_argument_value(args, kwargs, 3, "mod_name")

    module = sys.modules[mod_name]
    for hook in _pre_run_module_hooks:
        hook(module)

    for transformer in _run_module_transformers:
        code = transformer(code)

    kwargs.pop("code", None)
    new_args = (code, *args[1:])

    module.__code__ = code  # type: ignore[attr-defined]

    try:
        return _run_code(*new_args, **kwargs)
    finally:
        module = sys.modules[mod_name]
        for hook in _post_run_module_hooks:
            hook(module)


runpy._run_code = _wrapped_run_code  # type: ignore[attr-defined]


def register_pre_run_module_hook(hook: ModuleHookType) -> None:
    """Register a pre run module hook.

    The hooks gets called before the module is loaded. For this to work, the
    hook needs to be registered during the interpreter initialization, e.g. as
    part of a sitecustomize.py script.
    """
    _pre_run_module_hooks.append(hook)


def unregister_pre_run_module_hook(hook: ModuleHookType) -> None:
    """Unregister a pre run module hook.

    If the hook was not registered, a ``ValueError`` exception is raised.
    """
    _pre_run_module_hooks.remove(hook)


def register_post_run_module_hook(hook: ModuleHookType) -> None:
    """Register a post run module hook.

    The hooks gets called after the module is loaded. For this to work, the
    hook needs to be registered during the interpreter initialization, e.g. as
    part of a sitecustomize.py script.
    """
    _post_run_module_hooks.append(hook)


def unregister_post_run_module_hook(hook: ModuleHookType) -> None:
    """Unregister a post run module hook.

    If the hook was not registered, a ``ValueError`` exception is raised.
    """
    _post_run_module_hooks.remove(hook)


def register_run_module_transformer(transformer: TransformerType) -> None:
    """Register a run module transformer."""
    _run_module_transformers.append(transformer)


def unregister_run_module_transformer(transformer: TransformerType) -> None:
    """Unregister a run module transformer.

    If the transformer was not registered, a ``ValueError`` exception is raised.
    """
    _run_module_transformers.remove(transformer)


def origin(module: ModuleType) -> t.Optional[Path]:
    """Get the origin source file of the module."""
    try:
        # DEV: Use object.__getattribute__ to avoid potential side-effects.
        orig = Path(object.__getattribute__(module, "__file__")).resolve()
    except (AttributeError, TypeError):
        # Module is probably only partially initialised, so we look at its
        # spec instead
        try:
            # DEV: Use object.__getattribute__ to avoid potential side-effects.
            orig = Path(object.__getattribute__(module, "__spec__").origin).resolve()
        except (AttributeError, ValueError, TypeError):
            orig = None

    if orig is not None and orig.is_file():
        return orig.with_suffix(".py") if orig.suffix == ".pyc" else orig

    return None


# Borrowed from the wrapt module
# https://github.com/GrahamDumpleton/wrapt/blob/df0e62c2740143cceb6cafea4c306dae1c559ef8/src/wrapt/importer.py


def find_loader(fullname: str) -> t.Optional[Loader]:
    return getattr(find_spec(fullname), "loader", None)


class _ImportHookChainedLoader(Loader):
    def __init__(self, loader: Loader, handler) -> None:
        self.loader = loader
        self.handler = handler
        self.callbacks: t.Dict[t.Any, t.Callable[[ModuleType], None]] = {}
        self.transformers: t.Dict[t.Any, TransformerType] = {}

        # DEV: load_module is deprecated so we define it at runtime if also
        # defined by the default loader. We also check and define for the
        # methods that are supposed to replace the load_module functionality.
        if hasattr(loader, "load_module"):
            self.load_module = self._load_module  # type: ignore[assignment]
        if hasattr(loader, "create_module"):
            self.create_module = self._create_module  # type: ignore[assignment]
        if hasattr(loader, "exec_module"):
            self.exec_module = self._exec_module  # type: ignore[assignment]

    def __getattr__(self, name):
        # Proxy any other attribute access to the underlying loader.
        return getattr(self.loader, name)

    def add_callback(self, key: t.Any, callback: t.Callable[[ModuleType], None]) -> None:
        self.callbacks[key] = callback

    def add_transformer(self, key: t.Any, transformer: TransformerType) -> None:
        self.transformers[key] = transformer

    def _load_module(self, fullname: str) -> ModuleType:
        module = self.loader.load_module(fullname)
        for callback in self.callbacks.values():
            callback(module)

        return module

    def _create_module(self, spec):
        return self.loader.create_module(spec)

    def _exec_module(self, module):
        _get_code = getattr(self.loader, "get_code", None)
        if _get_code is not None:

            def get_code(_loader, fullname):
                code = _get_code(fullname)

                for callback in self.transformers.values():
                    code = callback(code)

                module.__code__ = code

                return code

            self.loader.get_code = get_code.__get__(self.loader, type(self.loader))

        self.loader.exec_module(module)

        for callback in self.callbacks.values():
            callback(module)


class BaseModuleWatchdog(abc.ABC):
    """Base module watchdog.

    Invokes ``after_import`` every time a new module is imported.
    """

    _instance: t.Optional["BaseModuleWatchdog"] = None

    def __init__(self) -> None:
        self._finding: t.Set[str] = set()

    def _add_to_meta_path(self) -> None:
        sys.meta_path.insert(0, self)  # type: ignore[arg-type]

    @classmethod
    def _find_in_meta_path(cls) -> t.Optional[int]:
        for i, meta_path in enumerate(sys.meta_path):
            if type(meta_path) is cls:
                return i
        return None

    @classmethod
    def _remove_from_meta_path(cls) -> None:
        i = cls._find_in_meta_path()

        if i is None:
            raise RuntimeError("%s is not installed" % cls.__name__)

        sys.meta_path.pop(i)

    def after_import(self, module: ModuleType) -> None:
        raise NotImplementedError()

    def code_transformer(self, code: CodeType) -> CodeType:
        return code

    def find_module(self, fullname: str, _path: t.Optional[str] = None) -> t.Optional[Loader]:
        if fullname in self._finding:
            return None

        self._finding.add(fullname)

        try:
            loader = find_loader(fullname)
            if loader is not None:
                if not isinstance(loader, _ImportHookChainedLoader):
                    loader = _ImportHookChainedLoader(loader, self)

                loader.add_callback(type(self), self.after_import)

                return loader

        finally:
            self._finding.remove(fullname)

        return None

    def find_spec(
        self, fullname: str, _path: t.Optional[str] = None, _target: t.Optional[ModuleType] = None
    ) -> t.Optional[ModuleSpec]:
        if fullname in self._finding:
            return None

        self._finding.add(fullname)

        try:
            try:
                # Best effort
                spec = find_spec(fullname)
            except Exception:
                return None

            if spec is None:
                return None

            loader = getattr(spec, "loader", None)

            if loader is not None:
                if not isinstance(loader, _ImportHookChainedLoader):
                    spec.loader = _ImportHookChainedLoader(loader, self)

                t.cast(_ImportHookChainedLoader, spec.loader).add_callback(type(self), self.after_import)
                t.cast(_ImportHookChainedLoader, spec.loader).add_transformer(type(self), self.code_transformer)

            return spec

        finally:
            self._finding.remove(fullname)

    @classmethod
    def _check_installed(cls) -> None:
        if not cls.is_installed():
            raise RuntimeError("%s is not installed" % cls.__name__)

    @classmethod
    def install(cls) -> None:
        """Install the module watchdog."""
        if cls.is_installed():
            raise RuntimeError("%s is already installed" % cls.__name__)

        cls._instance = cls()
        cls._instance._add_to_meta_path()

    @classmethod
    def is_installed(cls):
        """Check whether this module watchdog class is installed."""
        return cls._instance is not None and type(cls._instance) is cls

    @classmethod
    def uninstall(cls) -> None:
        """Uninstall the module watchdog.

        This will uninstall only the most recently installed instance of this
        class.
        """
        cls._check_installed()
        cls._remove_from_meta_path()

        cls._instance = None


class ModuleWatchdog(BaseModuleWatchdog):
    """Module watchdog.

    Hooks into the import machinery to detect when modules are loaded/unloaded.
    This is also responsible for triggering any registered import hooks.

    Subclasses might customize the default behavior by overriding the
    ``after_import`` method, which is triggered on every module import, once
    the subclass is installed.
    """

    def __init__(self) -> None:
        self._hook_map: t.DefaultDict[str, t.List[ModuleHookType]] = defaultdict(list)
        self._transformer_map: t.DefaultDict[str, t.List[t.Callable[[CodeType], CodeType]]] = defaultdict(list)
        self._om: t.Optional[t.Dict[str, ModuleType]] = None
        self._finding: t.Set[str] = set()

        register_post_run_module_hook(self.after_import)
        register_run_module_transformer(self.code_transformer)

    @property
    def _origin_map(self) -> t.Dict[str, ModuleType]:
        def modules_with_origin(modules):
            result = WVDict({str(origin(m)): m for m in modules})
            try:
                del result[None]
            except KeyError:
                pass
            return result

        if self._om is None:
            try:
                self._om = modules_with_origin(sys.modules.values())
            except RuntimeError:
                # The state of sys.modules might have been mutated by another
                # thread. We try to build the full mapping at the next occasion.
                # For now we take the more expensive route of building a list of
                # the current values, which might be incomplete.
                return modules_with_origin(list(sys.modules.values()))

        return self._om

    def after_import(self, module: ModuleType) -> None:
        module_path = origin(module)
        path = str(module_path) if module_path is not None else None
        if path is not None:
            self._origin_map[path] = module

        # Collect all hooks by module origin and name
        hooks = []
        if path is not None and path in self._hook_map:
            hooks.extend(self._hook_map[path])
        if module.__name__ in self._hook_map:
            hooks.extend(self._hook_map[module.__name__])

        if hooks:
            for hook in hooks:
                hook(module)

    def code_transformer(self, code: CodeType) -> CodeType:
        path = str(Path(code.co_filename).resolve())

        for transformer in self._transformer_map.get(path, []):
            code = transformer(code)

        return code

    @classmethod
    def get_by_origin(cls, _origin: Path) -> t.Optional[ModuleType]:
        """Lookup a module by its origin."""
        cls._check_installed()

        instance = t.cast(ModuleWatchdog, cls._instance)

        path = str(_origin)
        module = instance._origin_map.get(path)
        if module is not None:
            return module

        # Check if this is the __main__ module
        main_module = sys.modules.get("__main__")
        if main_module is not None and origin(main_module) == _origin:
            # Register for future lookups
            instance._origin_map[path] = main_module

            return main_module

        return None

    @classmethod
    def register_origin_hook(cls, origin: Path, hook: ModuleHookType) -> None:
        """Register a hook to be called when the module with the given origin is
        imported.

        The hook will be called with the module object as argument.
        """
        cls._check_installed()

        # DEV: Under the hypothesis that this is only ever called by the probe
        # poller thread, there are no further actions to take. Should this ever
        # change, then thread-safety might become a concern.
        path = str(origin)

        instance = t.cast(ModuleWatchdog, cls._instance)
        instance._hook_map[path].append(hook)
        try:
            module = instance._origin_map[path]
            # Sanity check: the module might have been removed from sys.modules
            # but not yet garbage collected.
            try:
                sys.modules[module.__name__]
            except KeyError:
                del instance._origin_map[path]
                raise
        except KeyError:
            # The module is not loaded yet. Nothing more we can do.
            return

        # The module was already imported so we invoke the hook straight-away
        hook(module)

    @classmethod
    def unregister_origin_hook(cls, origin: Path, hook: ModuleHookType) -> None:
        """Unregister the hook registered with the given module origin and
        argument.
        """
        cls._check_installed()

        path = str(origin)

        instance = t.cast(ModuleWatchdog, cls._instance)
        if path not in instance._hook_map:
            raise ValueError("No hooks registered for origin %s" % origin)

        try:
            if path in instance._hook_map:
                hooks = instance._hook_map[path]
                hooks.remove(hook)
                if not hooks:
                    del instance._hook_map[path]
        except ValueError as e:
            msg = f"Hook {hook} not registered for origin {origin}"
            raise ValueError(msg) from e

    @classmethod
    def register_module_hook(cls, module: str, hook: ModuleHookType) -> None:
        """Register a hook to be called when the module with the given name is
        imported.

        The hook will be called with the module object as argument.
        """
        cls._check_installed()

        instance = t.cast(ModuleWatchdog, cls._instance)
        instance._hook_map[module].append(hook)
        try:
            module_object = sys.modules[module]
        except KeyError:
            # The module is not loaded yet. Nothing more we can do.
            return

        # The module was already imported so we invoke the hook straight-away
        hook(module_object)

    @classmethod
    def unregister_module_hook(cls, module: str, hook: ModuleHookType) -> None:
        """Unregister the hook registered with the given module name and
        argument.
        """
        cls._check_installed()

        instance = t.cast(ModuleWatchdog, cls._instance)
        if module not in instance._hook_map:
            raise ValueError("No hooks registered for module %s" % module)

        try:
            if module in instance._hook_map:
                hooks = instance._hook_map[module]
                hooks.remove(hook)
                if not hooks:
                    del instance._hook_map[module]
        except ValueError as e:
            msg = f"Hook {hook} not registered for module {module}"
            raise ValueError(msg) from e

    @classmethod
    def register_transformer(cls, origin: Path, transformer: TransformerType) -> None:
        cls._check_installed()

        path = str(origin)

        instance = t.cast(ModuleWatchdog, cls._instance)
        instance._transformer_map[path].append(transformer)

    @classmethod
    def transformer(cls, origin: Path) -> t.Callable[[TransformerType], TransformerType]:
        def _(transformer: TransformerType) -> TransformerType:
            cls.register_transformer(origin, transformer)
            return transformer

        return _

    @classmethod
    def unregister_transformer(cls, origin, transformer):
        cls._check_installed()

        path = str(origin)

        instance = t.cast(ModuleWatchdog, cls._instance)
        if path not in instance._transformer_map:
            raise ValueError("No hooks registered for origin %s" % origin)

        try:
            if path in instance._transformer_map:
                hooks = instance._transformer_map[path]
                hooks.remove(transformer)
                if not hooks:
                    del instance._transformer_map[path]
        except ValueError as e:
            msg = f"Transformer {transformer} not registered for origin {origin}"
            raise ValueError(msg) from e


class CodeDiscovery:
    def __init__(self, module: ModuleType) -> None:
        self.module = module
        self._lines: t.Dict[int, CodeType] = {}
        self._codes: t.Dict[CodeType, CodeType] = {}

        module_code = module.__dict__.pop("__code__", None)
        if module_code is None:
            return

        for code, parent in collect_code_objects(module_code):
            self._codes[code] = parent
            for ln in get_lines(code):
                self._lines[ln] = code

    def at_line(self, line: int) -> t.Tuple[CodeType, CodeType]:
        code = self._lines[line]
        return (code, self._codes[code])

    def replace(self, old_code: CodeType, new_code: CodeType) -> None:
        self._codes[new_code] = parent = self._codes.pop(old_code)

        for ln in get_lines(old_code):
            self._lines[ln] = new_code

        replace_in_tuple(parent.co_consts, old_code, new_code)

    @classmethod
    def from_module(cls, module: ModuleType) -> "CodeDiscovery":
        try:
            return module.__discovery__  # type: ignore[attr-defined]
        except AttributeError:
            result = module.__discovery__ = cls(module)  # type: ignore[attr-defined]
            return result
