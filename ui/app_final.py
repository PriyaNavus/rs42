from __future__ import annotations

import csv
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


# ============================================================
# Paths
# ============================================================

REPO = Path(__file__).resolve().parents[1]

PROFILE_DIR = REPO / "asp" / "profiles"
SCENARIO_DIR = REPO / "asp" / "scenarios"

ACTIVE_PROFILE = PROFILE_DIR / "active_profile.lp"

RESULTS_CSV = (
    REPO
    / "experiments"
    / "final_evaluation"
    / "results"
    / "runs"
    / "all_runs.csv"
)

BACKEND_ENV = os.environ.get(
    "RS42_BACKEND_ENV",
    "flatlandrs42",
)


# ============================================================
# Canonical RS42 setup
# ============================================================

PLANNER_ENVIRONMENTS = [
    "e1_fast_slow",
    "e2_transfer_network",
    "e3_waiting_network",
    "e4_simple_complex",
    "e5_mixed_preferences",
]

ALL_ENVIRONMENTS = PLANNER_ENVIRONMENTS + [
    "e6_shared_conflict",
]


LABELS = {
    "e1_fast_slow": "E1 · Fast vs Slow",
    "e2_transfer_network": "E2 · Transfer Network",
    "e3_waiting_network": "E3 · Waiting Network",
    "e4_simple_complex": "E4 · Simple vs Complex",
    "e5_mixed_preferences": "E5 · Mixed Preferences",
    "e6_shared_conflict": "E6 · Shared Infrastructure",
}


SHORT_LABELS = {
    "e1_fast_slow": "Fast vs Slow",
    "e2_transfer_network": "Transfers",
    "e3_waiting_network": "Waiting",
    "e4_simple_complex": "Route Simplicity",
    "e5_mixed_preferences": "Mixed Preferences",
    "e6_shared_conflict": "Infrastructure",
}


DESCRIPTIONS = {
    "e1_fast_slow": (
        "Two non-trivial services compete primarily on journey time. "
        "Both routes remain deliberately comparable in physical complexity."
    ),
    "e2_transfer_network": (
        "A quicker connected journey competes with a longer direct service, "
        "making the cost of changing trains explicit."
    ),
    "e3_waiting_network": (
        "Both choices require a transfer, but their connection timing differs. "
        "The experiment isolates the value of reducing waiting."
    ),
    "e4_simple_complex": (
        "A quicker but more complicated route competes with a longer route "
        "that has fewer direction changes."
    ),
    "e5_mixed_preferences": (
        "The integrated passenger experiment, now built on the real Flatland "
        "Test_02 Level_8 railway topology. Travel time, waiting, transfers and "
        "route simplicity compete in one larger network."
    ),
    "e6_shared_conflict": (
        "A multi-train environment used to check whether the optimized plan "
        "can be executed when trains share infrastructure."
    ),
}


QUESTIONS = {
    "e1_fast_slow": (
        "Which service should be chosen when travel time is the main difference?"
    ),
    "e2_transfer_network": (
        "When is a quicker trip worth changing trains?"
    ),
    "e3_waiting_network": (
        "When is a slightly longer trip worth a better connection?"
    ),
    "e4_simple_complex": (
        "When is a simpler route worth additional travel time?"
    ),
    "e5_mixed_preferences": (
        "How does the recommendation change when several passenger priorities "
        "matter at the same time?"
    ),
    "e6_shared_conflict": (
        "Can the generated plan still execute correctly in shared infrastructure?"
    ),
}


FOCUS = {
    "e1_fast_slow": [
        "Travel time",
        "Comparable route complexity",
    ],
    "e2_transfer_network": [
        "Travel time",
        "Transfers",
        "Direct vs connected journey",
    ],
    "e3_waiting_network": [
        "Connection waiting",
        "Travel time",
        "Equal transfer count",
    ],
    "e4_simple_complex": [
        "Route complexity",
        "Travel time",
    ],
    "e5_mixed_preferences": [
        "Travel time",
        "Waiting",
        "Transfers",
        "Route simplicity",
    ],
    "e6_shared_conflict": [
        "Shared infrastructure",
        "Multi-train execution",
    ],
}


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
    "fastest": (
        "Prioritises reaching the destination as early as possible."
    ),
    "least_waiting": (
        "Prioritises shorter connection waiting between services."
    ),
    "fewest_transfers": (
        "Prioritises staying on fewer trains."
    ),
    "simple": (
        "Prioritises a less complicated physical journey."
    ),
    "balanced": (
        "Balances time, waiting, transfers and route simplicity."
    ),
}


