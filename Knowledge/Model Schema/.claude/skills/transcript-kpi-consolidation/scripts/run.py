"""Orchestrate the transcript-kpi-consolidation skill (STEPS 2-4).

Usage:  python run.py {TICKER}

Runs build_transcript_tabs.py -> build_kpi_sheet.py -> audit_kpi_sheet.py.
STEP 1 (extract digests) must already be done: one digest JSON per transcript
in Ticker Libraries/{TICKER}/MDA and Other/transcript_digests/  (see SKILL.md
STEP 1 + data/schema.md).
"""
import os, sys, subprocess

if len(sys.argv) < 2:
    sys.exit("usage: python run.py {TICKER}")
TICKER = sys.argv[1].upper()
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_SCHEMA = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DIGESTS = os.path.join(MODEL_SCHEMA, "Ticker Libraries", TICKER, "MDA and Other",
                       "transcript_digests")

if not os.path.isdir(DIGESTS) or not [f for f in os.listdir(DIGESTS)
                                      if f.endswith('.json')]:
    sys.exit(f"STEP 1 not done — no digest JSONs at:\n  {DIGESTS}\n"
             "Extract one digest per transcript first (SKILL.md STEP 1 + data/schema.md).")

for script in ("build_transcript_tabs.py", "build_kpi_sheet.py", "audit_kpi_sheet.py"):
    print(f"\n=== {script} {TICKER} ===")
    rc = subprocess.run([sys.executable, os.path.join(HERE, script), TICKER]).returncode
    if rc != 0:
        sys.exit(f"{script} failed (exit {rc})")
print(f"\n[{TICKER}] transcript-kpi-consolidation complete.")


if __name__ == "__main__":
    pass
