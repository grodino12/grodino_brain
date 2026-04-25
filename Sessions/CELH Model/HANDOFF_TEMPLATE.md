---
type: handoff-template
purpose: Tight handoff format for end-of-session writes. Cuts live-folder context cost ~5x vs. prior verbose style.
---

# Handoff Template

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`.

**Target length: ~800–1200 words; hard ceiling 1500.** A cold-start reader should be able to act from this alone — no re-asking.

## Structure (9 sections)

1. **YAML frontmatter** — `type: session-handoff`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro** — prior handoff reference + one sentence on what this session did + one sentence on what the next session should do.
4. **Starting state** — 3–5 bullets. Just enough to anchor the diff.
5. **Work done this session** — numbered `### N.` subsections grouped by subsystem. **Why over what.** The diff shows what.
6. **Current state** — bullet list, one line per subsystem. Numbers and status.
7. **Open decisions / pending work** — numbered, 1–2 lines each. Include any active propagating rules (e.g. playground-sync). Flag unresolved user questions.
8. **Key file paths** — two-column table. Absolute paths. Load-bearing files only.
9. **How to create the next handoff** — link to this file. Don't paste it verbatim into every handoff.

## Consolidation rules

- Don't list every library entry / ledger row added — cite file + count + non-obvious decisions.
- Don't re-explain code. Reference by function/file name.
- Reverted exploration: one line.
- Memory rules referenced not duplicated — say "per `feedback_X.md`".
- No "design rationale" walkthroughs. Rationale belongs in commit messages or the roadmap, not in every handoff.
- "Starting state" should be a delta-anchor, not a recap of the prior handoff's "current state" — link to the prior handoff for full context.

## Folder hygiene

- After ~5 live handoffs accumulate, move older ones to `Handoffs/Archive/`. Live folder is for resumption fuel; archive is for history.
- ROADMAP.md is the cross-session source of truth — update it after each session, not in the handoff narrative.
