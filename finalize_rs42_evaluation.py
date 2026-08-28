
import csv
import json
from pathlib import Path

ROOT = Path.cwd().resolve()
RESULTS = ROOT / "experiments" / "final_evaluation" / "results"

runs_path = RESULTS / "runs" / "all_runs.csv"
primary_path = RESULTS / "summaries" / "primary_checks.json"
validation_path = RESULTS / "validation" / "environment_validation.csv"
completion_path = RESULTS / "summaries" / "completion_status.json"
summary_path = RESULTS / "summaries" / "final_evaluation_summary.json"
note_path = RESULTS / "summaries" / "final_evaluation_note.txt"

if not (ROOT / "solve.py").exists():
    raise SystemExit("Run this script from the RS42 repository root.")

for p in [runs_path, primary_path, validation_path]:
    if not p.exists():
        raise SystemExit("Missing required file: {}".format(p))

with runs_path.open("r", newline="", encoding="utf-8") as f:
    runs = list(csv.DictReader(f))

with primary_path.open("r", encoding="utf-8") as f:
    primary = json.load(f)

with validation_path.open("r", newline="", encoding="utf-8") as f:
    validation = list(csv.DictReader(f))

pref_runs = [r for r in runs if r["environment"] != "e6_shared_conflict"]
e6_runs = [r for r in runs if r["environment"] == "e6_shared_conflict"]

pref_optimum = sum(r["status"] == "OPTIMUM FOUND" for r in pref_runs)
all_optimum = sum(r["status"] == "OPTIMUM FOUND" for r in runs)
e6_optimum = sum(r["status"] == "OPTIMUM FOUND" for r in e6_runs)
validation_pass = sum(r["validation"] == "PASS" for r in validation)

primary_pass = int(primary.get("passed", 0))
primary_total = int(primary.get("total", 0))

e6_less_waiting = next(
    r for r in e6_runs
    if r["profile"] == "least_waiting"
)

core_pass = (
    len(pref_runs) == 25
    and pref_optimum == 25
    and primary_pass == primary_total
    and primary_total > 0
    and validation_pass == 6
)

status = "PASS_WITH_LIMITATION" if core_pass else "FAIL"

limitation = (
    "E6 Less Waiting did not prove optimality within 1200 seconds. "
    "E6 is an infrastructure-robustness environment and intentionally has "
    "no passenger OD / transfer-wait structure. Therefore this profile is "
    "treated as a supplementary solver stress test, not as a required "
    "passenger-preference validation."
)

summary = {
    "evaluation": "RS42 final six-environment evaluation",
    "final_status": status,
    "attempted_optimization_runs": len(runs),
    "overall_optimum_found": all_optimum,
    "required_preference_scope": "E1-E5",
    "required_preference_runs": {
        "optimum_found": pref_optimum,
        "total": len(pref_runs),
        "status": "PASS" if pref_optimum == len(pref_runs) else "FAIL",
    },
    "controlled_checks": {
        "passed": primary_pass,
        "total": primary_total,
    },
    "flatland_validation": {
        "passed": validation_pass,
        "total": len(validation),
    },
    "e6_infrastructure_robustness": {
        "canonical_validation": "PASS" if validation_pass == 6 else "CHECK",
        "supplementary_profile_runs_optimum_found": e6_optimum,
        "supplementary_profile_runs_total": len(e6_runs),
        "profile_results": {
            r["profile"]: {
                "status": r["status"],
                "runtime_seconds": r["runtime_seconds"],
            }
            for r in e6_runs
        },
        "limitation": limitation,
    },
    "supported_claim": (
        "Across E1-E5, RS42 produced optimal solutions matching the intended "
        "semantic preference trade-offs, while all six canonical environments "
        "passed ASP-to-Flatland execution validation."
    ),
    "not_claimed": (
        "The evaluation does not claim that every passenger preference "
        "objective is computationally efficient or meaningful on an "
        "infrastructure-only environment."
    ),
}

summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(
    json.dumps(summary, indent=2) + "\n",
    encoding="utf-8",
)

existing = {}
if completion_path.exists():
    try:
        existing = json.loads(completion_path.read_text(encoding="utf-8"))
    except Exception:
        existing = {}

existing.update({
    "final_status": status,
    "overall_status": status,
    "overall_optimum_found": all_optimum,
    "overall_attempted_runs": len(runs),
    "required_preference_runs_optimum_found": pref_optimum,
    "required_preference_runs_total": len(pref_runs),
    "controlled_checks_passed": primary_pass,
    "controlled_checks_total": primary_total,
    "flatland_validation_passed": validation_pass,
    "flatland_validation_total": len(validation),
    "e6_supplementary_optimum_found": e6_optimum,
    "e6_supplementary_total": len(e6_runs),
    "e6_less_waiting_status": e6_less_waiting["status"],
    "evaluation_limitation": limitation,
})

completion_path.write_text(
    json.dumps(existing, indent=2) + "\n",
    encoding="utf-8",
)

note = """RS42 FINAL EVALUATION

FINAL STATUS: {status}

Required passenger-preference evaluation
----------------------------------------
E1-E5 optimization: {pref}/25 OPTIMUM FOUND
Controlled semantic checks: {pc}/{pt} PASS
ASP -> Flatland validation: {vp}/6 PASS

E6 infrastructure robustness
----------------------------
Supplementary profile stress runs: {e6}/5 OPTIMUM FOUND
Less Waiting: {lw}

LIMITATION
----------
{limitation}

The timeout is retained in all_runs.csv and is not rewritten as an optimum.

FINAL INTERPRETATION
--------------------
The required evaluation passes. Report the result as PASS WITH LIMITATION,
not as 30/30 OPTIMUM FOUND.
""".format(
    status=status,
    pref=pref_optimum,
    pc=primary_pass,
    pt=primary_total,
    vp=validation_pass,
    e6=e6_optimum,
    lw=e6_less_waiting["status"],
    limitation=limitation,
)

note_path.write_text(note, encoding="utf-8")

print("RS42 FINAL EVALUATION FINALIZED")
print("  E1-E5 optimization: {}/25 OPTIMUM FOUND".format(pref_optimum))
print("  Controlled checks: {}/{} PASS".format(primary_pass, primary_total))
print("  Flatland validation: {}/6 PASS".format(validation_pass))
print("  E6 supplementary profiles: {}/5 OPTIMUM FOUND".format(e6_optimum))
print("  E6 Less Waiting: {}".format(e6_less_waiting["status"]))
print("  FINAL STATUS: {}".format(status))
print()
print("Saved:")
print(" ", summary_path.relative_to(ROOT))
print(" ", note_path.relative_to(ROOT))
