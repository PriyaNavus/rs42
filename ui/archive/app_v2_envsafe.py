# RS42 frontend v2
# Run from repository root:
#   streamlit run ui/app_v2.py

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

ENCODINGS = [
    "asp/custom/connection.lp",
    "asp/custom/encoding.lp",
    "asp/custom/waypoint.lp",
    "asp/custom/passenger_transfer.lp",
    "asp/custom/visual.lp",
]

WEIGHTS = ["w_arrival", "w_wait", "w_transfer", "w_turn", "w_waypoint"]
WEIGHT_LABELS = {
    "w_arrival": "Early arrival",
    "w_wait": "Less waiting",
    "w_transfer": "Fewer transfers",
    "w_turn": "Simpler route",
    "w_waypoint": "Earlier intermediate stops",
}
PROFILE_LABELS = {
    "fastest": "Fastest",
    "least_waiting": "Less waiting",
    "fewest_transfers": "Fewer transfers",
    "comfort": "Simple journey",
    "balanced": "Balanced",
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


def write_active_profile(weights):
    lines = [f"#const {name} = {int(weights[name])}." for name in WEIGHTS]
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
        "waiting": waits,
        "turns": turns,
        "transfers": transfers,
        "waypoints": waypoints,
        "costs": parse_cost_atoms(atoms),
        "actions": actions,
        "atoms": non_actions,
        "arrival_total": sum(arrivals.values()),
        "waiting_total": sum(waits.values()),
        "turn_total": sum(turns.values()),
        "transfer_total": sum(transfers.values()),
        "waypoint_total": sum(waypoints.values()),
    }


def render_metric_summary(parsed):
    cols = st.columns(5)
    cols[0].metric("Total arrival time", parsed["arrival_total"])
    cols[1].metric("Waiting", parsed["waiting_total"])
    cols[2].metric("Transfers", parsed["transfer_total"])
    cols[3].metric("Route turns", parsed["turn_total"])
    cols[4].metric("Intermediate timing", parsed["waypoint_total"])

    if parsed["arrivals"]:
        with st.expander("Per-train journey metrics"):
            train_ids = sorted(
                set(parsed["arrivals"]) | set(parsed["waiting"]) | set(parsed["turns"]) | set(parsed["waypoints"])
            )
            rows = []
            for train_id in train_ids:
                rows.append(
                    {
                        "Train": train_id,
                        "Arrival": parsed["arrivals"].get(train_id, 0),
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
planner_tab, evaluation_tab = st.tabs(["Journey Planner", "Research Evaluation"])

with planner_tab:
    st.subheader("Plan a journey")

    pkl_envs = available_envs("pkl")
    lp_envs = available_envs("lp")
    common_stems = sorted(set(path.stem for path in pkl_envs) & set(path.stem for path in lp_envs))

    if not common_stems:
        st.error("No environment has a matching .lp, .pkl and scenario file.")
    else:
        scenario_stem = st.selectbox(
            "Railway scenario",
            common_stems,
            format_func=lambda value: value.replace("_", " "),
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
            st.write("Backend weights")
            st.code("\n".join(f"#const {weight} = {weights[weight]}." for weight in WEIGHTS))

        if st.button("Optimize journey", type="primary", use_container_width=True, key="planner_run"):
            write_active_profile(weights)
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
                        f"Profile-specific objective value: {parsed['optimization']} · "
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
            format_func=lambda path: path.stem.replace("_", " "),
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
            "Compare outcome metrics across profiles. The raw optimization value is profile-specific because each profile uses different weights, so absolute objective values should not be used to rank different profiles."
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
                        write_active_profile(weights)
                        run = run_clingo(eval_env, eval_time_limit)
                        parsed = parse_solver_result(run)
                        raw_outputs[name] = run["text"]
                        rows.append(
                            {
                                "Profile": profile_label(name),
                                "Status": parsed["status"],
                                "Arrival": parsed["arrival_total"],
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
                        "Arrival": row["Arrival"],
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
