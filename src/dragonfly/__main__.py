import argparse
import os
import shutil
import site
from pathlib import Path

from dragonfly._version import __version__  # type: ignore[import-not-found]


def main():
    parser = argparse.ArgumentParser(prog="dragonfly")
    parser.add_argument("-r", "--run", action="store_true", help="Run the given command immediately")
    parser.add_argument("command", nargs=argparse.REMAINDER, type=str, help="Command string to execute")
    parser.add_argument("-V", "--version", action="version", version=__version__)
    args = parser.parse_args()

    python_paths = os.environ.get("PYTHONPATH", "").split(os.path.pathsep)
    python_paths.insert(0, str(Path(__file__).parent.resolve() / "_bootstrap"))
    python_paths.extend(site.getsitepackages())

    os.environ["PYTHONPATH"] = os.path.pathsep.join(python_paths)

    # Pass options
    os.environ["DRAGONFLY_RUN"] = str(int(args.run))

    executable = shutil.which(args.command[0])
    os.execl(executable, executable, *args.command[1:])  # noqa


if __name__ == "__main__":
    main()
