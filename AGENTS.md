# Workflow Orchestration

## 0. Overview
- Always work in english, even if communitation is in another language. This ensures consistency and clarity.

## 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don’t keep pushing
- Write plan mode for verification step, not just building
- Write detailed success criteria to reduce ambiguity
- Always ask before going into implementation mode — never assume you know the right way to do something without checking

## 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

## 3. Self-Improvement Loop
- After ANY correction from the user, update `doc/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

## 4. Verification Before Done
- Never mark a task complete without proving it works
- Ask yourself: “Would a smart engineer disagree with relevant evidence?”
- Drift prevention: build a safety review process then test it
- Run tests, check logs, demonstrate correctness

## 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask “is there a more elegant way?”
- But fix first, refine second — don’t over-engineer
- Simplicity beats cleverness if both solve the problem

## 6. Autonomous Bug Fixing
- When a bug appears, don’t stop at fix. Don’t ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go the failing CI tests without being told how

## 7. Task Management & Documentation
1. **Plan First**: For multi-step work, write a plan to `doc/todo/YYYY-MM-DD-HH-MM-STUB-NAME-FOR-PROBLEM-DESCRIPTION.md` with checkable items. The `HH-MM` is when the file is first created (24h, local time) — needed because several docs often land in the same commit, and commit order alone doesn't reveal which task actually happened first.
2. **Verify Planner**: Check before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: Write concise commit-style summaries
5. **Document Results**: Write up what shipped — narrative summary, decisions made, and verification evidence — directly in `doc/done/YYYY-MM-DD-HH-MM-STUB-NAME-FOR-PROBLEM-DESCRIPTION.md` (same `HH-MM`-in-filename rule as above). If the work started from a `doc/todo/` plan, move that file to `doc/done/` (renaming to add `HH-MM` if it didn't already have it) and add the write-up as its Review section; if the work was ad-hoc (no todo doc), create the `doc/done/` entry directly. Every file's second line must be `**Created:** YYYY-MM-DD HH:MM`, matching the filename, so the timestamp is visible without decoding the filename. `doc/done/` is the single record of completed work — there is no separate blog directory.
6. **Capture Lessons**: Update `doc/lessons.md` after corrections

## 8. Deployment Model
- This local repository is the single source of truth
- All changes are made here, locally, first — never edit files directly on the server
- Changes are deployed to apished.com via rsync
- Code is only run/tested on apished.com after being rsynced there

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Assumptions**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what’s necessary. Avoid introducing bugs.