WEIGHTS = [
    "w_arrival",
    "w_wait",
    "w_transfer",
    "w_turn",
]


WEIGHT_LABELS = {
    "w_arrival": "Travel time",
    "w_wait": "Waiting",
    "w_transfer": "Transfers",
    "w_turn": "Route simplicity",
}


ENCODINGS = [
    "asp/custom/connection.lp",
    "asp/custom/encoding.lp",
    "asp/custom/waypoint.lp",
    "asp/custom/passenger_transfer.lp",
    "asp/custom/visual.lp",
    "asp/custom/objectives.lp",
]


# ============================================================
# Styling
# ============================================================

st.set_page_config(
    page_title="RS42 Journey Planner",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1450px;
    }

    [data-testid="stSidebar"] {
        min-width: 320px;
        max-width: 320px;
    }

    .rs42-hero {
        padding: 1.15rem 1.35rem;
        border: 1px solid rgba(120,120,120,.25);
        border-radius: 16px;
        margin-bottom: 1rem;
    }

    .rs42-kicker {
        font-size: .82rem;
        text-transform: uppercase;
        letter-spacing: .11em;
        opacity: .65;
        margin-bottom: .35rem;
    }

    .rs42-title {
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
    }

    .rs42-subtitle {
        opacity: .76;
        margin-top: .45rem;
        margin-bottom: 0;
    }

    .rs42-card {
        border: 1px solid rgba(120,120,120,.25);
        border-radius: 14px;
        padding: 1rem 1.05rem;
        min-height: 115px;
    }

    .rs42-card-title {
        font-weight: 650;
        font-size: 1.03rem;
        margin-bottom: .4rem;
    }

    .rs42-muted {
        opacity: .72;
        font-size: .94rem;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(120,120,120,.22);
        border-radius: 14px;
        padding: .65rem .8rem;
    }

    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Helpers
# ============================================================

def backend_python_cmd():
    conda = shutil.which("conda")

    if conda:
        return [
            conda,
            "run",
            "-n",
            BACKEND_ENV,
            "python",
        ]

    explicit = os.environ.get(
        "RS42_BACKEND_PYTHON"
    )

    if explicit:
        return [explicit]

    return [sys.executable]


def environment_paths(stem):
    return {
        "pkl": (
            REPO
            / "envs"
            / "pkl"
            / f"{stem}.pkl"
        ),
        "lp": (
            REPO
            / "envs"
            / "lp"
            / f"{stem}.lp"
        ),
        "png": (
            REPO
            / "envs"
            / "png"
            / f"{stem}.png"
        ),
        "scenario": (
            SCENARIO_DIR
            / f"{stem}.lp"
        ),
    }


def environment_available(stem):
    paths = environment_paths(stem)

    return all(
        paths[key].exists()
        for key in [
            "pkl",
            "lp",
            "scenario",
        ]
    )


def available_planner_environments():
    return [
        stem
        for stem in PLANNER_ENVIRONMENTS
        if environment_available(stem)
    ]


def profile_text(profile):
    path = PROFILE_FILES[profile]

    if not path.exists():
        raise FileNotFoundError(
            f"Missing profile: {path}"
        )

    return path.read_text(
        encoding="utf-8"
    )


def profile_weights(profile):
    text = profile_text(profile)

    values = {}

    for key, value in re.findall(
        r"#const\s+(\w+)\s*=\s*(-?\d+)\s*\.",
        text,
    ):
        values[key] = int(value)

    return values


def write_custom_profile(weights):
    runtime_dir = (
        REPO
        / "ui"
        / ".runtime"
    )

    runtime_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        runtime_dir
        / "custom_profile.lp"
    )

    lines = [
        "% RS42 custom UI profile",
        "objective_mode(weighted).",
        "",
    ]

    for key in WEIGHTS:
        lines.append(
            f"#const {key} = {int(weights[key])}."
        )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return path


