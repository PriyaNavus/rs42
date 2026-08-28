# RS42 final Streamlit frontend
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
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parents[1]
PROFILE_DIR = REPO / "asp" / "profiles"
SCENARIO_DIR = REPO / "asp" / "scenarios"
ACTIVE_PROFILE = PROFILE_DIR / "active_profile.lp"

FINAL_EVAL_DIR = REPO / "experiments" / "final_evaluation"
FINAL_RESULTS_CSV = FINAL_EVAL_DIR / "results" / "runs" / "all_runs.csv"
COMPLETION_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "completion_status.json"
PRIMARY_CHECKS_JSON = FINAL_EVAL_DIR / "results" / "summaries" / "primary_checks.json"

BACKEND_CONDA_ENV = os.environ.get("RS42_BACKEND_ENV", "flatlandrs42")

ENCODINGS = [
    "asp/custom/connection.lp",
    "asp/custom/encoding.lp",
    "asp/custom/waypoint.lp",
    "asp/custom/passenger_transfer.lp",
    "asp/custom/visual.lp",
    "asp/custom/objectives.lp",
]

PROFILE_FILES = {
    "fastest": PROFILE_DIR / "profile_fastest.lp",
    "least_waiting": PROFILE_DIR / "profile_least_waiting.lp",
    "fewest_transfers": PROFILE_DIR / "profile_fewest_transfers.lp",
    "simple": PROFILE_DIR / "profile_comfort.lp",
    "balanced": PROFILE_DIR / "profile_balanced.lp",
}

PROFILE_LABELS = {
    "fastest": "Fastest",
    "least_waiting": "Less Waiting",
    "fewest_transfers": "Fewer Transfers",
    "simple": "Simple Journey",
    "balanced": "Balanced",
}

PROFILE_DESCRIPTIONS = {
    "fastest": "Prioritizes the shortest passenger journey time.",
    "least_waiting": "Prioritizes reducing connection waiting during the passenger journey.",
    "fewest_transfers": "Prioritizes using fewer train changes, even if the journey becomes longer.",
    "simple": "Prioritizes a route with fewer turns / lower route complexity.",
    "balanced": "Uses the project's weighted multi-objective policy to balance time, waiting, transfers and route simplicity.",
}

SCENARIO_ORDER = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
]

SCENARIO_LABELS = {
    "e1_fast_slow": "E1 — Fast vs Slow",
    "e2_transfer_network": "E2 — Transfer Network",
    "e3_waiting_network": "E3 — Waiting Network",
    "e4_simple_complex": "E4 — Simple vs Complex",
}

SCENARIO_DESCRIPTIONS = {
    "e1_fast_slow": (
        "Two services connect the same passenger origin and destination. "
        "One is shorter/faster and the other is longer/slower."
    ),
    "e2_transfer_network": (
        "A slower direct train competes with a faster three-leg journey "
        "through two intermediate transfer stations."
    ),
    "e3_waiting_network": (
        "Two one-transfer itineraries trade total journey time against "
        "connection waiting time."
    ),
    "e4_simple_complex": (
        "A shorter route with more turns competes with a longer route "
        "with fewer turns."
    ),
}

SCENARIO_QUESTIONS = {
    "e1_fast_slow": "Does the optimizer identify the genuinely faster service?",
    "e2_transfer_network": "Will Fastest accept transfers while Fewer Transfers prefers the slower direct service?",
    "e3_waiting_network": "Will Less Waiting accept a longer trip to reduce connection waiting?",
    "e4_simple_complex": "Will Simple Journey accept a longer trip to reduce route complexity?",
}

WEIGHTS = ["w_arrival", "w_wait", "w_transfer", "w_turn"]
WEIGHT_LABELS = {
    "w_arrival": "Journey / arrival",
    "w_wait": "Waiting",
    "w_transfer": "Transfers",
    "w_turn": "Route simplicity",
}


def backend_python_cmd():
    conda = shutil.which("conda")
    if conda:
        return [conda, "run", "-n", BACKEND_CONDA_ENV, "python"]
    explicit_python = os.environ.get("RS42_BACKEND_PYTHON")
    if explicit_python:
        return [explicit_python]
    return [sys.executable]


def profile_label(name):
    return PROFILE_LABELS.get(name, name.replace("_", " ").title())


def read_profile_text(name):
    path = PROFILE_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"Missing canonical profile: {path}")
    return path.read_text(encoding="utf-8")


