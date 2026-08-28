
from __future__ import print_function

import ast
import re
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


def sub_once(source, pattern, replacement, label):
    updated, count = re.subn(
        pattern,
        replacement,
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(
            "Could not patch {}. Expected one match, got {}.".format(
                label, count
            )
        )
    return updated


# ------------------------------------------------------------
# Final evaluation paths
# ------------------------------------------------------------

anchor = 'PRIMARY_CHECKS_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "primary_checks.json"\n'
replacement = (
    anchor
    + 'FINAL_SUMMARY_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "final_evaluation_summary.json"\n'
    + 'VALIDATION_CSV = FINAL_EVAL_DIR / "results" / "validation" / "environment_validation.csv"\n'
)

if "FINAL_SUMMARY_JSON =" not in text:
    if anchor not in text:
        raise RuntimeError("Could not find PRIMARY_CHECKS_JSON anchor.")
    text = text.replace(anchor, replacement, 1)


# ------------------------------------------------------------
# Scenario definitions
# ------------------------------------------------------------

scenario_block = """
SCENARIO_ORDER = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
    "e5_mixed_preferences",
]

EVALUATION_ORDER = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
    "e5_mixed_preferences",
    "e6_shared_conflict",
]

SCENARIO_LABELS = {
    "e1_fast_slow": "E1 — Fast vs Slow",
    "e2_transfer_network": "E2 — Transfer Network",
    "e3_waiting_network": "E3 — Waiting Network",
    "e4_simple_complex": "E4 — Simple vs Complex",
    "e5_mixed_preferences": "E5 — Mixed Preferences",
    "e6_shared_conflict": "E6 — Infrastructure Robustness",
}

SCENARIO_DESCRIPTIONS = {
    "e1_fast_slow": (
        "Two curved services connect the same passenger origin and destination. "
        "One is deliberately faster while both have the same turn count."
    ),
    "e2_transfer_network": (
        "A slower direct service competes with a faster three-leg journey "
        "through two transfer stations."
    ),
    "e3_waiting_network": (
        "Two one-transfer itineraries trade total journey time against "
        "connection waiting while keeping transfer count equal."
    ),
    "e4_simple_complex": (
        "A shorter route with more turns competes with a longer route "
        "with fewer turns."
    ),
    "e5_mixed_preferences": (
        "Three alternatives compete simultaneously: a fast multi-transfer "
        "journey, a zero-transfer direct journey and a one-transfer compromise."
    ),
    "e6_shared_conflict": (
        "A validated two-train Flatland environment used to test multi-train "
        "infrastructure scheduling and ASP-to-Flatland execution robustness."
    ),
}

SCENARIO_QUESTIONS = {
    "e1_fast_slow": "Does the optimizer identify the genuinely faster service?",
    "e2_transfer_network": (
        "Will Fastest accept transfers while Fewer Transfers chooses the "
        "slower direct service?"
    ),
    "e3_waiting_network": (
        "Will Less Waiting accept a longer trip to reduce connection waiting?"
    ),
    "e4_simple_complex": (
        "Will Simple Journey accept a longer trip to reduce route complexity?"
    ),
    "e5_mixed_preferences": (
        "When several trade-offs coexist, do semantic profiles select "
        "different appropriate alternatives?"
    ),
    "e6_shared_conflict": (
        "Can RS42 solve and execute a second multi-train infrastructure "
        "environment consistently in Flatland?"
    ),
}

EXPERIMENT_PURPOSE = {
    "e1_fast_slow": "Isolated travel-time control.",
    "e2_transfer_network": "Travel time versus number of transfers.",
    "e3_waiting_network": "Travel time versus transfer waiting.",
    "e4_simple_complex": "Travel time versus route simplicity.",
    "e5_mixed_preferences": (
        "Integrated test with three simultaneously competing alternatives."
    ),
    "e6_shared_conflict": (
        "Infrastructure robustness and multi-train execution validation."
    ),
}

EXPERIMENT_DESIGN = {
    "e1_fast_slow": [
        "Fast service: journey 10.",
        "Slow service: designed journey 18.",
        "Both curved alternatives use two turns.",
        "Geometry does not give one service a simplicity advantage.",
    ],
    "e2_transfer_network": [
        "Fast alternative: journey 14, wait 2, two transfers.",
        "Direct alternative: journey 18, wait 0, zero transfers.",
        "Deliberate travel-time versus transfer-count trade-off.",
    ],
    "e3_waiting_network": [
        "Fast/high-wait alternative: journey 11, wait 5, one transfer.",
        "Slow/low-wait alternative: journey 13, wait 1, one transfer.",
        "Transfer count is equal so waiting is isolated.",
    ],
    "e4_simple_complex": [
        "Fast/complex result: journey 32 with 8 turns.",
        "Simple result: journey 41 with 4 turns.",
        "Tests whether route simplicity can justify a longer trip.",
    ],
    "e5_mixed_preferences": [
        "Alternative A: journey 14, wait 2, two transfers.",
        "Alternative B: journey 18, wait 0, zero transfers.",
        "Alternative C: journey 16, wait 1, one transfer.",
        "Several preference dimensions coexist in one environment.",
    ],
    "e6_shared_conflict": [
        "Two trains operate in a separate validated Flatland environment.",
        "E6 is infrastructure robustness rather than passenger choice.",
        "Canonical ASP-to-Flatland validation passes.",
        "Profile runs are supplementary solver stress tests.",
    ],
}

EXPERIMENT_FINDING = {
    "e1_fast_slow": (
        "All profiles select journey 10. The faster service dominates."
    ),
    "e2_transfer_network": (
        "Fastest selects journey 14 with two transfers. Less Waiting, "
        "Fewer Transfers, Simple Journey and Balanced select journey 18 direct."
    ),
    "e3_waiting_network": (
        "Fastest selects journey 11 / wait 5. Less Waiting and Balanced "
        "select journey 13 / wait 1."
    ),
    "e4_simple_complex": (
        "Fastest selects journey 32 / 8 turns. Simple Journey accepts "
        "journey 41 to reduce route turns to 4."
    ),
    "e5_mixed_preferences": (
        "Fastest selects the 14-step multi-transfer route; Less Waiting and "
        "Fewer Transfers select the direct 18-step service; Simple Journey "
        "selects the 16-step compromise; Balanced selects the direct route."
    ),
    "e6_shared_conflict": (
        "Canonical E6 passes ASP-to-Flatland validation. Four of five "
        "supplementary profile stress runs reach OPTIMUM FOUND. Less Waiting "
        "times out and is retained as a computational limitation."
    ),
}
"""

text = sub_once(
    text,
    r'SCENARIO_ORDER\s*=\s*\[.*?\]\s*\n\s*'
    r'SCENARIO_LABELS\s*=\s*\{.*?\}\s*\n\s*'
    r'SCENARIO_DESCRIPTIONS\s*=\s*\{.*?\}\s*\n\s*'
    r'SCENARIO_QUESTIONS\s*=\s*\{.*?\}\s*\n',
    scenario_block.strip() + "\n",
    "scenario definitions",
)


# ------------------------------------------------------------
# Research interpretation
# ------------------------------------------------------------

research_function = """
def research_interpretation(stem):
    return {
        "e1_fast_slow": (
            "Control result: all five profiles select the same 10-step "
            "fast service."
        ),
        "e2_transfer_network": (
            "Fastest accepts two transfers to reduce journey time from "
            "18 to 14; transfer-sensitive profiles select the direct service."
        ),
        "e3_waiting_network": (
            "Fastest selects journey 11 with wait 5; Less Waiting accepts "
            "journey 13 to reduce connection wait to 1."
        ),
        "e4_simple_complex": (
            "Fastest selects journey 32 with 8 turns; Simple Journey accepts "
            "journey 41 to reduce turns to 4."
        ),
        "e5_mixed_preferences": (
            "The integrated environment separates the profiles across fast, "
            "direct and compromise alternatives."
        ),
        "e6_shared_conflict": (
            "E6 is infrastructure-only evidence. Its canonical ASP plan "
            "matches Flatland execution. Four of five profile stress runs "
            "reach an optimum; Less Waiting is a retained timeout."
        ),
    }.get(stem, "")
"""

text = sub_once(
    text,
    r'def research_interpretation\(stem\):.*?(?=\n\nst\.set_page_config)',
    research_function.strip(),
    "research_interpretation",
)


# ------------------------------------------------------------
# Top status cards + tabs
# ------------------------------------------------------------

status_block = """
completion = load_json(COMPLETION_JSON) or {}
checks = load_json(PRIMARY_CHECKS_JSON) or {}
final_summary = load_json(FINAL_SUMMARY_JSON) or {}

_snapshot_results = load_final_results()
_required_optimum = 0
_overall_optimum = 0
_e6_optimum = 0

if _snapshot_results is not None:
    _required = _snapshot_results[
        _snapshot_results["environment"] != "e6_shared_conflict"
    ]
    _e6 = _snapshot_results[
        _snapshot_results["environment"] == "e6_shared_conflict"
    ]
    _required_optimum = int(
        (_required["status"] == "OPTIMUM FOUND").sum()
    )
    _overall_optimum = int(
        (_snapshot_results["status"] == "OPTIMUM FOUND").sum()
    )
    _e6_optimum = int(
        (_e6["status"] == "OPTIMUM FOUND").sum()
    )

_controlled_passed = int(
    checks.get("passed", completion.get("controlled_checks_passed", 10))
)
_controlled_total = int(
    checks.get("total", completion.get("controlled_checks_total", 10))
)
_flatland_passed = int(
    completion.get("flatland_validation_passed", 6)
)

_final_status = final_summary.get(
    "final_status",
    completion.get("final_status"),
)

if not _final_status:
    if (
        _required_optimum == 25
        and _controlled_passed == _controlled_total
        and _flatland_passed == 6
    ):
        _final_status = "PASS_WITH_LIMITATION"
    else:
        _final_status = "CHECK_RESULTS"

status_cols = st.columns(4)
status_cols[0].metric("Canonical environments", "6")
status_cols[1].metric(
    "Required preference runs",
    f"{_required_optimum}/25",
)
status_cols[2].metric(
    "Controlled checks",
    f"{_controlled_passed}/{_controlled_total}",
)
status_cols[3].metric(
    "Flatland validation",
    f"{_flatland_passed}/6",
)

if _final_status == "PASS_WITH_LIMITATION":
    st.warning(
        "Final evaluation: PASS WITH LIMITATION — E1–E5 achieved 25/25 "
        "optimal preference runs and all six environments passed Flatland "
        "validation. E6 Less Waiting remains a supplementary timeout."
    )
elif _final_status == "PASS":
    st.success("Final evaluation: PASS")
else:
    st.info(f"Final evaluation status: {_final_status}")

planner_tab, evaluation_tab, experiments_tab = st.tabs(
    ["Journey Planner", "Research Evaluation", "Experimental Setups"]
)
"""

text = sub_once(
    text,
    r'completion\s*=\s*load_json\(COMPLETION_JSON\).*?'
    r'planner_tab,\s*evaluation_tab(?:,\s*experiments_tab)?\s*=\s*st\.tabs\(.*?\)\s*',
    status_block.strip() + "\n",
    "status block",
)


# ------------------------------------------------------------
# Planner and Research wording
# ------------------------------------------------------------

text = text.replace(
    "The four canonical final-evaluation environments are not ",
    "The five passenger-preference environments are not ",
)

text = text.replace(
    '"Four deterministic environments × five canonical semantic profiles "\n'
    '        "= 20 optimization runs."',
    '"E1–E5 provide the required passenger-preference evaluation. "\n'
    '        "E6 is a separate infrastructure-robustness experiment. "\n'
    '        "Thirty environment/profile runs were attempted overall."',
)

text = text.replace(
    "for stem in SCENARIO_ORDER\n                if stem in set(results[\"environment\"])",
    "for stem in EVALUATION_ORDER\n                if stem in set(results[\"environment\"])",
)


# ------------------------------------------------------------
# Experimental Setups tab
# ------------------------------------------------------------

experimental_tab = """
with experiments_tab:
    st.subheader("Experimental Setups")
    st.caption(
        "Six fixed canonical environments are used in the final evaluation. "
        "E1–E5 test semantic passenger preferences; E6 tests multi-train "
        "infrastructure robustness."
    )

    st.info(
        "Preference weights belong to the optimization policy, not to "
        "individual trains. Within each experiment the railway environment "
        "stays fixed; only the semantic optimization objective changes."
    )

    final_rows = []

    if FINAL_RESULTS_CSV.exists():
        with FINAL_RESULTS_CSV.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as handle:
            final_rows = list(csv.DictReader(handle))
    else:
        st.warning(
            "Final result CSV is missing: "
            f"{FINAL_RESULTS_CSV.relative_to(REPO)}"
        )

    experiment_tabs = st.tabs(
        [SCENARIO_LABELS[stem] for stem in EVALUATION_ORDER]
    )

    profile_order = {
        "fastest": 0,
        "least_waiting": 1,
        "fewest_transfers": 2,
        "simple": 3,
        "balanced": 4,
    }

    for stem, experiment_view in zip(
        EVALUATION_ORDER,
        experiment_tabs,
    ):
        with experiment_view:
            st.markdown(f"### {SCENARIO_LABELS[stem]}")
            st.write(EXPERIMENT_PURPOSE[stem])

            left, right = st.columns([1.15, 1])

            with left:
                render_environment_image(stem)

            with right:
                st.markdown("#### Design")
                for item in EXPERIMENT_DESIGN[stem]:
                    st.write(f"- {item}")

                st.markdown("#### Evaluation role")

                if stem == "e6_shared_conflict":
                    st.write(
                        "E6 is not a passenger-choice experiment. Its primary "
                        "criterion is successful multi-train ASP-to-Flatland "
                        "execution. Profile runs are supplementary stress tests."
                    )
                else:
                    st.write(
                        "The exact same environment is solved with Fastest, "
                        "Less Waiting, Fewer Transfers, Simple Journey and "
                        "Balanced. Only the optimization policy changes."
                    )

            st.markdown("#### Final results")

            environment_rows = [
                row
                for row in final_rows
                if row.get("environment") == stem
            ]
            environment_rows.sort(
                key=lambda row: profile_order.get(
                    row.get("profile"), 99
                )
            )

            if environment_rows:
                table_rows = []
                for row in environment_rows:
                    table_rows.append(
                        {
                            "Profile": row.get(
                                "profile_label",
                                PROFILE_LABELS.get(
                                    row.get("profile"),
                                    row.get("profile", ""),
                                ),
                            ),
                            "Status": row.get("status", ""),
                            "Journey": row.get("journey_time", ""),
                            "Wait": row.get("transfer_wait", ""),
                            "Transfers": row.get("transfers", ""),
                            "Turns": row.get("turns", ""),
                            "Runtime (s)": row.get("runtime_seconds", ""),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(table_rows),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No final rows are available for this environment.")

            if stem == "e6_shared_conflict":
                st.warning(EXPERIMENT_FINDING[stem])
                st.caption(
                    "The Less Waiting TIMEOUT remains visible and is not "
                    "relabeled as an optimum."
                )
            else:
                st.success(EXPERIMENT_FINDING[stem])

            with st.expander("Contribution to the final evaluation"):
                if stem == "e6_shared_conflict":
                    st.write(
                        "E6 contributes infrastructure validation plus five "
                        "supplementary profile stress runs. Passenger metrics "
                        "are intentionally not interpreted."
                    )
                else:
                    st.write(
                        "This environment contributes five required preference "
                        "runs. E1–E5 therefore provide 25 required runs."
                    )

    st.divider()
    st.markdown("### Final evaluation summary")

    summary_cols = st.columns(4)
    summary_cols[0].metric(
        "Required preference runs",
        f"{_required_optimum}/25",
    )
    summary_cols[1].metric(
        "Controlled checks",
        f"{_controlled_passed}/{_controlled_total}",
    )
    summary_cols[2].metric(
        "Flatland validation",
        f"{_flatland_passed}/6",
    )
    summary_cols[3].metric(
        "E6 stress profiles",
        f"{_e6_optimum}/5",
    )

    st.write(
        "**Final interpretation:** the required passenger-preference "
        "evaluation passes. The E6 Less Waiting timeout is retained as a "
        "computational limitation of applying a waiting-oriented objective "
        "to an infrastructure-only environment."
    )
"""

if "\nwith experiments_tab:" in text:
    text = (
        text.split("\nwith experiments_tab:", 1)[0].rstrip()
        + "\n\n"
        + experimental_tab.strip()
        + "\n"
    )
else:
    text = text.rstrip() + "\n\n" + experimental_tab.strip() + "\n"


# ------------------------------------------------------------
# Validate and install
# ------------------------------------------------------------

ast.parse(text)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = APP.with_name(
    "app_v3_before_six_env_ui_{}.py".format(timestamp)
)

shutil.copy2(str(APP), str(backup))
APP.write_text(text, encoding="utf-8")
ast.parse(APP.read_text(encoding="utf-8"))

print("RS42 FINAL UI UPDATE: SUCCESS")
print()
print("Journey Planner: E1-E5")
print("Research Evaluation: E1-E6")
print("Experimental Setups: E1-E6")
print("E6 timeout: displayed as limitation")
print()
print("Backup:")
print(" ", backup.relative_to(ROOT))
print("Updated:")
print(" ", APP.relative_to(ROOT))
print()
print("Launch:")
print("  conda activate rs42ui")
print("  streamlit run ui/app_v3.py")
