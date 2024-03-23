import os

from dragonfly._debugger import Debugger

debugger = Debugger()

# Replace the built-in breakpoint() function with our own.
__builtins__["breakpoint"] = debugger.interrupt

if os.environ.get("DRAGONFLY_RUN", "0") == "0":
    debugger.interrupt()
else:
    debugger.run()
