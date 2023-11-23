import os
import sys

import preload  # noqa

# Check for and import any sitecustomize that would have normally been used
bootstrap_dir = os.path.abspath(os.path.dirname(__file__))
abs_paths = [os.path.abspath(_) for _ in sys.path]
if bootstrap_dir in abs_paths:
    index = abs_paths.index(bootstrap_dir)
    del sys.path[index]

    sys.modules["dragonfly._bootstrap.sitecustomize"] = sys.modules.pop("sitecustomize")

    try:
        import sitecustomize
    except ImportError:
        # If an additional sitecustomize is not found then put our sitecustomize
        # back.
        sys.modules["sitecustomize"] = sys.modules.pop("dragonfly._bootstrap.sitecustomize")
    finally:
        sys.path.insert(index, bootstrap_dir)
else:
    try:
        import sitecustomize  # noqa
    except ImportError:
        pass
