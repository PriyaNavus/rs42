# Final evaluation run data

`all_runs.csv` is the canonical 30-run E1–E6 dataset used by the final report,
`../summaries/primary_checks.json`, and `../summaries/final_evaluation_summary.json`. Run
`python tools/final_evaluation/recheck_semantics.py` from the repository root to
recompute the 10 relational checks from this CSV.

The earlier E1–E3 refresh output is retained for history at
`../../_archive/fresh_e1_e2_e3_runs_pre_final.csv`. It contains pre-final
environment results and must not be used to check the final report. Running
The historical `tools/legacy_root_scripts/refresh_final_evaluation_15.py`
may generate a new `fresh_e1_e2_e3_runs.csv`
here; that intermediate output is also not a replacement for `all_runs.csv`.
