# v0.7.14.1: Windows report-test encoding fix

This is a test-only hotfix for Windows installations where the system default text encoding is cp1252.

## Symptom

`test_full_multi_skill_report_and_guidance` fails when checking `Early → recent`, because `Path.read_text()` without an explicit encoding decodes the UTF-8 report as cp1252 (`Early â†’ recent`).

## Changes

- Read generated Markdown and CSV with `encoding='utf-8'` in report tests.
- Add a UTF-8 bytes decode assertion on the generated report.
- No gameplay, arena, models, or data formats have been changed.
- Output files remain UTF-8 (unchanged).

## Upgrade

If v0.7.14 is running fine, either apply the two-line test change in `quickstart/tests/test_v079_multiskill.py`, or extract this source build to a new folder and restore your runtime folders. Do not overwrite saved training logs.

This fix does not claim live Minecraft validation.
