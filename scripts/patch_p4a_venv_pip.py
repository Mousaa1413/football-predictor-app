#!/usr/bin/env python3
"""Patch python-for-android to fix multi-arch pure-Python pip install.

Root cause (build_log):
  p4a run_pymodules_install() runs once per ABI and does:
      hostpython -m venv venv
      source venv/bin/activate && pip install -U pip

  After the first ABI succeeds, pip is upgraded (e.g. 24.0 -> 26.1.2).
  On the second ABI, `python -m venv venv` without --clear re-runs
  ensurepip --upgrade on the existing tree and mixes the bundled pip 24
  vendor files with leftover pip 26 files. The next `pip install -U pip`
  then crashes with:

      ImportError: cannot import name 'RequirementInformation'
        from 'pip._vendor.resolvelib.structs'

Fix:
  1) Always recreate the venv with --clear.
  2) Pin pip to a known-good version instead of floating latest.
"""
from __future__ import annotations

import sys
from pathlib import Path


VENV_OLD = "shprint(host_python, '-m', 'venv', 'venv')"
VENV_NEW = "shprint(host_python, '-m', 'venv', '--clear', 'venv')"

PIP_OLD = '"source venv/bin/activate && pip install -U pip"'
PIP_NEW = '"source venv/bin/activate && pip install -U \'pip==24.3.1\'"'


def patch(p4a_root: Path) -> None:
    target = p4a_root / "pythonforandroid" / "build.py"
    if not target.is_file():
        raise SystemExit(f"p4a build.py not found: {target}")

    text = target.read_text(encoding="utf-8")
    original = text

    if VENV_NEW in text and PIP_NEW in text:
        print(f"Already patched: {target}")
        return

    if VENV_OLD not in text and VENV_NEW not in text:
        raise SystemExit(
            f"Could not find venv creation line in {target}. "
            "Upstream p4a may have changed; update this script."
        )
    if PIP_OLD not in text and PIP_NEW not in text:
        raise SystemExit(
            f"Could not find pip upgrade line in {target}. "
            "Upstream p4a may have changed; update this script."
        )

    if VENV_OLD in text:
        text = text.replace(VENV_OLD, VENV_NEW, 1)
    if PIP_OLD in text:
        text = text.replace(PIP_OLD, PIP_NEW, 1)

    if text == original:
        raise SystemExit(f"No changes applied to {target}")

    target.write_text(text, encoding="utf-8")
    print(f"Patched: {target}")
    print("  - venv --clear")
    print("  - pin pip==24.3.1")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <python-for-android-root>", file=sys.stderr)
        return 2
    patch(Path(argv[1]).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
