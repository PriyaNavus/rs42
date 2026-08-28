from pathlib import Path

ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this installer from the RS42 repository root.")

SOURCE = Path(__file__).resolve().with_name("retry_e6_timeouts.py")
TARGET = ROOT / "tools" / "final_evaluation" / "retry_e6_timeouts.py"

if not SOURCE.exists():
    raise SystemExit("ERROR: retry_e6_timeouts.py must be beside this installer.")

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")

print("Installed:", TARGET.relative_to(ROOT))
print()
print(r"Run: python tools\final_evaluation\retry_e6_timeouts.py")
