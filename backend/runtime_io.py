"""Process-wide stdout/stderr hardening.

Many modules log progress with non-ASCII characters (arrows ->, >=, x, ...).
On Windows the default console encoding is cp1252, so a single such ``print``
raises ``UnicodeEncodeError`` and — because it happens inside request handling —
takes down the whole analysis with an opaque "Something went wrong".

Reconfiguring the streams to UTF-8 with ``errors="replace"`` makes logging
crash-proof everywhere at once, instead of chasing individual print statements.
Import this module (or call :func:`configure_utf8_output`) as early as possible.
"""

import sys


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Stream may be detached/redirected in a way that can't be reconfigured.
            pass


# Run on import so simply importing the module is enough to be safe.
configure_utf8_output()
