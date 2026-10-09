"""
Feedback Generation Service (Section 6.1, Section 9.8).

Split by responsibility so the deterministic half stays testable independently
of the LLM half — Section 9.8 step 5 is explicit that "LLM handles qualitative
content, deterministic code handles the score":

- `transcript_signals` — text-derivable communication signals (Section 9.7)
- `scoring`            — Section 10.2's weighted formulas, skip-aware
- `prompts`            — the grounded prompt + JSON schema (Section 9.8 step 3)
- `narrative`          — deterministic narrative when no provider is available
- `generator`          — the pipeline that ties them together and persists
- `exports`            — transcript TXT/JSON and PDF report (Section 7.4)
- `comparison`         — Before & After against a prior attempt (Section 4.11A)
"""
