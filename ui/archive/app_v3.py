# RS42 frontend v3
# Run from repository root:
#   streamlit run ui/app_v3.py

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

REPO = Path(__file__).resolve().parents[1]
PROFILE_DIR = REPO / "asp" / "profiles"

BACKEND_CONDA_ENV = os.environ.get("RS42_BACKEND_ENV", "flatlandrs42")


def backend_python_cmd():
    """Run backend Python inside the validated RS42 Conda environment."""
    conda = shutil.which("conda")
    if conda:
        return [conda, "run", "-n", BACKEND_CONDA_ENV, "python"]

    explicit_python = os.environ.get("RS42_BACKEND_PYTHON")
    if explicit_python:
        return [explicit_python]

    return [sys.executable]

ACTIVE_PROFILE = PROFILE_DIR / "active_profile.lp"
SCENARIO_DIR = REPO / "asp" / "scenarios"

FINAL_EVAL_DIR = REPO / "experiments" / "final_evaluation"
FINAL_RESULTS_CSV = FINAL_EVAL_DIR / "results" / "runs" / "all_runs.csv"
FINAL_SUMMARY_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "final_evaluation_summary.json"
COMPLETION_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "completion_status.json"
PRIMARY_CHECKS_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "primary_checks.json"
VALIDATION_CSV = FINAL_EVAL_DIR / "results" / "validation" / "environment_validation.csv"

PASSENGER_ENVIRONMENTS = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
    "e5_mixed_preferences",
]

EVALUATION_ENVIRONMENTS = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
    "e5_mixed_preferences",
    "e6_shared_conflict",
]

EXPERIMENT_LABELS = {
    "e1_fast_slow": "E1 — Fast vs Slow",
    "e2_transfer_network": "E2 — Transfer Network",
    "e3_waiting_network": "E3 — Waiting Network",
    "e4_simple_complex": "E4 — Simple vs Complex",
    "e5_mixed_preferences": "E5 — Mixed Preferences",
    "e6_shared_conflict": "E6 — Infrastructure Robustness",
}

EXPERIMENT_PURPOSE = {
    "e1_fast_slow": "Isolated travel-time control using two curved alternatives.",
    "e2_transfer_network": "Tests journey time against number of passenger transfers.",
    "e3_waiting_network": "Tests journey time against transfer waiting while transfer count is held equal.",
    "e4_simple_complex": "Tests journey time against route simplicity / number of turns.",
    "e5_mixed_preferences": "Integrated scenario where time, waiting and transfers compete simultaneously.",
    "e6_shared_conflict": "Multi-train infrastructure robustness and ASP-to-Flatland execution validation.",
}

EXPERIMENT_DESIGN = {
    "e1_fast_slow": [
        "Fast service: journey 10.",
        "Slow service: designed journey 18.",
        "Both alternatives are curved and use two turns.",
        "Purpose: isolate travel time without a simplicity advantage.",
    ],
    "e2_transfer_network": [
        "Fast option: journey 14, wait 2, two transfers.",
        "Direct option: journey 18, wait 0, zero transfers.",
        "Purpose: expose a deliberate time-versus-transfer trade-off.",
    ],
    "e3_waiting_network": [
        "Fast/high-wait option: journey 11, wait 5, one transfer.",
        "Slow/low-wait option: journey 13, wait 1, one transfer.",
        "Transfer count is equal, isolating the waiting preference.",
    ],
    "e4_simple_complex": [
        "Fast/complex result: journey 32 with 8 turns.",
        "Simple result: journey 41 with 4 turns.",
        "Purpose: test whether simplicity can justify a longer journey.",
    ],
    "e5_mixed_preferences": [
        "Alternative A: journey 14, wait 2, two transfers.",
        "Alternative B: journey 18, wait 0, zero transfers.",
        "Alternative C: journey 16, wait 1, one transfer.",
        "Purpose: combine several preference dimensions in one environment.",
    ],
    "e6_shared_conflict": [
        "Separate validated two-train Flatland environment.",
        "Primary criterion: conflict-free ASP-to-Flatland execution.",
        "E6 is not interpreted as a passenger-choice experiment.",
        "Five profile runs are supplementary solver stress tests.",
    ],
}

