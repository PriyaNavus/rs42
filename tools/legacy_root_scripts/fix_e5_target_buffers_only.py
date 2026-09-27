
from pathlib import Path

ROOT = Path.cwd().resolve()
E5 = ROOT / "tools" / "final_evaluation" / "build_e5_mixed_preferences.py"

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this from the RS42 repository root.")

if not E5.exists():
    raise SystemExit("ERROR: build_e5_mixed_preferences.py not found.")

text = E5.read_text(encoding="utf-8")

replacements = [
    (
        """FAST1 = manhattan_path([
    (9, 0),
    (9, 3),
    (11, 3),
    (11, 5),
    (10, 5),
])""",
        """FAST1 = manhattan_path([
    (9, 0),
    (9, 3),
    (11, 3),
    (11, 5),
    (10, 5),
    (9, 5),
])"""
    ),
    (
        """FAST2 = manhattan_path([
    (9, 7),
    (9, 10),
    (11, 10),
    (11, 12),
    (10, 12),
])""",
        """FAST2 = manhattan_path([
    (9, 7),
    (9, 10),
    (11, 10),
    (11, 12),
    (10, 12),
    (9, 12),
])"""
    ),
    (
        """FAST3 = manhattan_path([
    (9, 14),
    (9, 17),
    (11, 17),
    (11, 19),
    (10, 19),
])""",
        """FAST3 = manhattan_path([
    (9, 14),
    (9, 17),
    (11, 17),
    (11, 19),
    (10, 19),
    (9, 19),
])"""
    ),
]

changed = 0

for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)
        changed += 1

if changed != 3:
    raise SystemExit(
        "ERROR: Expected to patch 3 E5 fast paths, patched {}.".format(changed)
    )

compile(text, str(E5), "exec")
E5.write_text(text, encoding="utf-8")

print("E5 TARGET BUFFER FIX: SUCCESS")
print()
print("Added one rail cell after:")
print("  FAST1 target (10,5)")
print("  FAST2 target (10,12)")
print("  FAST3 target (10,19)")
print()
print("Movement lengths to the targets stay unchanged.")
print()
print("Now run:")
print(r"  python tools\final_evaluation\build_e5_mixed_preferences.py --overwrite")