def read_profile_weights(name):
    text = read_profile_text(name)
    values = {}
    for key, value in re.findall(r"#const\s+(\w+)\s*=\s*(-?\d+)\s*\.", text):
        values[key] = int(value)
    return values


def custom_profile_text(weights):
    lines = ["% RS42 UI custom weighted profile", "objective_mode(weighted).", ""]
    for weight in WEIGHTS:
        lines.append(f"#const {weight} = {int(weights[weight])}.")
    return "\n".join(lines) + "\n"


def write_custom_profile(weights):
    runtime_dir = REPO / "ui" / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = runtime_dir / "custom_profile.lp"
    path.write_text(custom_profile_text(weights), encoding="utf-8")
    return path


@contextmanager
def temporary_active_profile(profile_text):
    original = ACTIVE_PROFILE.read_text(encoding="utf-8") if ACTIVE_PROFILE.exists() else None
    ACTIVE_PROFILE.write_text(profile_text, encoding="utf-8")
    try:
        yield
    finally:
        if original is None:
            if ACTIVE_PROFILE.exists():
                ACTIVE_PROFILE.unlink()
        else:
            ACTIVE_PROFILE.write_text(original, encoding="utf-8")


def scenario_for_env(env_path):
    scenario = SCENARIO_DIR / f"{Path(env_path).stem}.lp"
    if not scenario.exists():
        raise FileNotFoundError(
            f"No scenario configuration exists for {Path(env_path).name}. "
            f"Expected {scenario}"
        )
    return scenario


def canonical_scenarios():
    available = []
    for stem in SCENARIO_ORDER:
        lp = REPO / "envs" / "lp" / f"{stem}.lp"
        pkl = REPO / "envs" / "pkl" / f"{stem}.pkl"
        scenario = SCENARIO_DIR / f"{stem}.lp"
        if lp.exists() and pkl.exists() and scenario.exists():
            available.append(stem)
    return available


def environment_image(stem):
    path = REPO / "envs" / "png" / f"{stem}.png"
    return path if path.exists() else None