def ensure_show_file():
    path = (
        REPO
        / "ui"
        / ".runtime"
        / "show_metrics.lp"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
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
                "#show turns/2.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return path


def run_preference(
    stem,
    profile_path,
    time_limit,
):
    paths = environment_paths(stem)

    cmd = (
        backend_python_cmd()
        + [
            "-m",
            "clingo",
            str(paths["lp"]),
        ]
        + [
            str(REPO / encoding)
            for encoding in ENCODINGS
        ]
        + [
            str(profile_path),
            str(paths["scenario"]),
            str(ensure_show_file()),
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
            timeout=int(time_limit) + 30,
        )

        return {
            "timed_out": False,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed": (
                time.perf_counter()
                - started
            ),
        }

    except subprocess.TimeoutExpired:
        return {
            "timed_out": True,
            "stdout": "",
            "stderr": "",
            "elapsed": (
                time.perf_counter()
                - started
            ),
        }


def pair_atoms(atoms, predicate):
    pattern = re.compile(
        rf"^{re.escape(predicate)}\(([^,()]+),(-?\d+)\)$"
    )

    values = {}

    for atom in atoms:
        match = pattern.match(atom)

        if match:
            values[
                match.group(1)
            ] = int(
                match.group(2)
            )

    return values


def passenger_metric(
    atoms,
    predicate,
):
    values = pair_atoms(
        atoms,
        predicate,
    )

    if not values:
        return None

    return next(
        iter(values.values())
    )


def chosen_legs(atoms):
    pattern = re.compile(
        r"^chosen_leg\("
        r"([^,]+),"
        r"(\d+),"
        r"(\d+),"
        r"([^,]+),"
        r"([^,]+),"
        r"(-?\d+),"
        r"(-?\d+)"
        r"\)$"
    )

    rows = []

    for atom in atoms:
        match = pattern.match(atom)

        if not match:
            continue

        rows.append(
            {
                "Leg": int(
                    match.group(2)
                ),
                "Train": int(
                    match.group(3)
                ),
                "From": match.group(4),
                "To": match.group(5),
                "Board": int(
                    match.group(6)
                ),
                "Arrive": int(
                    match.group(7)
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: row["Leg"],
    )


def selected_trains(
    atoms,
    legs,
):
    if legs:
        return sorted(
            {
                int(row["Train"])
                for row in legs
            }
        )

    ids = []

    patterns = [
        re.compile(
            r"^passenger_uses_train\([^,]+,(\d+)\)$"
        ),
        re.compile(
            r"^uses_train\([^,]+,(\d+),\d+\)$"
        ),
    ]

    for atom in atoms:
        for pattern in patterns:
            match = pattern.match(atom)

            if match:
                ids.append(
                    int(match.group(1))
                )
                break

    return sorted(set(ids))


def sum_for_trains(
    metric_map,
    train_ids,
):
    values = [
        metric_map[str(train)]
        for train in train_ids
        if str(train) in metric_map
    ]

    if not values:
        return None

    return sum(values)


def parse_result(
    run,
    stem,
):
    if run["timed_out"]:
        return {
            "ok": False,
            "message": (
                "This journey preference took longer than the selected "
                "calculation limit."
            ),
        }

    try:
        data = json.loads(
            run["stdout"]
        )

    except Exception:
        return {
            "ok": False,
            "message": (
                "The journey planner could not read the optimization result."
            ),
        }

    status = str(
        data.get(
            "Result",
            "UNKNOWN",
        )
    ).upper()

    calls = data.get(
        "Call",
        [],
    )

    witnesses = (
        calls[-1].get(
            "Witnesses",
            [],
        )
        if calls
        else []
    )

    if (
        status not in {
            "OPTIMUM FOUND",
            "SATISFIABLE",
        }
        or not witnesses
    ):
        return {
            "ok": False,
            "message": (
                "No valid recommendation was produced for this preference."
            ),
        }

    atoms = witnesses[-1].get(
        "Value",
        [],
    )

    legs = chosen_legs(atoms)
    train_ids = selected_trains(
        atoms,
        legs,
    )

    journey = passenger_metric(
        atoms,
        "passenger_journey_time",
    )

    waiting = passenger_metric(
        atoms,
        "passenger_transfer_wait",
    )

    transfers = passenger_metric(
        atoms,
        "transfer_count",
    )

    turns_map = pair_atoms(
        atoms,
        "turns",
    )

    travel_map = pair_atoms(
        atoms,
        "travel_time",
    )

    if journey is None:
        journey = sum_for_trains(
            travel_map,
            train_ids,
        )

    turns = sum_for_trains(
        turns_map,
        train_ids,
    )

    return {
        "ok": True,
        "journey": journey,
        "waiting": waiting,
        "transfers": transfers,
        "turns": turns,
        "legs": legs,
        "trains": train_ids,
    }


@contextmanager
def active_profile_context(text):
    old = (
        ACTIVE_PROFILE.read_text(
            encoding="utf-8"
        )
        if ACTIVE_PROFILE.exists()
        else None
    )

    ACTIVE_PROFILE.write_text(
        text,
        encoding="utf-8",
    )

    try:
        yield

    finally:
        if old is None:
            if ACTIVE_PROFILE.exists():
                ACTIVE_PROFILE.unlink()

        else:
            ACTIVE_PROFILE.write_text(
                old,
                encoding="utf-8",
            )


def run_simulation(
    stem,
    selected_profile_text,
):
    paths = environment_paths(stem)

    output_dir = (
        REPO
        / "output"
    )

    before = (
        set(output_dir.glob("*"))
        if output_dir.exists()
        else set()
    )

    with active_profile_context(
        selected_profile_text
    ):
        process = subprocess.run(
            backend_python_cmd()
            + [
                "solve.py",
                str(paths["pkl"]),
            ],
            capture_output=True,
            text=True,
            cwd=REPO,
        )

    after = (
        set(output_dir.glob("*"))
        if output_dir.exists()
        else set()
    )

    new_items = sorted(
        after - before,
        key=lambda path: (
            path.stat().st_mtime
        ),
    )

    run_dir = (
        new_items[-1]
        if new_items
        else None
    )

    validation = None
    gif = None

    if run_dir:
        validation_path = (
            run_dir
            / "validation.json"
        )

        if validation_path.exists():
            validation = json.loads(
                validation_path.read_text(
                    encoding="utf-8"
                )
            )

        candidate_gif = (
            run_dir
            / "animation.gif"
        )

        if candidate_gif.exists():
            gif = candidate_gif

    return {
        "process": process,
        "validation": validation,
        "gif": gif,
    }


def show_environment(stem):
    path = environment_paths(stem)[
        "png"
    ]

    if path.exists():
        st.image(
            str(path),
            use_container_width=True,
        )

    else:
        st.info(
            "No preview image is available for this experiment."
        )


def result_value(value):
    return (
        "—"
        if value is None
        else str(value)
    )


def show_result(parsed):
    st.markdown("### Recommended journey")

    cols = st.columns(4)

    cols[0].metric(
        "Journey time",
        result_value(
            parsed.get("journey")
        ),
    )

    cols[1].metric(
        "Waiting",
        result_value(
            parsed.get("waiting")
        ),
    )

    cols[2].metric(
        "Transfers",
        result_value(
            parsed.get("transfers")
        ),
    )

    cols[3].metric(
        "Route turns",
        result_value(
            parsed.get("turns")
        ),
    )

    if parsed.get("legs"):
        st.markdown("#### Journey sequence")

        st.dataframe(
            pd.DataFrame(
                parsed["legs"]
            ),
            use_container_width=True,
            hide_index=True,
        )


def results_are_current(stem):
    if not RESULTS_CSV.exists():
        return False

    environment = environment_paths(stem)

    sources = [
        environment["pkl"],
        environment["lp"],
        environment["scenario"],
    ]

    sources = [
        path
        for path in sources
        if path.exists()
    ]

    if not sources:
        return False

    latest_environment = max(
        path.stat().st_mtime
        for path in sources
    )

    return (
        RESULTS_CSV.stat().st_mtime
        >= latest_environment
    )


def load_results():
    if not RESULTS_CSV.exists():
        return None

    return pd.read_csv(
        RESULTS_CSV
    )


# ============================================================
# Sidebar
# ============================================================

st.sidebar.markdown(
    "## RS42"
)

st.sidebar.caption(
    "Passenger-oriented railway scheduling"
)

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    [
        "Plan a Journey",
        "Compare Preferences",
        "Explore Experiments",
    ],
    label_visibility="collapsed",
)

st.sidebar.divider()

st.sidebar.caption(
    "The interface hides solver implementation details and "
    "shows only journey-level information."
)


# ============================================================
# Header
# ============================================================

st.markdown(
    """
    <div class="rs42-hero">
        <div class="rs42-kicker">Railway Scheduling · Passenger Preferences</div>
        <div class="rs42-title">RS42 Journey Planner</div>
        <p class="rs42-subtitle">
            Explore how travel time, waiting, transfers and route simplicity
            change the recommended railway journey.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Page 1 — Plan
# ============================================================

if page == "Plan a Journey":

    available = available_planner_environments()

    if not available:
        st.error(
            "No passenger environments are currently available."
        )
        st.stop()

    control_col, visual_col = st.columns(
        [0.8, 1.35],
        gap="large",
    )

    with control_col:

        st.markdown("### 1 · Choose an experiment")

        stem = st.selectbox(
            "Experiment",
            available,
            format_func=lambda value: (
                LABELS[value]
            ),
            label_visibility="collapsed",
        )

        st.markdown(
            f"""
            <div class="rs42-card">
                <div class="rs42-card-title">{SHORT_LABELS[stem]}</div>
                <div class="rs42-muted">{DESCRIPTIONS[stem]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### 2 · Choose your priority")

        profile = st.radio(
            "Preference",
            list(
                PROFILE_FILES.keys()
            ),
            format_func=lambda value: (
                PROFILE_LABELS[value]
            ),
            label_visibility="collapsed",
        )

        st.caption(
            PROFILE_DESCRIPTIONS[
                profile
            ]
        )

        custom = st.toggle(
            "Create a custom balance"
        )

        if custom:

            defaults = profile_weights(
                "balanced"
            )

            st.markdown(
                "#### Adjust priorities"
            )

            weights = {}

            for key in WEIGHTS:
                weights[key] = st.slider(
                    WEIGHT_LABELS[key],
                    min_value=0,
                    max_value=20,
                    value=int(
                        defaults.get(
                            key,
                            8,
                        )
                    ),
                )

            selected_profile_path = (
                write_custom_profile(
                    weights
                )
            )

            selected_profile_text = (
                selected_profile_path.read_text(
                    encoding="utf-8"
                )
            )

        else:

            selected_profile_path = (
                PROFILE_FILES[
                    profile
                ]
            )

            selected_profile_text = (
                profile_text(
                    profile
                )
            )

        with st.expander(
            "Run options"
        ):

            validate = st.checkbox(
                "Validate in Flatland after optimization",
                value=False,
            )

            time_limit = st.slider(
                "Maximum calculation time",
                30,
                300,
                120,
                30,
            )

        run_clicked = st.button(
            "Find my journey",
            type="primary",
            use_container_width=True,
        )

    with visual_col:

        st.markdown(
            "### Railway environment"
        )

        show_environment(stem)

        st.markdown(
            f"""
            <div class="rs42-card">
                <div class="rs42-card-title">Question</div>
                <div class="rs42-muted">{QUESTIONS[stem]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if run_clicked:

        with st.spinner(
            "Finding the best journey..."
        ):

            run = run_preference(
                stem,
                selected_profile_path,
                time_limit,
            )

            parsed = parse_result(
                run,
                stem,
            )

        if not parsed["ok"]:

            st.error(
                parsed["message"]
            )

        else:

            st.divider()

            show_result(
                parsed
            )

            if validate:

                with st.spinner(
                    "Checking the journey in Flatland..."
                ):

                    validation_run = run_simulation(
                        stem,
                        selected_profile_text,
                    )

                validation = (
                    validation_run[
                        "validation"
                    ]
                )

                if (
                    validation
                    and validation.get(
                        "success"
                    )
                ):

                    st.success(
                        "The optimized schedule was reproduced successfully in Flatland."
                    )

                    if validation_run[
                        "gif"
                    ]:

                        st.image(
                            str(
                                validation_run[
                                    "gif"
                                ]
                            ),
                            use_container_width=True,
                        )

                else:

                    st.warning(
                        "The simulation did not return a successful validation record."
                    )


# ============================================================
# Page 2 — Compare
# ============================================================

elif page == "Compare Preferences":

    st.markdown(
        "## Compare passenger preferences"
    )

    st.write(
        "See how the predefined preferences change the outcome "
        "within the same railway experiment."
    )

    available = [
        stem
        for stem in ALL_ENVIRONMENTS
        if environment_available(stem)
    ]

    if not available:
        st.warning(
            "No evaluation environments are available."
        )
        st.stop()

    stem = st.selectbox(
        "Experiment",
        available,
        format_func=lambda value: (
            LABELS[value]
        ),
    )

    left, right = st.columns(
        [1.15, 1],
        gap="large",
    )

    with left:
        show_environment(stem)

    with right:

        st.markdown(
            f"### {SHORT_LABELS[stem]}"
        )

        st.write(
            DESCRIPTIONS[stem]
        )

        st.markdown(
            "#### Evaluation focus"
        )

        for item in FOCUS[stem]:
            st.write(
                f"• {item}"
            )

    results = load_results()

    st.divider()

    if results is None:

        st.info(
            "No saved evaluation results are available yet."
        )

    elif not results_are_current(
        stem
    ):

        st.info(
            "This environment has changed since the saved evaluation was generated. "
            "Run the final evaluation again before showing comparison values."
        )

    else:

        rows = results[
            results[
                "environment"
            ]
            == stem
        ].copy()

        if rows.empty:

            st.info(
                "No saved results are available for this experiment."
            )

        else:

            profile_column = (
                "profile_label"
                if "profile_label"
                in rows.columns
                else "profile"
            )

            display = pd.DataFrame()

            display[
                "Preference"
            ] = rows[
                profile_column
            ].replace(
                {
                    "comfort": "Simple Journey",
                    "simple": "Simple Journey",
                    "fastest": "Fastest",
                    "least_waiting": "Less Waiting",
                    "fewest_transfers": "Fewer Transfers",
                    "balanced": "Balanced",
                }
            )

            mapping = [
                (
                    "journey_time",
                    "Journey time",
                ),
                (
                    "transfer_wait",
                    "Waiting",
                ),
                (
                    "transfers",
                    "Transfers",
                ),
                (
                    "turns",
                    "Route turns",
                ),
            ]

            for source, target in mapping:
                if source in rows.columns:
                    display[
                        target
                    ] = rows[
                        source
                    ]

            st.dataframe(
                display,
                use_container_width=True,
                hide_index=True,
            )

            numeric = [
                column
                for column in [
                    "Journey time",
                    "Waiting",
                    "Transfers",
                    "Route turns",
                ]
                if (
                    column
                    in display.columns
                    and pd.to_numeric(
                        display[column],
                        errors="coerce",
                    )
                    .notna()
                    .any()
                )
            ]

            if (
                numeric
                and stem
                != "e6_shared_conflict"
            ):

                chart = (
                    display[
                        [
                            "Preference"
                        ]
                        + numeric
                    ]
                    .set_index(
                        "Preference"
                    )
                )

                st.markdown(
                    "### Outcome comparison"
                )

                st.bar_chart(
                    chart
                )


# ============================================================
# Page 3 — Explore experiments
# ============================================================

else:

    st.markdown(
        "## Experimental environments"
    )

    st.write(
        "Each setup targets a different passenger or infrastructure question. "
        "The environments increase from controlled preference tests to a larger "
        "mixed-preference network and finally shared-infrastructure validation."
    )

    selected = st.selectbox(
        "Choose an experiment to inspect",
        ALL_ENVIRONMENTS,
        format_func=lambda value: (
            LABELS[value]
        ),
    )

    st.divider()

    left, right = st.columns(
        [1.3, 1],
        gap="large",
    )

    with left:

        show_environment(
            selected
        )

    with right:

        st.markdown(
            f"## {LABELS[selected]}"
        )

        st.write(
            DESCRIPTIONS[
                selected
            ]
        )

        st.markdown(
            "### What it evaluates"
        )

        for item in FOCUS[
            selected
        ]:
            st.write(
                f"• {item}"
            )

        st.markdown(
            "### Main question"
        )

        st.write(
            QUESTIONS[
                selected
            ]
        )

        if (
            selected
            == "e5_mixed_preferences"
        ):

            st.success(
                "E5 now uses the real Flatland Test_02 Level_8 rail topology "
                "with a selected subset of services for the mixed-preference experiment."
            )

        if (
            selected
            == "e6_shared_conflict"
        ):

            st.info(
                "E6 is not primarily a passenger-choice experiment. "
                "It checks execution on shared railway infrastructure."
            )

    st.divider()

    st.markdown(
        "### Experiment overview"
    )

    overview_cols = st.columns(3)

    overview = [
        (
            "E1–E3",
            "Controlled trade-offs",
            "Travel time, transfers and waiting are tested separately.",
        ),
        (
            "E4–E5",
            "Combined journey choices",
            "Route simplicity and multiple passenger priorities are evaluated.",
        ),
        (
            "E6",
            "Execution robustness",
            "The optimized plan is checked in a shared multi-train environment.",
        ),
    ]

    for column, (
        title,
        subtitle,
        body,
    ) in zip(
        overview_cols,
        overview,
    ):

        with column:
            st.markdown(
                f"""
                <div class="rs42-card">
                    <div class="rs42-card-title">{title} · {subtitle}</div>
                    <div class="rs42-muted">{body}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