EXPERIMENT_FINDING = {
    "e1_fast_slow": "All five profiles select journey 10; the fast service dominates.",
    "e2_transfer_network": (
        "Fastest selects journey 14 with two transfers. Less Waiting, "
        "Fewer Transfers, Simple Journey and Balanced select the direct journey 18."
    ),
    "e3_waiting_network": (
        "Fastest selects journey 11 / wait 5. Less Waiting and Balanced "
        "select journey 13 / wait 1."
    ),
    "e4_simple_complex": (
        "Fastest selects journey 32 / 8 turns. Simple Journey accepts "
        "journey 41 to reduce turns to 4."
    ),
    "e5_mixed_preferences": (
        "Fastest selects the 14-step multi-transfer route; Less Waiting and "
        "Fewer Transfers select the direct 18-step route; Simple Journey "
        "selects the 16-step compromise; Balanced selects direct."
    ),
    "e6_shared_conflict": (
        "Canonical ASP-to-Flatland validation passes. Four of five "
        "supplementary profile runs reach OPTIMUM FOUND. Less Waiting "
        "remains a reported timeout / computational limitation."
    ),
}

# Final controlled evaluation assets used only by the read-only
# Experimental Setups tab. The existing planner/evaluation logic is unchanged.
FINAL_RESULTS_CSV = (
    REPO
    / "experiments"
    / "final_evaluation"
    / "results"
    / "runs"
    / "all_runs.csv"
)

EXPERIMENT_ORDER = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
]

EXPERIMENT_LABELS = {
    "e1_fast_slow": "E1 — Fast vs Slow",
    "e2_transfer_network": "E2 — Transfer Network",
    "e3_waiting_network": "E3 — Waiting Network",
    "e4_simple_complex": "E4 — Simple vs Complex",
}

EXPERIMENT_PURPOSE = {
    "e1_fast_slow": (
        "Control environment: two services connect the same symbolic origin "
        "and destination. One service is physically/timetably faster."
    ),
    "e2_transfer_network": (
        "Tests journey time versus transfers: a faster three-train itinerary "
        "competes with a slower direct service."
    ),
    "e3_waiting_network": (
        "Tests journey time versus connection waiting while keeping transfer "
        "count equal at one transfer for both alternatives."
    ),
    "e4_simple_complex": (
        "Tests journey time versus route simplicity: a shorter route with "
        "more turns competes with a longer route with fewer turns."
    ),
}

EXPERIMENT_DESIGN = {
    "e1_fast_slow": [
        "Train 0: fast service, passenger journey time 10.",
        "Train 1: slower service, designed journey time 18.",
        "No meaningful waiting/transfer/turn trade-off is introduced.",
        "Purpose: baseline/control that the optimizer recognizes the dominant service.",
    ],
    "e2_transfer_network": [
        "Direct option: Train 0, journey 18, 0 transfers, 0 transfer wait.",
        "Fast option: Trains 1 → 2 → 3 through stations B and C.",
        "Fast option result: journey 14, 2 transfers, transfer wait 2.",
        "Purpose: show that Fastest can accept transfers while Fewer Transfers chooses direct.",
    ],
    "e3_waiting_network": [
        "Route A: one transfer, journey 11, transfer wait 5.",
        "Route B: one transfer, journey 13, transfer wait 1.",
        "Both alternatives have the same transfer count.",
        "Purpose: isolate waiting preference from transfer-count preference.",
    ],
    "e4_simple_complex": [
        "Fast/complex outcome: journey 32 with 8 turns.",
        "Simple outcome: journey 41 with 4 turns.",
        "Purpose: test whether route simplicity can justify a longer journey.",
        "E4 is a promoted validated legacy Flatland environment.",
    ],
}

