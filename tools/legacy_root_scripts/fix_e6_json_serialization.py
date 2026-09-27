from pathlib import Path

ROOT = Path.cwd().resolve()
TARGET = ROOT / "tools" / "final_evaluation" / "build_e6_shared_conflict.py"

if not TARGET.exists():
    raise SystemExit("ERROR: build_e6_shared_conflict.py not found. Run from rs42 root.")

text = TARGET.read_text(encoding="utf-8")

marker = "\ndef inspect_source_pickle():\n"

helper = '''
def json_safe(value):
    """Convert NumPy/Flatland values to normal JSON-safe Python types."""
    if value is None:
        return None

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(json_safe(key)): json_safe(val)
            for key, val in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass

    return value

'''

if "def json_safe(value):" not in text:
    if marker not in text:
        raise SystemExit("ERROR: inspect_source_pickle() not found in current builder.")
    text = text.replace(marker, "\n" + helper + marker, 1)

text = text.replace(
    'list(agent.initial_position)',
    'json_safe(agent.initial_position)'
)

text = text.replace(
    'list(agent.target)',
    'json_safe(agent.target)'
)

text = text.replace(
    '''"earliest_departure": getattr(
                    agent,
                    "earliest_departure",
                    None,
                ),''',
    '''"earliest_departure": json_safe(
                    getattr(
                        agent,
                        "earliest_departure",
                        None,
                    )
                ),'''
)

text = text.replace(
    '''"latest_arrival": getattr(
                    agent,
                    "latest_arrival",
                    None,
                ),''',
    '''"latest_arrival": json_safe(
                    getattr(
                        agent,
                        "latest_arrival",
                        None,
                    )
                ),'''
)

text = text.replace(
    'json.dumps(metadata, indent=2) + "\\n"',
    'json.dumps(json_safe(metadata), indent=2) + "\\n"'
)

compile(text, str(TARGET), "exec")
TARGET.write_text(text, encoding="utf-8")

print("PATCHED:", TARGET.relative_to(ROOT))
print("JSON serialization fix: INSTALLED")
print()
print(r"Now run:")
print(r"  python tools\final_evaluation\build_e6_shared_conflict.py --overwrite")
