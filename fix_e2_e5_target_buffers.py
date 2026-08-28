
from pathlib import Path

ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this from the RS42 repository root.")

files = [
    ROOT / "tools" / "final_evaluation" / "build_e2_transfer_network.py",
    ROOT / "tools" / "final_evaluation" / "build_e5_mixed_preferences.py",
]

for path in files:
    if not path.exists():
        raise SystemExit("Missing: {}".format(path))

    text = path.read_text(encoding="utf-8")

    replacements = [
        (
            """T1_PATH = manhattan_path([
    (9, 0),
    (9, 3),
    (11, 3),
    (11, 5),
    (10, 5),
])""",
            """T1_PATH = manhattan_path([
    (9, 0),
    (9, 3),
    (11, 3),
    (11, 5),
    (10, 5),
    (9, 5),
])"""
        ),
        (
            """T2_PATH = manhattan_path([
    (9, 7),
    (9, 10),
    (11, 10),
    (11, 12),
    (10, 12),
])""",
            """T2_PATH = manhattan_path([
    (9, 7),
    (9, 10),
    (11, 10),
    (11, 12),
    (10, 12),
    (9, 12),
])"""
        ),
        (
            """T3_PATH = manhattan_path([
    (9, 14),
    (9, 17),
    (11, 17),
    (11, 19),
    (10, 19),
])""",
            """T3_PATH = manhattan_path([
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
            "ERROR: {}: expected to patch 3 fast paths, patched {}. "
            "Send the current builder instead of editing manually."
            .format(path.name, changed)
        )

    compile(text, str(path), "exec")
    path.write_text(text, encoding="utf-8")

    print("PATCHED:", path.relative_to(ROOT))

print()
print("Fast-route target buffers added.")
print("Movement distances to targets are unchanged.")
print()
print("Now run:")
print(r"  python tools\final_evaluation\build_e2_transfer_network.py --overwrite")
print(r"  python tools\final_evaluation\build_e5_mixed_preferences.py --overwrite")