EXPERIMENT_FINDING = {
    "e1_fast_slow": (
        "All five profiles choose the fast service (journey 10). "
        "This is expected because the fast option dominates the slower option "
        "on the measured preference dimensions."
    ),
    "e2_transfer_network": (
        "Fastest chooses journey 14 with 2 transfers. Fewer Transfers, "
        "Less Waiting and Balanced choose the direct journey 18 with 0 transfers."
    ),
    "e3_waiting_network": (
        "Fastest chooses journey 11 / wait 5, while Less Waiting and Balanced "
        "choose journey 13 / wait 1."
    ),
    "e4_simple_complex": (
        "Fastest chooses journey 32 / 8 turns, while Simple Journey chooses "
        "journey 41 / 4 turns."
    ),
}

ENCODINGS = [
    "asp/custom/connection.lp",
    "asp/custom/encoding.lp",
    "asp/custom/waypoint.lp",
    "asp/custom/passenger_transfer.lp",
    "asp/custom/visual.lp",
    "asp/custom/objectives.lp",
]

WEIGHTS = ["w_arrival", "w_wait", "w_transfer", "w_turn", "w_waypoint"]
WEIGHT_LABELS = {
    "w_arrival": "Early arrival",
    "w_wait": "Transfer timing (ideal: 6 steps)",
    "w_transfer": "Fewer transfers",
    "w_turn": "Simpler route",
    "w_waypoint": "Earlier intermediate stops",
}
PROFILE_LABELS = {
    "fastest": "Fastest",
    "least_waiting": "Less Waiting (ideal transfer: 6 steps)",
    "fewest_transfers": "Fewer transfers",
    "comfort": "Simple journey",
    "balanced": "Balanced",
}

OBJECTIVE_MODE_BY_PROFILE = {
    "fastest": "fastest",
    "least_waiting": "least_waiting",
    "fewest_transfers": "fewest_transfers",
    "comfort": "simple",
    "balanced": "weighted",
}

OBJECTIVE_DESCRIPTION = {
    "fastest": "Journey duration first; other metrics break ties.",
    "least_waiting": "Transfer-time deviation from the 6-step ideal first; other metrics break ties.",
    "fewest_transfers": "Passenger transfers first; other metrics break ties.",
    "simple": "Route turns first; other metrics break ties.",
    "weighted": "Weighted multi-objective optimization.",
}


def read_profile(path):
    values = {}
    text = path.read_text(encoding="utf-8")
    for name, num in re.findall(r"#const\s+(\w+)\s*=\s*(\d+)\s*\.", text):
        values[name] = int(num)
    return values


def list_profiles():
    profiles = {}
    for path in sorted(PROFILE_DIR.glob("profile_*.lp")):
        name = path.stem.replace("profile_", "")
        if name == "active":
            continue
        profiles[name] = read_profile(path)
    return profiles


def profile_label(name):
    return PROFILE_LABELS.get(name, name.replace("_", " ").title())


def write_active_profile(weights, objective_mode="weighted"):
    lines = [
        f"objective_mode({objective_mode}).",
        "",
        *[f"#const {name} = {int(weights[name])}." for name in WEIGHTS],
    ]
    ACTIVE_PROFILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def scenario_for_env(env_path):
    scenario = SCENARIO_DIR / f"{Path(env_path).stem}.lp"
    if not scenario.exists():
        raise FileNotFoundError(
            f"No scenario configuration exists for {Path(env_path).name}. "
            f"Expected {scenario}"
        )
    return scenario


def available_envs(kind):
    folder = REPO / "envs" / kind
    extension = "*.lp" if kind == "lp" else "*.pkl"
    return [
        path
        for path in sorted(folder.glob(extension))
        if (SCENARIO_DIR / f"{path.stem}.lp").exists()
    ]


