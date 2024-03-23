<p align="center">
  <br/>
  <img src="art/logo.png"
       alt="Dragonfly logo"
       height="256px" />
  <br/>
</p>

<h3 align="center">Lightweight CPython Debugger</h3>

<p align="center">
  <a href="https://github.com/P403n1x87/dragonfly/actions?workflow=Tests">
    <img src="https://github.com/P403n1x87/dragonfly/workflows/Tests/badge.svg"
         alt="GitHub Actions: Tests">
  </a>
  <a href="https://github.com/P403n1x87/dragonfly/actions?workflow=Checks">
    <img src="https://github.com/P403n1x87/dragonfly/workflows/Checks/badge.svg"
         alt="GitHub Actions: Checks">
  </a>  <a href="https://codecov.io/gh/P403n1x87/dragonfly">
    <img src="https://codecov.io/gh/P403n1x87/dragonfly/branch/main/graph/badge.svg"
         alt="Codecov">
  </a>
  <br/>
  <a href="https://pypi.org/project/dfly/">
    <img src="https://img.shields.io/pypi/v/dfly.svg"
         alt="PyPI">
  </a>
  <a href="https://pepy.tech/project/dfly">
    <img src="https://static.pepy.tech/personalized-badge/dfly?period=total&units=international_system&left_color=grey&right_color=blue&left_text=downloads"
         alt="Downloads" />
  <a/>
  <br/>
  <a href="https://github.com/P403n1x87/dragonfly/blob/main/LICENSE.md">
    <img src="https://img.shields.io/badge/license-GPLv3-ff69b4.svg"
         alt="LICENSE">
  </a>
</p>

<p align="center">
  <a href="#synopsis"><b>Synopsis</b></a>&nbsp;&bull;
  <a href="#installation"><b>Installation</b></a>&nbsp;&bull;
  <a href="#usage"><b>Usage</b></a>&nbsp;&bull;
  <a href="#compatibility"><b>Compatibility</b></a>&nbsp;&bull;
  <a href="#documentation"><b>Documentation</b></a>&nbsp;&bull;
  <a href="#contribute"><b>Contribute</b></a>&nbsp;&bull;
  <a href="#credits"><b>Credits</b></a>
</p>

<p align="center">
  <a href="https://www.buymeacoffee.com/Q9C1Hnm28" target="_blank">
    <img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" />
  </a>
</p>


# Synopsis

Dragonfly is a lightweight CPython debugger designed with speed in mind.
Contrary to more traditional debuggers, like pdb, Dragonfly does not rely
heavily on tracing, allowing the target application to run at full speed in most
cases. Occasionally, tracing might be required, so that the slowdown would be
similar to that of pdb in the worst case.


# Installation

This package can be installed from PyPI with

~~~ bash
pip install --user dfly --upgrade
~~~


# Usage

To debug a Python script or application, simply prefix the command with `dfly`.
The built-in `breakpoint()` is replaced with Dragonfly's own implementation, so
that you can set breakpoints in your code by simply adding `breakpoint()` where
needed. Alternatively, if you are not using the `dfly` command, you can simply
import `dragonfly.bite` before any calls to `breakpoint` to achieve the same
effect.

Dragonfly is still in an early stage of development, so it is not yet feature
complete. However, it is already usable for the most common debugging tasks,
with some initial support for multi-threading.

If you find this tool useful, please consider starring the repository and/or
becoming a [Sponsor][sponsor] to support the development.


# Compatibility

Dragonfly is tested on Linux and macOS with Python 3.8-3.12.


# Why Dragonfly

The typical CPython debugger relies heavily, or even exclusively on tracing in
their implementation. This technique is very powerful, but it has a few
shortcomings:

- high overhead - tracing is slow, and it can slow down the target application
  by a factor of 10 or more.

- limited support for multithreading - supporting multithreading in a
  tracing-based debugger is difficult, especially in older versions of Python.

Some of these problems have been addressed in [PEP 669][pep-0669]. But whilst
the cost of monitoring has been lowered, some impact still remains. Besides,
PEP 669 is only available in Python 3.12 and later.

Dragonfly poses itself as a lightweight alternative to the traditional, and the
PEP 669-based debuggers. At its core, Dragonfly uses bytecode transformation to
implement traps. These can be injected where breakpoints are requested, and
control is then passed to the prompt. When the targeted bytecode is already
being executed, Dragonfly turns on tracing to ensure that any breakpoints can
still be hit. In this case, the performance impact can be similar to that of
tracing-based debuggers. However, this should normally be a transient situation,
and the ammortised cost of debugging should be essentially negligible.

To make this clearer, let's look at a simple example. Consider the following
code:

```python
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


from time import monotonic as time

start = time()
fibonacci(30)
end = time()
print(end - start)
```

When we run this without any debuggers, the reported time is of the order of
0.1 seconds.

```console
$ python3.12 -m tests.fib
0.11031840229406953
```

If we run this with pdb, without any breakpoints, the reported time is of the
order of over 3 seconds:

```console
$ python3.12 -m pdb -m tests.fib
> /tmp/fib.py(1)<module>()
-> def fibonacci(n):
(Pdb) r
3.2781156906858087
--Return--
> /tmp/fib.py(12)<module>()->None
-> print(end - start)
(Pdb) 
```

However, if we run it through Dragonfly, again without any breakpoints set, the
reported time is essentially the same as without any debugger:

```console
$ dfly -r python -m fib         
0.11001458810642362
```

## Bytecode debugging

Dragonfly can also be used to debug CPython at the bytecode level. When setting
`trace-opcodes` with `set trace-opcodes 1`, every stepping operation will be
performed at the bytecode level. The `disassemble` command can be used to
display the bytecode currently running, along with the values in the stack for
the current frame.


# Contribute

If you want to help with the development, then have a look at the open issues
and have a look at the [contributing guidelines](CONTRIBUTING.md) before you
open a pull request.

You can also contribute to the development by either [becoming a
Patron](https://www.patreon.com/bePatron?u=19221563) on Patreon, by [buying me a
coffee](https://www.buymeacoffee.com/Q9C1Hnm28) on BMC or by chipping in a few
pennies on [PayPal.Me](https://www.paypal.me/gtornetta/1).

<p align="center">
  <a href="https://www.buymeacoffee.com/Q9C1Hnm28" target="_blank">
    <img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png"
         alt="Buy Me A Coffee" />
  </a>
</p>


## Credits

Artwork by [Antea a.k.a. Aisling][aisling].


[aisling]: https://linktr.ee/ladyofshalott
[pep-0669]: https://peps.python.org/pep-0669/
[sponsor]: https://www.github.com/sponsors/P403n1x87
