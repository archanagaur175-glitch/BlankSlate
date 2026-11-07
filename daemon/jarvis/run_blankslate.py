"""Frozen entry point for the BlankSlate daemon (vendored jarvis fork).

Kept as a flat script (not a package __main__) so PyInstaller can resolve the
absolute ``jarvis.main`` import without package-context ambiguity.
"""

import os
import sys

# The frozen (windowed) executable inherits a non-UTF-8 stdout/stderr codepage
# (e.g. cp1252), which cannot encode the daemon's Unicode status glyphs (✓, 🤖).
# Force UTF-8 before any jarvis code prints.
os.environ.setdefault("PYTHONUTF8", "1")
for _s in (sys.stdout, sys.stderr):
    if _s is not None:
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis.main import main

if __name__ == "__main__":
    main()