def ensure_show_metrics_file():
    show_file = REPO / "ui" / "show_metrics.lp"
    show_file.write_text(
        "\n".join(
            [
                "#show cost/3.",
                "#show arrival/2.",
                "#show travel_time/2.",
                "#show waiting_time/2.",
                "#show turns/2.",
                "#show transfer_count/2.",
                "#show waypoint_time/2.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return show_file


def run_clingo(env_lp, time_limit):
    show_file = ensure_show_metrics_file()
    scenario = scenario_for_env(env_lp)
    clingo_cmd = backend_python_cmd() + ["-m", "clingo"]
    cmd = (
        clingo_cmd
        + [str(env_lp)]
        + [str(REPO / encoding) for encoding in ENCODINGS]
        + [str(scenario), str(ACTIVE_PROFILE), str(show_file)]
        + [f"--time-limit={int(time_limit)}"]
    )
    started = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    elapsed = time.perf_counter() - started
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "text": result.stdout + result.stderr,
        "elapsed": elapsed,
    }


def last_answer_atoms(text):
    matches = re.findall(
        r"Answer:\s*\d+\s*\n(.*?)(?=\nOptimization:|\nAnswer:|\nOPTIMUM FOUND|\nSATISFIABLE|\nUNSATISFIABLE|\Z)",
        text,
        flags=re.DOTALL,
    )
    return matches[-1].split() if matches else []


def parse_pair_atoms(atoms, predicate):
    pattern = re.compile(rf"^{re.escape(predicate)}\(([^,()]+),(-?\d+)\)$")
    values = {}
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            values[match.group(1)] = int(match.group(2))
    return values


def parse_cost_atoms(atoms):
    pattern = re.compile(r"^cost\(([^,()]+),([^,()]+),(-?\d+)\)$")
    values = []
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            values.append({"entity": match.group(1), "type": match.group(2), "cost": int(match.group(3))})
    return values


def parse_solver_result(run):
    text = run["text"]
    atoms = last_answer_atoms(text)
    optimization_matches = re.findall(r"Optimization:\s*(.+)", text)
    optimization = optimization_matches[-1].strip() if optimization_matches else None
    time_match = re.search(r"\nTime\s*:\s*([\d.]+)s", text)
    solver_time = float(time_match.group(1)) if time_match else run["elapsed"]

    status = "UNKNOWN"
    if "UNSATISFIABLE" in text:
        status = "UNSAT"
    elif "OPTIMUM FOUND" in text:
        status = "OPTIMUM"
    elif "SATISFIABLE" in text or atoms:
        status = "SAT"

    arrivals = parse_pair_atoms(atoms, "arrival")
    travel_times = parse_pair_atoms(atoms, "travel_time")
    waits = parse_pair_atoms(atoms, "waiting_time")
    turns = parse_pair_atoms(atoms, "turns")
    transfers = parse_pair_atoms(atoms, "transfer_count")
    waypoints = parse_pair_atoms(atoms, "waypoint_time")

    actions = [atom for atom in atoms if atom.startswith("action(")]
    non_actions = [atom for atom in atoms if not atom.startswith("action(")]

    return {
        "status": status,
        "optimization": optimization,
        "solver_time": solver_time,
        "arrivals": arrivals,
        "travel_times": travel_times,
        "waiting": waits,
        "turns": turns,
        "transfers": transfers,
        "waypoints": waypoints,
        "costs": parse_cost_atoms(atoms),
        "actions": actions,
        "atoms": non_actions,
        "arrival_total": sum(arrivals.values()),
        "travel_time_total": sum(travel_times.values()),
        "waiting_total": sum(waits.values()),
        "turn_total": sum(turns.values()),
        "transfer_total": sum(transfers.values()),
        "waypoint_total": sum(waypoints.values()),
    }


def render_metric_summary(parsed):
    cols = st.columns(5)
    cols[0].metric("Journey time", parsed["travel_time_total"])
    cols[1].metric("Waiting", parsed["waiting_total"])
    cols[2].metric("Transfers", parsed["transfer_total"])
    cols[3].metric("Route turns", parsed["turn_total"])
    cols[4].metric("Intermediate timing", parsed["waypoint_total"])

    if parsed["arrivals"]:
        with st.expander("Per-train journey metrics"):
            train_ids = sorted(
                set(parsed["arrivals"]) | set(parsed["travel_times"]) | set(parsed["waiting"]) | set(parsed["turns"]) | set(parsed["waypoints"])
            )
            rows = []
            for train_id in train_ids:
                rows.append(
                    {
                        "Train": train_id,
                        "Arrival clock": parsed["arrivals"].get(train_id, 0),
                        "Journey time": parsed["travel_times"].get(train_id, 0),
                        "Waiting": parsed["waiting"].get(train_id, 0),
                        "Turns": parsed["turns"].get(train_id, 0),
                        "Intermediate timing": parsed["waypoints"].get(train_id, 0),
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)


def run_full_simulation(env_pkl):
    output_dir = REPO / "output"
    before = set(output_dir.glob("*")) if output_dir.exists() else set()
    result = subprocess.run(
        backend_python_cmd() + ["solve.py", str(env_pkl)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    after = set(output_dir.glob("*")) if output_dir.exists() else set()
    new_dirs = sorted(after - before, key=lambda path: path.stat().st_mtime)
    run_dir = new_dirs[-1] if new_dirs else None

    validation = None
    if run_dir:
        validation_path = run_dir / "validation.json"
        if validation_path.exists():
            validation = json.loads(validation_path.read_text(encoding="utf-8"))

    return {
        "process": result,
        "run_dir": run_dir,
        "validation": validation,
        "gif": (run_dir / "animation.gif") if run_dir else None,
    }


def render_validation(full_run):
    validation = full_run["validation"]
    gif = full_run["gif"]
    process = full_run["process"]

    if validation and validation.get("success"):
        st.success("Validated schedule — ASP and Flatland agree, and all trains reached their destinations.")
        if gif and gif.exists():
            st.image(str(gif))
        return

    if validation:
        st.error("The schedule failed Flatland execution validation.")
        c1, c2 = st.columns(2)
        c1.metric("All trains completed", "Yes" if validation.get("all_trains_done") else "No")
        c2.metric("Plan/execution divergences", validation.get("divergence_count", 0))
        if validation.get("first_divergence"):
            with st.expander("First divergence"):
                st.json(validation["first_divergence"])
        if gif and gif.exists():
            st.caption("Failed execution animation")
            st.image(str(gif))
        return

    if process.returncode != 0:
        st.error("The full simulation failed before validation completed.")
    else:
        st.warning("The simulation finished but did not produce validation.json.")


def csv_from_rows(rows):
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


st.set_page_config(page_title="RS42 Journey Optimizer", page_icon=None, layout="wide")
st.title("RS42 Journey Optimizer")
st.caption("Passenger-oriented railway schedule optimization with validated Flatland execution.")

profiles = list_profiles()
planner_tab, evaluation_tab, experiments_tab = st.tabs(
    ["Journey Planner", "Research Evaluation", "Experiments"]
)

with planner_tab:
    st.subheader("Plan a journey")

    pkl_envs = available_envs("pkl")
    lp_envs = [
        path
        for path in available_envs("lp")
        if path.stem in EVALUATION_ENVIRONMENTS
    ]
    common_stems = sorted(
        (
            set(path.stem for path in pkl_envs)
            & set(path.stem for path in lp_envs)
        )
        & set(PASSENGER_ENVIRONMENTS)
    )

    if not common_stems:
        st.error("No environment has a matching .lp, .pkl and scenario file.")
    else:
        scenario_stem = st.selectbox(
            "Railway scenario",
            common_stems,
            format_func=lambda value: EXPERIMENT_LABELS.get(
                value, value.replace("_", " ")
            ),
            key="planner_scenario",
        )

        st.write("What matters most for this journey?")
        choice = st.radio(
            "Journey preference",
            list(profiles.keys()) + ["custom"],
            format_func=lambda value: "Custom priorities" if value == "custom" else profile_label(value),
            horizontal=True,
            label_visibility="collapsed",
            key="planner_preference",
        )

        if choice == "custom":
            base = profiles.get("balanced", {weight: 8 for weight in WEIGHTS})
            weights = {}
            with st.expander("Custom optimization priorities", expanded=True):
                cols = st.columns(len(WEIGHTS))
                for col, weight in zip(cols, WEIGHTS):
                    with col:
                        weights[weight] = st.slider(
                            WEIGHT_LABELS[weight], 0, 25, base.get(weight, 5), key=f"planner_{weight}"
                        )
        else:
            weights = {weight: profiles[choice].get(weight, 5) for weight in WEIGHTS}

        with st.expander("Advanced options"):
            st.caption(
                f"Backend environment: {BACKEND_CONDA_ENV} "
                "(Clingo + Flatland)"
            )
            execution_mode = st.radio(
                "Execution",
                ["Validate in Flatland + animation", "ASP preview only"],
                key="planner_execution",
            )
            time_limit = st.number_input(
                "Clingo time limit (seconds)", 5, 600, 60, key="planner_time_limit"
            )
            objective_mode = (
                "weighted"
                if choice == "custom"
                else OBJECTIVE_MODE_BY_PROFILE.get(choice, "weighted")
            )
            st.write("Optimization policy")
            st.caption(
                OBJECTIVE_DESCRIPTION.get(
                    objective_mode,
                    "Weighted multi-objective optimization.",
                )
            )
            if objective_mode == "weighted":
                st.write("Backend weights")
                st.code(
                    "\n".join(
                        f"#const {weight} = {weights[weight]}."
                        for weight in WEIGHTS
                    )
                )

        if st.button("Optimize journey", type="primary", use_container_width=True, key="planner_run"):
            objective_mode = (
                "weighted"
                if choice == "custom"
                else OBJECTIVE_MODE_BY_PROFILE.get(choice, "weighted")
            )
            write_active_profile(weights, objective_mode)
            env_lp = REPO / "envs" / "lp" / f"{scenario_stem}.lp"
            env_pkl = REPO / "envs" / "pkl" / f"{scenario_stem}.pkl"

            with st.spinner("Finding the best schedule for this preference..."):
                quick_run = run_clingo(env_lp, time_limit)
                parsed = parse_solver_result(quick_run)

            if parsed["status"] == "UNSAT":
                st.error("No feasible schedule exists for this setup.")
            elif parsed["status"] == "UNKNOWN":
                st.error("The solver did not return a usable schedule.")
            else:
                preference_name = "Custom priorities" if choice == "custom" else profile_label(choice)
                st.success(f"Recommended schedule — {preference_name}")
                render_metric_summary(parsed)

                if parsed["optimization"] is not None:
                    st.caption(
                        f"Clingo optimization result: {parsed['optimization']} · "
                        f"Solver time: {parsed['solver_time']:.2f}s"
                    )

                if execution_mode.startswith("Validate"):
                    with st.spinner("Executing the optimized schedule in Flatland..."):
                        full_run = run_full_simulation(env_pkl)
                    render_validation(full_run)
                    with st.expander("Technical execution log"):
                        st.text((full_run["process"].stdout + full_run["process"].stderr)[-5000:])

                with st.expander("ASP schedule and technical details"):
                    st.write(f"Actions: {len(parsed['actions'])}")
                    st.code("\n".join(sorted(parsed["actions"])) or "No actions parsed.")
                    st.write("Best-answer-set metrics")
                    st.code("\n".join(sorted(parsed["atoms"])) or "No displayed metrics.")
                    st.write("Raw Clingo output")
                    st.text(quick_run["text"][-8000:])

with evaluation_tab:
    st.subheader("Compare optimization strategies")
    st.caption(
        "Run predefined preference profiles on the same railway scenario and compare the resulting schedule characteristics."
    )

    lp_envs = available_envs("lp")
    if not lp_envs:
        st.error("No scenario-aware .lp environments are available.")
    else:
        eval_env = st.selectbox(
            "Railway scenario",
            lp_envs,
            format_func=lambda path: EXPERIMENT_LABELS.get(
                path.stem, path.stem.replace("_", " ")
            ),
            key="evaluation_scenario",
        )
        eval_time_limit = st.number_input(
            "Time limit per profile (seconds)", 5, 600, 60, key="evaluation_time_limit"
        )
        selected_profiles = st.multiselect(
            "Profiles to compare",
            list(profiles.keys()),
            default=list(profiles.keys()),
            format_func=profile_label,
            key="evaluation_profiles",
        )

        st.info(
            "Named profiles use lexicographic priorities, while Balanced uses a weighted objective. Compare the actual outcome metrics across profiles; the Clingo optimization result may be a multi-priority vector and should not be compared as a single score across different policies."
        )

        if st.button("Run comparison", type="primary", use_container_width=True, key="evaluation_run"):
            if not selected_profiles:
                st.warning("Select at least one profile.")
            else:
                original_active = ACTIVE_PROFILE.read_text(encoding="utf-8") if ACTIVE_PROFILE.exists() else None
                rows = []
                raw_outputs = {}
                progress = st.progress(0)

                try:
                    for index, name in enumerate(selected_profiles, start=1):
                        weights = {weight: profiles[name].get(weight, 5) for weight in WEIGHTS}
                        objective_mode = OBJECTIVE_MODE_BY_PROFILE.get(name, "weighted")
                        write_active_profile(weights, objective_mode)
                        run = run_clingo(eval_env, eval_time_limit)
                        parsed = parse_solver_result(run)
                        raw_outputs[name] = run["text"]
                        rows.append(
                            {
                                "Profile": profile_label(name),
                                "Status": parsed["status"],
                                "Journey time": parsed["travel_time_total"],
                                "Arrival clock": parsed["arrival_total"],
                                "Waiting": parsed["waiting_total"],
                                "Transfers": parsed["transfer_total"],
                                "Route turns": parsed["turn_total"],
                                "Intermediate timing": parsed["waypoint_total"],
                                "Solver time (s)": round(parsed["solver_time"], 3),
                                "Profile objective": parsed["optimization"] or "",
                            }
                        )
                        progress.progress(int(index / len(selected_profiles) * 100))
                finally:
                    if original_active is not None:
                        ACTIVE_PROFILE.write_text(original_active, encoding="utf-8")

                st.success("Comparison complete")
                st.dataframe(rows, use_container_width=True, hide_index=True)

                chart_rows = {
                    row["Profile"]: {
                        "Journey time": row["Journey time"],
                        "Waiting": row["Waiting"],
                        "Transfers": row["Transfers"],
                        "Route turns": row["Route turns"],
                    }
                    for row in rows
                    if row["Status"] in {"OPTIMUM", "SAT"}
                }
                if chart_rows:
                    st.write("Outcome comparison")
                    st.bar_chart(chart_rows)

                st.download_button(
                    "Download comparison CSV",
                    data=csv_from_rows(rows),
                    file_name=f"rs42_{eval_env.stem}_profile_comparison.csv",
                    mime="text/csv",
                )

                with st.expander("Raw solver outputs"):
                    for name in selected_profiles:
                        st.write(profile_label(name))
                        st.text(raw_outputs[name][-5000:])

with experiments_tab:
    st.subheader("Experiments")
    st.caption(
        "Six railway scenarios were used to see how different journey "
        "preferences change the recommended schedule."
    )

    experiment_order = [
        "e1_fast_slow",
        "e2_transfer_network",
        "e3_waiting_network",
        "e4_simple_complex",
        "e5_mixed_preferences",
        "e6_shared_conflict",
    ]

    labels = {
        "e1_fast_slow": "E1 — Fast vs Slow",
        "e2_transfer_network": "E2 — Transfers",
        "e3_waiting_network": "E3 — Waiting",
        "e4_simple_complex": "E4 — Simple vs Complex",
        "e5_mixed_preferences": "E5 — Mixed Preferences",
        "e6_shared_conflict": "E6 — Shared Infrastructure",
    }

    intro = {
        "e1_fast_slow": (
            "A control case with a clearly faster and a slower service."
        ),
        "e2_transfer_network": (
            "A faster journey with train changes competes with a slower "
            "direct journey."
        ),
        "e3_waiting_network": (
            "Two journeys have the same number of transfers but different "
            "connection waiting times."
        ),
        "e4_simple_complex": (
            "A shorter but more complex route competes with a longer, "
            "simpler route."
        ),
        "e5_mixed_preferences": (
            "Journey time, waiting and number of transfers all compete "
            "in the same scenario."
        ),
        "e6_shared_conflict": (
            "A separate two-train scenario checks whether schedules still "
            "work when trains share infrastructure."
        ),
    }

    question = {
        "e1_fast_slow": (
            "Does the planner reliably identify the clearly faster service?"
        ),
        "e2_transfer_network": (
            "When is saving time worth changing trains?"
        ),
        "e3_waiting_network": (
            "When is a slightly longer trip worth less waiting?"
        ),
        "e4_simple_complex": (
            "When is a simpler route worth taking more time?"
        ),
        "e5_mixed_preferences": (
            "Do different priorities still lead to sensible choices when "
            "several trade-offs exist together?"
        ),
        "e6_shared_conflict": (
            "Can the generated schedule still be executed successfully "
            "with multiple trains?"
        ),
    }

    finding = {
        "e1_fast_slow": (
            "All preferences choose the faster service."
        ),
        "e2_transfer_network": (
            "Fastest chooses the quicker journey with transfers. "
            "The other preferences choose the direct journey."
        ),
        "e3_waiting_network": (
            "Fastest chooses the shorter trip. Less Waiting and Balanced "
            "accept a slightly longer trip to reduce connection waiting."
        ),
        "e4_simple_complex": (
            "Fastest chooses the shorter route. Simple Journey accepts a "
            "longer trip to reduce route complexity."
        ),
        "e5_mixed_preferences": (
            "Fastest chooses the quickest option, Simple Journey chooses "
            "the compromise, and waiting/transfer-sensitive preferences "
            "choose the direct option."
        ),
        "e6_shared_conflict": (
            "The multi-train schedule was successfully executed and "
            "validated in Flatland."
        ),
    }

    friendly_profile = {
        "fastest": "Fastest",
        "least_waiting": "Less Waiting (ideal transfer: 6 steps)",
        "fewest_transfers": "Fewer Transfers",
        "simple": "Simple Journey",
        "comfort": "Simple Journey",
        "balanced": "Balanced",
    }

    results_path = (
        REPO
        / "experiments"
        / "final_evaluation"
        / "results"
        / "runs"
        / "all_runs.csv"
    )

    final_rows = []
    if results_path.exists():
        with results_path.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as handle:
            final_rows = list(csv.DictReader(handle))

    experiment_tabs = st.tabs(
        [labels[stem] for stem in experiment_order]
    )

    profile_order = {
        "fastest": 0,
        "least_waiting": 1,
        "fewest_transfers": 2,
        "simple": 3,
        "comfort": 3,
        "balanced": 4,
    }

    for stem, view in zip(experiment_order, experiment_tabs):
        with view:
            st.markdown(f"### {labels[stem]}")
            st.write(intro[stem])

            image_col, explanation_col = st.columns([1.2, 1])

            with image_col:
                image_path = (
                    REPO
                    / "envs"
                    / "png"
                    / f"{stem}.png"
                )

                if image_path.exists():
                    st.image(
                        str(image_path),
                        use_container_width=True,
                    )
                else:
                    st.info("Scenario preview is not available.")

            with explanation_col:
                st.markdown("#### What are we testing?")
                st.write(question[stem])

                st.markdown("#### Result")
                st.write(finding[stem])

            environment_rows = [
                row
                for row in final_rows
                if row.get("environment") == stem
            ]

            environment_rows.sort(
                key=lambda row: profile_order.get(
                    row.get("profile"),
                    99,
                )
            )

            if stem != "e6_shared_conflict" and environment_rows:
                st.markdown("#### How preferences changed the journey")

                table_rows = []

                for row in environment_rows:
                    table_rows.append(
                        {
                            "Preference": friendly_profile.get(
                                row.get("profile", ""),
                                row.get(
                                    "profile_label",
                                    row.get("profile", ""),
                                ),
                            ),
                            "Journey time": row.get(
                                "journey_time",
                                "",
                            ),
                            "Waiting": row.get(
                                "transfer_wait",
                                "",
                            ),
                            "Transfers": row.get(
                                "transfers",
                                "",
                            ),
                            "Route turns": row.get(
                                "turns",
                                "",
                            ),
                        }
                    )

                st.dataframe(
                    table_rows,
                    use_container_width=True,
                    hide_index=True,
                )

            elif stem == "e6_shared_conflict":
                st.success(
                    "Multi-train execution successfully validated."
                )
                st.caption(
                    "One optional preference stress test did not finish "
                    "within the evaluation window. This does not affect "
                    "the successful infrastructure execution check."
                )

    st.divider()
    st.write(
        "Together, these experiments show that the planner responds to "
        "different passenger priorities while still producing schedules "
        "that can be executed in the railway simulation."
    )
