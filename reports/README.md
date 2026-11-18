# Current reports

Launch `RESEARCH_AND_MODEL_REPORT.bat` to write the following to `reports/generated/`:

- `training_report.md`: stage results, diagnostics, failure reasons and suggested improvements.
- `training_report.json`: structured diagnostic report and policies.
- `training_current_summary.csv`: comparable rolling 100/500 and latest-session train/held-out results.
- `training_summary.csv`: lifetime historical results, including earlier scoring generations.

`CHECK_LIVE_SKILLS.bat` is read-only and shows policy gates and fallbacks. `STRATEGY_REPORT.bat` summarizes local tactical feedback and imported Mine AI research counts. Neither cumulative success nor same-arena validation proves performance on an unseen map.

Outputs are generated locally. No test observations, reports or live model data are shipped.
