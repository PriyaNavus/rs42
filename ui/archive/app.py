# ui for team rs42 passenger convenience planner
# run from repo root:  streamlit run ui/app.py
#
# what it does:
# 1. user picks a profile or moves the sliders
# 2. we write the weights into asp/profiles/active_profile.lp
# 3. solve either with plain clingo (quick check, shows metrics)
#    or with solve.py (full flatland animation)
#
# active_profile.lp must be listed in asp/params.py primary,
# that is how the choice actually reaches the solver.

import re
import shutil
import subprocess
import sys
from pathlib import Path

import streamlit as st

# repo root = one folder above ui/
REPO = Path(__file__).resolve().parents[1]

PROFILE_DIR = REPO / "asp" / "profiles"
ACTIVE_PROFILE = PROFILE_DIR / "active_profile.lp"

# the encodings, hardcoded on purpose so it is easy to read
ENCODINGS = [
    "asp/custom/connection.lp",
    "asp/custom/encoding.lp",
    "asp/custom/generated_waypoints.lp",
    "asp/custom/waypoint.lp",
    "asp/custom/passenger_transfer.lp",
    "asp/custom/visual.lp",
]

# the five weights every profile must define
WEIGHTS = ["w_arrival", "w_wait", "w_transfer", "w_turn", "w_waypoint"]

# short labels for the sliders
LABELS = {
    "w_arrival": "early arrival",
    "w_wait": "little waiting",
    "w_transfer": "few transfers",
    "w_turn": "few turns (comfort)",
    "w_waypoint": "early stops",
}


def read_profile(path):
    # parse '#const w_x = 5.' lines into a dict
    values = {}
    for name, num in re.findall(r"#const\s+(\w+)\s*=\s*(\d+)\s*\.", path.read_text()):
        values[name] = int(num)
    return values


def list_profiles():
    # every profile_*.lp in asp/profiles, name without prefix
    profiles = {}
    for f in sorted(PROFILE_DIR.glob("profile_*.lp")):
        name = f.stem.replace("profile_", "")
        profiles[name] = read_profile(f)
    return profiles


def write_active_profile(weights):
    # write the chosen weights so params.py picks them up
    lines = [f"#const {w} = {weights[w]}." for w in WEIGHTS]
    ACTIVE_PROFILE.write_text("\n".join(lines) + "\n")


def run_clingo(env_lp, time_limit):
    # quick check without flatland: solve and show the metrics
    # extra #show lines so we can read the numbers from the output
    show_file = REPO / "ui" / "show_metrics.lp"
    show_file.write_text(
        "#show cost/3.\n#show arrival/2.\n#show waiting_time/2.\n"
        "#show turns/2.\n#show transfer_count/2.\n"
    )
    # use the clingo binary if installed, else the python module
    clingo_cmd = ["clingo"] if shutil.which("clingo") else [sys.executable, "-m", "clingo"]
    cmd = (
        clingo_cmd + [str(env_lp)]
        + [str(REPO / e) for e in ENCODINGS]
        + [str(ACTIVE_PROFILE), str(show_file), f"--time-limit={time_limit}"]
    )
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    return result.stdout + result.stderr


def parse_clingo_output(text):
    # grab the last answer set and the optimization value
    answers = re.findall(r"Answer: \d+\n(.*?)\n", text, re.DOTALL)
    opt = re.findall(r"Optimization: (.+)", text)
    last = answers[-1] if answers else ""
    atoms = last.split() if last else []
    metrics = [a for a in atoms if not a.startswith("action(")]
    actions = [a for a in atoms if a.startswith("action(")]
    return metrics, actions, (opt[-1] if opt else None)


st.set_page_config(page_title="rs42 convenience planner", page_icon=None)
st.title("rs42 passenger convenience planner")
st.caption("pick what matters for the ride, we find the schedule")

# --- step 1: profile or custom sliders -------------------------------
profiles = list_profiles()
# don't offer the active profile as a choice, it is the output
profiles.pop("active", None)

choice = st.radio(
    "preference profile",
    list(profiles.keys()) + ["custom"],
    horizontal=True,
)

if choice != "custom":
    base = profiles[choice]
else:
    # custom starts from balanced if it exists, else mid values
    base = profiles.get("balanced", {w: 8 for w in WEIGHTS})

st.write("weights (bigger = matters more)")
weights = {}
cols = st.columns(len(WEIGHTS))
for col, w in zip(cols, WEIGHTS):
    with col:
        weights[w] = st.slider(
            LABELS[w], 0, 25, base.get(w, 5),
            disabled=(choice != "custom"),
        )

# when a fixed profile is picked, use its values, not the sliders
if choice != "custom":
    weights = {w: base.get(w, 5) for w in WEIGHTS}

# --- step 2: environment and mode ------------------------------------
lp_envs = sorted((REPO / "envs" / "lp").glob("*.lp"))
pkl_envs = sorted((REPO / "envs" / "pkl").glob("*.pkl"))

mode = st.radio(
    "how to solve",
    ["quick check (clingo only)", "full animation (solve.py)"],
    horizontal=True,
)

if mode.startswith("quick"):
    env = st.selectbox("environment", lp_envs, format_func=lambda p: p.name)
    time_limit = st.number_input("time limit in seconds", 5, 600, 60)
else:
    env = st.selectbox("environment", pkl_envs, format_func=lambda p: p.name)

# --- step 3: run ------------------------------------------------------
if st.button("solve", type="primary"):
    write_active_profile(weights)
    st.code("\n".join(f"#const {w} = {weights[w]}." for w in WEIGHTS))

    if mode.startswith("quick"):
        with st.spinner("clingo is solving..."):
            output = run_clingo(env, time_limit)
        if "UNSATISFIABLE" in output:
            st.error("unsatisfiable, no schedule exists for this setup")
        else:
            metrics, actions, opt = parse_clingo_output(output)
            if opt:
                st.success(f"optimization value: {opt}")
            if metrics:
                st.write("metrics of the best schedule found:")
                st.code("\n".join(sorted(metrics)))
            with st.expander("actions (the schedule)"):
                st.code("\n".join(sorted(actions)) or "no actions parsed")
        with st.expander("raw clingo output"):
            st.text(output)
    else:
        # remember which output folders exist before the run, so we can
        # find the new one afterwards (solve.py names it by timestamp)
        output_dir = REPO / "output"
        before = set(output_dir.glob("*")) if output_dir.exists() else set()

        with st.spinner("running solve.py, this can take a while..."):
            result = subprocess.run(
                ["python", "solve.py", str(env)],
                capture_output=True, text=True, cwd=REPO,
            )

        if result.returncode != 0:
            st.error("solve.py failed, stderr below")
            st.text(result.stderr[-3000:])
        else:
            after = set(output_dir.glob("*")) if output_dir.exists() else set()
            new_dirs = sorted(after - before, key=lambda p: p.stat().st_mtime)
            gif_path = None
            if new_dirs:
                candidate = new_dirs[-1] / "animation.gif"
                if candidate.exists():
                    gif_path = candidate
            if gif_path:
                st.success("done, here is the schedule")
                st.image(str(gif_path))
            else:
                st.warning(
                    "solve.py finished but no animation.gif was found in "
                    "output/. showing the raw log instead."
                )
        with st.expander("solve.py log"):
            st.text(result.stdout[-3000:])
