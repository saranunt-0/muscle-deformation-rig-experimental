"""Run a script body and hard-exit.

The pip ``bpy`` module (and sometimes ``blender -b``) can hang during
interpreter shutdown, especially after an exception. ``run`` prints any
traceback, flushes, and leaves with ``os._exit`` so CI never stalls.
"""

import os
import sys
import traceback


def run(main):
    code = 0
    try:
        result = main()
        if isinstance(result, int):
            code = result
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
