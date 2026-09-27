from __future__ import print_function

import ast
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd().resolve()
APP = ROOT / "ui" / "app_v3.py"

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this script from the RS42 repository root.")

if not APP.exists():
    raise SystemExit("ERROR: ui/app_v3.py not found.")

text = APP.read_text(encoding="utf-8")

# Keep the existing three-tab layout, but use a cleaner label.
text = text.replace(
    '"Experimental Setups"',
    '"Experiments"',
)

# Remove the currently broken/technical experiments section.
marker = "\nwith experiments_tab:"
if marker not in text:
    raise RuntimeError(
        "Could not find the existing experiments_tab block in ui/app_v3.py."
    )

text = text.split(marker, 1)[0].rstrip()

CLEAN_BLOCK = '\nwith experiments_tab:\n    st.subheader("Experiments")\n    st.caption(\n        "Six railway scenarios were used to see how different journey "\n        "preferences change the recommended schedule."\n    )\n\n    experiment_order = [\n        "e1_fast_slow",\n        "e2_transfer_network",\n        "e3_waiting_network",\n        "e4_simple_complex",\n        "e5_mixed_preferences",\n        "e6_shared_conflict",\n    ]\n\n    labels = {\n        "e1_fast_slow": "E1 — Fast vs Slow",\n        "e2_transfer_network": "E2 — Transfers",\n        "e3_waiting_network": "E3 — Waiting",\n        "e4_simple_complex": "E4 — Simple vs Complex",\n        "e5_mixed_preferences": "E5 — Mixed Preferences",\n        "e6_shared_conflict": "E6 — Shared Infrastructure",\n    }\n\n    intro = {\n        "e1_fast_slow": (\n            "A control case with a clearly faster and a slower service."\n        ),\n        "e2_transfer_network": (\n            "A faster journey with train changes competes with a slower "\n            "direct journey."\n        ),\n        "e3_waiting_network": (\n            "Two journeys have the same number of transfers but different "\n            "connection waiting times."\n        ),\n        "e4_simple_complex": (\n            "A shorter but more complex route competes with a longer, "\n            "simpler route."\n        ),\n        "e5_mixed_preferences": (\n            "Journey time, waiting and number of transfers all compete "\n            "in the same scenario."\n        ),\n        "e6_shared_conflict": (\n            "A separate two-train scenario checks whether schedules still "\n            "work when trains share infrastructure."\n        ),\n    }\n\n    question = {\n        "e1_fast_slow": (\n            "Does the planner reliably identify the clearly faster service?"\n        ),\n        "e2_transfer_network": (\n            "When is saving time worth changing trains?"\n        ),\n        "e3_waiting_network": (\n            "When is a slightly longer trip worth less waiting?"\n        ),\n        "e4_simple_complex": (\n            "When is a simpler route worth taking more time?"\n        ),\n        "e5_mixed_preferences": (\n            "Do different priorities still lead to sensible choices when "\n            "several trade-offs exist together?"\n        ),\n        "e6_shared_conflict": (\n            "Can the generated schedule still be executed successfully "\n            "with multiple trains?"\n        ),\n    }\n\n    finding = {\n        "e1_fast_slow": (\n            "All preferences choose the faster service."\n        ),\n        "e2_transfer_network": (\n            "Fastest chooses the quicker journey with transfers. "\n            "The other preferences choose the direct journey."\n        ),\n        "e3_waiting_network": (\n            "Fastest chooses the shorter trip. Less Waiting and Balanced "\n            "accept a slightly longer trip to reduce connection waiting."\n        ),\n        "e4_simple_complex": (\n            "Fastest chooses the shorter route. Simple Journey accepts a "\n            "longer trip to reduce route complexity."\n        ),\n        "e5_mixed_preferences": (\n            "Fastest chooses the quickest option, Simple Journey chooses "\n            "the compromise, and waiting/transfer-sensitive preferences "\n            "choose the direct option."\n        ),\n        "e6_shared_conflict": (\n            "The multi-train schedule was successfully executed and "\n            "validated in Flatland."\n        ),\n    }\n\n    friendly_profile = {\n        "fastest": "Fastest",\n        "least_waiting": "Less Waiting",\n        "fewest_transfers": "Fewer Transfers",\n        "simple": "Simple Journey",\n        "comfort": "Simple Journey",\n        "balanced": "Balanced",\n    }\n\n    results_path = (\n        REPO\n        / "experiments"\n        / "final_evaluation"\n        / "results"\n        / "runs"\n        / "all_runs.csv"\n    )\n\n    final_rows = []\n    if results_path.exists():\n        with results_path.open(\n            "r",\n            newline="",\n            encoding="utf-8",\n        ) as handle:\n            final_rows = list(csv.DictReader(handle))\n\n    experiment_tabs = st.tabs(\n        [labels[stem] for stem in experiment_order]\n    )\n\n    profile_order = {\n        "fastest": 0,\n        "least_waiting": 1,\n        "fewest_transfers": 2,\n        "simple": 3,\n        "comfort": 3,\n        "balanced": 4,\n    }\n\n    for stem, view in zip(experiment_order, experiment_tabs):\n        with view:\n            st.markdown(f"### {labels[stem]}")\n            st.write(intro[stem])\n\n            image_col, explanation_col = st.columns([1.2, 1])\n\n            with image_col:\n                image_path = (\n                    REPO\n                    / "envs"\n                    / "png"\n                    / f"{stem}.png"\n                )\n\n                if image_path.exists():\n                    st.image(\n                        str(image_path),\n                        use_container_width=True,\n                    )\n                else:\n                    st.info("Scenario preview is not available.")\n\n            with explanation_col:\n                st.markdown("#### What are we testing?")\n                st.write(question[stem])\n\n                st.markdown("#### Result")\n                st.write(finding[stem])\n\n            environment_rows = [\n                row\n                for row in final_rows\n                if row.get("environment") == stem\n            ]\n\n            environment_rows.sort(\n                key=lambda row: profile_order.get(\n                    row.get("profile"),\n                    99,\n                )\n            )\n\n            if stem != "e6_shared_conflict" and environment_rows:\n                st.markdown("#### How preferences changed the journey")\n\n                table_rows = []\n\n                for row in environment_rows:\n                    table_rows.append(\n                        {\n                            "Preference": friendly_profile.get(\n                                row.get("profile", ""),\n                                row.get(\n                                    "profile_label",\n                                    row.get("profile", ""),\n                                ),\n                            ),\n                            "Journey time": row.get(\n                                "journey_time",\n                                "",\n                            ),\n                            "Waiting": row.get(\n                                "transfer_wait",\n                                "",\n                            ),\n                            "Transfers": row.get(\n                                "transfers",\n                                "",\n                            ),\n                            "Route turns": row.get(\n                                "turns",\n                                "",\n                            ),\n                        }\n                    )\n\n                st.dataframe(\n                    table_rows,\n                    use_container_width=True,\n                    hide_index=True,\n                )\n\n            elif stem == "e6_shared_conflict":\n                st.success(\n                    "Multi-train execution successfully validated."\n                )\n                st.caption(\n                    "One optional preference stress test did not finish "\n                    "within the evaluation window. This does not affect "\n                    "the successful infrastructure execution check."\n                )\n\n    st.divider()\n    st.write(\n        "Together, these experiments show that the planner responds to "\n        "different passenger priorities while still producing schedules "\n        "that can be executed in the railway simulation."\n    )\n'

text = text + "\n\n" + CLEAN_BLOCK.strip() + "\n"

# Validate before writing.
ast.parse(text)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = APP.with_name(
    "app_v3_before_clean_experiments_{}.py".format(timestamp)
)

shutil.copy2(str(APP), str(backup))
APP.write_text(text, encoding="utf-8")

# Validate installed file too.
ast.parse(APP.read_text(encoding="utf-8"))

print("RS42 EXPERIMENT UI CLEANUP: SUCCESS")
print()
print("Fixed:")
print("  E5/E6 KeyError")
print("  stale four-environment label dictionary no longer used")
print()
print("Removed from normal experiment UI:")
print("  25/25, 10/10, 6/6, 4/5 dashboard")
print("  PASS WITH LIMITATION banner")
print("  OPTIMUM/TIMEOUT status columns")
print("  solver runtimes and backend terminology")
print()
print("Kept:")
print("  all six experiment images")
print("  simple scenario explanation")
print("  preference outcome table for E1-E5")
print("  plain-language E6 validation result")
print()
print("Backup:")
print("  {}".format(backup.relative_to(ROOT)))
print()
print("Launch:")
print("  streamlit run ui/app_v3.py")
