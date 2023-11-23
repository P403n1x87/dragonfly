# This file is part of "dragonfly" which is released under MIT.
#
# Copyright (c) 2023 Gabriele N. Tornetta <phoenix1987@gmail.com>.

from pathlib import Path

from setuptools import Extension
from setuptools import setup

codemodule = Extension(
    "dragonfly._maxilla",
    sources=["src/dragonfly/_maxilla.c"],
)

setup(
    name="dfly",
    author="Gabriele N. Tornetta",
    description="Lightweight CPython Debugger",
    long_description=Path("README.md")
    .read_text()
    .replace('src="art/', 'src="https://raw.githubusercontent.com/P403n1x87/dragonfly/main/art/'),
    ext_modules=[codemodule],
    packages=["dragonfly"],
    package_dir={"": "src"},
)
