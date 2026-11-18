# Recommended V4 reports

Run `RESEARCH_AND_MODEL_REPORT.bat` (or `VIEW_REPORT.bat`). The output separates **lifetime history** from **current comparable results**. `training_current_summary.csv` contains per-stage rolling 100/500 and latest-session train/held-out success. The existing `training_summary.csv` remains an explicitly historical CSV for backward compatibility. `training_report.md` and `.json` show both, as well as scoring-generation counts and V4 candidate-specific certification. No old data is deleted or rewritten.

`CHECK_LIVE_SKILLS.bat` reports V4 candidate status and fallbacks. V4 held-out sessions are variants within one arena, **not** a separate-map generalization result.

# Reports

Run `VIEW_REPORT.bat` after training. This reads local real-trial logs and writes under `reports/generated/`:

- **training_report.md**: readable performance summary, stage-by-stage early vs recent success rates, confidence ranges, dominant failure reasons and engineering recommendations.
- **training_summary.csv**: per-stage data for Excel, plotting or further analysis.
- **training_report.json**: full machine-readable snapshot (including learned action choices).

The summaries use observed trials only and cannot establish improvement without a meaningful number of examples. Compare at least ~30 trials for basic troubleshooting and verify policy changes on held-out stages, not just the same five courses.

The generated output is local and not version controlled. No made-up training progress is packaged with this release.

## Strategic progress

Run `STRATEGY_REPORT.bat` to inspect Hunter/Runner tactical feedback and optional Mine AI MCP tool-use research counts from `runtime/strategy/`. Separation change is only an exploratory heuristic and must not be interpreted as a model benchmark or final win rate.