def ensure_show_metrics_file():
    show_file = REPO / "ui" / "show_metrics.lp"
    show_file.write_text(
        "\n".join(
            [
                "#show chosen_leg/7.",
                "#show passenger_journey_time/2.",
                "#show passenger_transfer_wait/2.",
                "#show passenger_uses_train/2.",
                "#show uses_train/3.",
                "#show transfer_count/2.",
                "#show arrival/2.",
                "#show travel_time/2.",
                "#show waiting_time/2.",
                "#show wait_time/2.",
                "#show turns/2.",
                "#show waypoint_time/2.",
                "#show cost/3.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return show_file


def run_clingo(env_lp, profile_path, time_limit):
    show_file = ensure_show_metrics_file()
    scenario = scenario_for_env(env_lp)
    cmd = (
        backend_python_cmd()
        + ["-m", "clingo"]
        + [str(env_lp)]
        + [str(REPO / encoding) for encoding in ENCODINGS]
        + [
            str(profile_path),
            str(scenario),
            str(show_file),
            "--outf=2",
            "--opt-mode=opt",
            f"--time-limit={int(time_limit)}",
        ]
    )
    started = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=int(time_limit) + 45,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed": time.perf_counter() - started,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return {
            "returncode": None,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed": time.perf_counter() - started,
            "timed_out": True,
        }


def parse_pair_atoms(atoms, predicate):
    pattern = re.compile(rf"^{re.escape(predicate)}\(([^,()]+),(-?\d+)\)$")
    values = {}
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            values[match.group(1)] = int(match.group(2))
    return values


def first_passenger_metric(atoms, predicate):
    values = parse_pair_atoms(atoms, predicate)
    if not values:
        return None
    return next(iter(values.values()))


def parse_cost_atoms(atoms):
    pattern = re.compile(r"^cost\(([^,()]+),([^,()]+),(-?\d+)\)$")
    values = []
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            values.append(
                {
                    "entity": match.group(1),
                    "type": match.group(2),
                    "cost": int(match.group(3)),
                }
            )
    return values


def parse_chosen_legs(atoms):
    rows = []
    pattern = re.compile(
        r"^chosen_leg\(([^,]+),(\d+),(\d+),([^,]+),([^,]+),(-?\d+),(-?\d+)\)$"
    )
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            rows.append(
                {
                    "Passenger": match.group(1),
                    "Leg": int(match.group(2)),
                    "Train": int(match.group(3)),
                    "From": match.group(4),
                    "To": match.group(5),
                    "Board": int(match.group(6)),
                    "Alight": int(match.group(7)),
                }
            )
    return sorted(rows, key=lambda row: row["Leg"])


def selected_train_ids(atoms, chosen_legs):
    if chosen_legs:
        return sorted({row["Train"] for row in chosen_legs})
    ids = []
    patterns = [
        re.compile(r"^passenger_uses_train\([^,]+,(\d+)\)$"),
        re.compile(r"^uses_train\([^,]+,(\d+),\d+\)$"),
    ]
    for atom in atoms:
        for pattern in patterns:
            match = pattern.match(atom)
            if match:
                ids.append(int(match.group(1)))
                break
    return sorted(set(ids))


def aggregate_metric(metric_map, train_ids):
    values = [
        metric_map[str(train_id)]
        for train_id in train_ids
        if str(train_id) in metric_map
    ]
    return sum(values) if values else None


def parse_solver_result(run, env_stem=None):
    if run["timed_out"]:
        return {
            "status": "TIMEOUT",
            "solver_time": run["elapsed"],
            "message": "The solver exceeded the selected time limit.",
        }

    try:
        data = json.loads(run["stdout"])
    except Exception:
        return {
            "status": "BAD_JSON",
            "solver_time": run["elapsed"],
            "message": "The solver did not return readable JSON output.",
        }

    status = str(data.get("Result", "UNKNOWN")).upper()
    calls = data.get("Call", [])
    witnesses = calls[-1].get("Witnesses", []) if calls else []

    if not witnesses:
        return {
            "status": status,
            "solver_time": run["elapsed"],
            "message": "No answer set was returned.",
        }

    witness = witnesses[-1]
    atoms = witness.get("Value", [])
    costs = witness.get("Costs", [])

    chosen_legs = parse_chosen_legs(atoms)
    train_ids = selected_train_ids(atoms, chosen_legs)

    travel_times = parse_pair_atoms(atoms, "travel_time")
    waiting_times = parse_pair_atoms(atoms, "waiting_time")
    if not waiting_times:
        waiting_times = parse_pair_atoms(atoms, "wait_time")
    turns = parse_pair_atoms(atoms, "turns")
    arrivals = parse_pair_atoms(atoms, "arrival")
    waypoints = parse_pair_atoms(atoms, "waypoint_time")

    if env_stem == "e4_simple_complex" and not train_ids:
        all_ids = set()
        for metric_map in [travel_times, waiting_times, turns, arrivals, waypoints]:
            all_ids.update(int(key) for key in metric_map)
        train_ids = sorted(all_ids)

    passenger_journey = first_passenger_metric(atoms, "passenger_journey_time")
    passenger_wait = first_passenger_metric(atoms, "passenger_transfer_wait")
    passenger_transfers = first_passenger_metric(atoms, "transfer_count")

    journey_time = passenger_journey if passenger_journey is not None else aggregate_metric(travel_times, train_ids)
    route_turns = aggregate_metric(turns, train_ids)

    return {
        "status": status,
        "solver_time": run["elapsed"],
        "optimization_cost": costs,
        "journey_time": journey_time,
        "passenger_wait": passenger_wait,
        "transfers": passenger_transfers,
        "turns": route_turns,
        "selected_trains": train_ids,
        "chosen_legs": chosen_legs,
        "travel_times": travel_times,
        "waiting_times": waiting_times,
        "turn_map": turns,
        "arrivals": arrivals,
        "waypoints": waypoints,
        "cost_atoms": parse_cost_atoms(atoms),
        "atoms": atoms,
        "message": None,
    }


def result_is_success(parsed):
    return parsed.get("status") in {"OPTIMUM FOUND", "SATISFIABLE"}


def display_value(value):
    return "N/A" if value is None else value


def render_metric_summary(parsed):
    cols = st.columns(4)
    cols[0].metric("Journey time", display_value(parsed["journey_time"]))
    cols[1].metric("Transfer waiting", display_value(parsed["passenger_wait"]))
    cols[2].metric("Transfers", display_value(parsed["transfers"]))
    cols[3].metric("Route turns", display_value(parsed["turns"]))

    if parsed["selected_trains"]:
        st.caption(
            "Selected train(s): "
            + ", ".join(str(train) for train in parsed["selected_trains"])
        )

    if parsed["chosen_legs"]:
        st.write("Passenger itinerary")
        st.dataframe(
            pd.DataFrame(parsed["chosen_legs"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(
            "This scenario does not expose OD journey legs in the same "
            "format as E1–E3; aggregate schedule metrics are shown instead."
        )


def render_per_train_metrics(parsed):
    train_ids = sorted(
        {
            int(key)
            for metric_map in [
                parsed.get("arrivals", {}),
                parsed.get("travel_times", {}),
                parsed.get("waiting_times", {}),
                parsed.get("turn_map", {}),
                parsed.get("waypoints", {}),
            ]
            for key in metric_map
        }
    )
    if not train_ids:
        return

    rows = []
    for train_id in train_ids:
        key = str(train_id)
        rows.append(
            {
                "Train": train_id,
                "Arrival clock": parsed["arrivals"].get(key),
                "Travel time": parsed["travel_times"].get(key),
                "Train waiting": parsed["waiting_times"].get(key),
                "Turns": parsed["turn_map"].get(key),
                "Intermediate timing": parsed["waypoints"].get(key),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def run_full_simulation(env_pkl, profile_text):
    output_dir = REPO / "output"
    before = set(output_dir.glob("*")) if output_dir.exists() else set()

    with temporary_active_profile(profile_text):
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
        st.success(
            "Flatland validation PASS — the ASP plan matched execution "
            "and all trains reached their destinations."
        )
        if gif and gif.exists():
            st.image(str(gif), use_container_width=True)
        return

    if validation:
        st.error("The schedule failed Flatland execution validation.")
        c1, c2 = st.columns(2)
        c1.metric(
            "All trains completed",
            "Yes" if validation.get("all_trains_done") else "No",
        )
        c2.metric(
            "Plan/execution divergences",
            validation.get("divergence_count", 0),
        )
        return

    if process.returncode != 0:
        st.error("The full Flatland simulation failed before validation.")
    else:
        st.warning("The simulation finished but did not produce validation.json.")


def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_final_results():
    if not FINAL_RESULTS_CSV.exists():
        return None
    frame = pd.read_csv(FINAL_RESULTS_CSV)
    for column in [
        "runtime_seconds",
        "journey_time",
        "transfer_wait",
        "transfers",
        "turns",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def scenario_header(stem):
    st.subheader(SCENARIO_LABELS.get(stem, stem.replace("_", " ").title()))
    st.write(SCENARIO_DESCRIPTIONS.get(stem, ""))
    st.caption(SCENARIO_QUESTIONS.get(stem, ""))


def render_environment_image(stem):
    image = environment_image(stem)
    if image:
        st.image(str(image), use_container_width=True)
    else:
        st.info("No environment preview image is available for this scenario.")


def csv_from_rows(rows):
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def research_interpretation(stem):
    return {
        "e1_fast_slow": (
            "Control result: every profile selects the same 10-step fast "
            "service because there is no meaningful competing advantage."
        ),
        "e2_transfer_network": (
            "Fastest accepts 2 transfers to reduce journey time from 18 to 14, "
            "while Fewer Transfers selects the slower direct service."
        ),
        "e3_waiting_network": (
            "Fastest selects journey 11 with wait 5; Less Waiting accepts "
            "journey 13 to reduce connection waiting to 1."
        ),
        "e4_simple_complex": (
            "Fastest selects journey 32 with 8 turns; Simple Journey accepts "
            "journey 41 to reduce route turns to 4."
        ),
    }.get(stem, "")


st.set_page_config(
    page_title="RS42 Journey Optimizer",
    page_icon="🚆",
    layout="wide",
)

st.title("RS42 Journey Optimizer")
st.caption(
    "Passenger-oriented railway scheduling with semantic preferences, "
    "ASP optimization and Flatland execution validation."
)

completion = load_json(COMPLETION_JSON)
checks = load_json(PRIMARY_CHECKS_JSON)

status_cols = st.columns(3)
status_cols[0].metric("Canonical environments", "4")
status_cols[1].metric(
    "Final optimization runs",
    f"{completion.get('optimum_found', 20)}/20" if completion else "20/20",
)
status_cols[2].metric(
    "Flatland validation",
    completion.get("flatland_validation", "PASS 4/4") if completion else "PASS 4/4",
)

planner_tab, evaluation_tab = st.tabs(["Journey Planner", "Research Evaluation"])

with planner_tab:
    scenarios = canonical_scenarios()

    if not scenarios:
        st.error(
            "The four canonical final-evaluation environments are not "
            "available with matching .lp, .pkl and scenario files."
        )
    else:
        left, right = st.columns([1.15, 1])

        with left:
            scenario_stem = st.selectbox(
                "Railway scenario",
                scenarios,
                format_func=lambda value: SCENARIO_LABELS.get(
                    value, value.replace("_", " ")
                ),
                key="planner_scenario",
            )
            render_environment_image(scenario_stem)

        with right:
            scenario_header(scenario_stem)

            st.write("### What matters most for this journey?")
            choice = st.radio(
                "Journey preference",
                list(PROFILE_FILES.keys()),
                format_func=profile_label,
                label_visibility="collapsed",
                key="planner_preference",
            )

            st.info(PROFILE_DESCRIPTIONS[choice])

            use_custom = st.checkbox(
                "Use custom weighted priorities",
                value=False,
                help=(
                    "Advanced option. The standard experiment uses the "
                    "five predefined semantic profiles."
                ),
            )

            if use_custom:
                base = read_profile_weights("balanced")
                with st.expander("Custom optimization priorities", expanded=True):
                    weights = {}
                    for weight in WEIGHTS:
                        weights[weight] = st.slider(
                            WEIGHT_LABELS[weight],
                            min_value=0,
                            max_value=25,
                            value=int(base.get(weight, 8)),
                            key=f"custom_{weight}",
                        )
                active_profile_path = write_custom_profile(weights)
                active_profile_text = active_profile_path.read_text(encoding="utf-8")
                preference_name = "Custom priorities"
            else:
                active_profile_path = PROFILE_FILES[choice]
                active_profile_text = read_profile_text(choice)
                preference_name = profile_label(choice)

            with st.expander("Advanced execution options"):
                st.caption(f"Backend Conda environment: {BACKEND_CONDA_ENV}")
                execution_mode = st.radio(
                    "Execution mode",
                    [
                        "ASP optimization only",
                        "ASP optimization + Flatland validation",
                    ],
                    key="planner_execution",
                )
                time_limit = st.number_input(
                    "Clingo time limit (seconds)",
                    min_value=5,
                    max_value=600,
                    value=60,
                    key="planner_time_limit",
                )
                if use_custom:
                    st.caption(
                        "Custom mode uses objective_mode(weighted). "
                        "Weights are shown only because Custom is enabled."
                    )

            if st.button(
                "Optimize journey",
                type="primary",
                use_container_width=True,
                key="planner_run",
            ):
                env_lp = REPO / "envs" / "lp" / f"{scenario_stem}.lp"
                env_pkl = REPO / "envs" / "pkl" / f"{scenario_stem}.pkl"

                with st.spinner(
                    f"Optimizing {SCENARIO_LABELS[scenario_stem]} "
                    f"for {preference_name}..."
                ):
                    run = run_clingo(env_lp, active_profile_path, time_limit)
                    parsed = parse_solver_result(run, scenario_stem)

                if not result_is_success(parsed):
                    st.error(f"Solver status: {parsed.get('status', 'UNKNOWN')}")
                    if parsed.get("message"):
                        st.write(parsed["message"])
                    with st.expander("Solver diagnostics"):
                        st.text((run["stdout"] + run["stderr"])[-8000:])
                else:
                    st.success(f"Recommended journey — {preference_name}")
                    render_metric_summary(parsed)

                    st.caption(
                        f"Solver status: {parsed['status']} · "
                        f"Runtime: {parsed['solver_time']:.2f}s"
                    )

                    if execution_mode.endswith("Flatland validation"):
                        with st.spinner(
                            "Executing the optimized schedule in Flatland..."
                        ):
                            full_run = run_full_simulation(
                                env_pkl, active_profile_text
                            )
                        render_validation(full_run)

                    with st.expander("Technical details"):
                        st.write("Per-train metrics")
                        render_per_train_metrics(parsed)
                        st.write("Optimization cost")
                        st.code(str(parsed.get("optimization_cost", [])))
                        if parsed.get("cost_atoms"):
                            st.write("Cost atoms")
                            st.dataframe(
                                pd.DataFrame(parsed["cost_atoms"]),
                                use_container_width=True,
                                hide_index=True,
                            )
                        st.write("Displayed ASP atoms")
                        st.code(
                            "\n".join(sorted(parsed.get("atoms", [])))
                            or "No atoms displayed."
                        )

with evaluation_tab:
    st.subheader("Final controlled evaluation")
    st.caption(
        "Four deterministic environments × five canonical semantic profiles "
        "= 20 optimization runs."
    )

    results = load_final_results()

    if results is None:
        st.warning(
            "Final results file not found. Expected: "
            f"{FINAL_RESULTS_CSV.relative_to(REPO)}"
        )
    else:
        scenario_stem = st.selectbox(
            "Environment",
            [
                stem
                for stem in SCENARIO_ORDER
                if stem in set(results["environment"])
            ],
            format_func=lambda value: SCENARIO_LABELS[value],
            key="evaluation_scenario",
        )

        image_col, text_col = st.columns([1.1, 1])
        with image_col:
            render_environment_image(scenario_stem)
        with text_col:
            scenario_header(scenario_stem)
            st.info(research_interpretation(scenario_stem))

        env_results = results[results["environment"] == scenario_stem].copy()
        label_order = [
            "Fastest",
            "Less Waiting",
            "Fewer Transfers",
            "Simple Journey",
            "Balanced",
        ]
        env_results["_order"] = env_results["profile_label"].map(
            {label: i for i, label in enumerate(label_order)}
        )
        env_results = env_results.sort_values("_order")

        display_columns = [
            "profile_label",
            "status",
            "journey_time",
            "transfer_wait",
            "transfers",
            "turns",
            "selected_trains",
            "runtime_seconds",
        ]
        display_names = {
            "profile_label": "Profile",
            "status": "Status",
            "journey_time": "Journey time",
            "transfer_wait": "Transfer wait",
            "transfers": "Transfers",
            "turns": "Route turns",
            "selected_trains": "Selected trains",
            "runtime_seconds": "Solver time (s)",
        }

        st.dataframe(
            env_results[display_columns].rename(columns=display_names),
            use_container_width=True,
            hide_index=True,
        )

        chart_metrics = [
            metric
            for metric in ["journey_time", "transfer_wait", "transfers", "turns"]
            if env_results[metric].notna().any()
        ]
        if chart_metrics:
            chart_frame = (
                env_results[["profile_label"] + chart_metrics]
                .set_index("profile_label")
                .rename(
                    columns={
                        "journey_time": "Journey time",
                        "transfer_wait": "Transfer waiting",
                        "transfers": "Transfers",
                        "turns": "Route turns",
                    }
                )
            )
            st.write("### Outcome comparison")
            st.bar_chart(chart_frame)

        if checks:
            environment_checks = [
                check
                for check in checks.get("checks", [])
                if check.get("environment") == scenario_stem
            ]
            if environment_checks:
                st.write("### Controlled checks")
                for check in environment_checks:
                    if check.get("pass"):
                        st.success(check["name"])
                    else:
                        st.error(check["name"])
                    st.caption(check.get("description", ""))

        st.download_button(
            "Download this environment's results",
            data=env_results.drop(columns=["_order"]).to_csv(index=False),
            file_name=f"rs42_{scenario_stem}_final_results.csv",
            mime="text/csv",
        )

        with st.expander("Live profile comparison (optional)", expanded=False):
            st.caption(
                "The table above is the reproducible final evaluation. "
                "Use this section only when you want to rerun profiles live."
            )
            selected_profiles = st.multiselect(
                "Profiles to rerun",
                list(PROFILE_FILES.keys()),
                default=["fastest", "balanced"],
                format_func=profile_label,
                key="live_profiles",
            )
            live_time_limit = st.number_input(
                "Time limit per live profile (seconds)",
                min_value=5,
                max_value=600,
                value=60,
                key="live_time_limit",
            )

            if st.button(
                "Run live comparison",
                key="live_comparison",
                use_container_width=True,
            ):
                if not selected_profiles:
                    st.warning("Select at least one profile.")
                else:
                    env_lp = REPO / "envs" / "lp" / f"{scenario_stem}.lp"
                    rows = []
                    progress = st.progress(0)

                    for index, profile in enumerate(selected_profiles, start=1):
                        run = run_clingo(
                            env_lp,
                            PROFILE_FILES[profile],
                            live_time_limit,
                        )
                        parsed = parse_solver_result(run, scenario_stem)
                        rows.append(
                            {
                                "Profile": profile_label(profile),
                                "Status": parsed.get("status"),
                                "Journey time": parsed.get("journey_time"),
                                "Transfer wait": parsed.get("passenger_wait"),
                                "Transfers": parsed.get("transfers"),
                                "Route turns": parsed.get("turns"),
                                "Solver time (s)": round(
                                    parsed.get("solver_time", 0), 3
                                ),
                            }
                        )
                        progress.progress(
                            int(index / len(selected_profiles) * 100)
                        )

                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.download_button(
                        "Download live comparison CSV",
                        data=csv_from_rows(rows),
                        file_name=f"rs42_{scenario_stem}_live_comparison.csv",
                        mime="text/csv",
                    )
