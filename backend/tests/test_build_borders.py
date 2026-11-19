"""The borders build script (scripts/build_us_borders.py): its simplification
keeps neighbouring states' shared borders identical, and it type-checks."""

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import build_us_borders as build

BACKEND = Path(__file__).resolve().parent.parent


def test_arc_simplification_is_the_same_in_both_directions():
    arc = [(0.0, 0.0), (1.0, 0.004), (2.0, -0.003), (3.0, 0.5), (4.0, 0.0)]
    forward = build.simplify_arc(arc, 0.01)
    backward = build.simplify_arc(arc[::-1], 0.01)
    assert forward == backward[::-1]
    assert (3.0, 0.5) in forward and (1.0, 0.004) not in forward


def test_shared_border_stays_identical_in_both_states():
    # Two squares sharing a wiggly border x=1 (walked in opposite directions).
    border = [(1.0, 0.0), (1.001, 0.25), (0.999, 0.5), (1.3, 0.75), (1.0, 1.0)]
    west = [(0.0, 0.0), *border, (0.0, 1.0), (0.0, 0.0)]
    east = [(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), *border[::-1][:-1], (1.0, 0.0)]
    a, b = build.simplify_rings([west, east], tol=0.01)
    assert a is not None and b is not None

    def edges(ring):
        return {tuple(sorted(e)) for e in zip(ring, ring[1:])}

    shared = edges(a) & edges(b)
    assert shared  # the common border survives in both
    assert (1.3, 0.75) in a and (1.3, 0.75) in b
    assert (1.001, 0.25) not in a and (1.001, 0.25) not in b


def test_script_passes_mypy():
    mypy = shutil.which("mypy") or str(BACKEND / ".venv" / "bin" / "mypy")
    if not Path(mypy).exists():
        pytest.skip("mypy not installed")
    result = subprocess.run([mypy, "scripts/build_us_borders.py"], cwd=BACKEND, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
