---
name: unity-tests-run
description: Run Unity Test Framework tests via CLI batchmode with auto-detection of Unity installation
---

# Run Unity tests

Use the current host's file and command tools. Read [unity-run](../unity-run/SKILL.md) for Unity discovery and batchmode constraints.

1. Read the applicable project instructions, including `AGENTS.md`. Locate the project root containing `ProjectSettings/ProjectVersion.txt`; use the user's explicit project path when provided.
2. Take the test platform from the user's request, defaulting to `EditMode`. Include a category or filter only when the user specifies it.
3. Resolve `../../scripts/run-unity-tests.sh` relative to this installed `SKILL.md` directory. Verify the script exists and use its absolute, quoted path:

   ```bash
   bash "<absolute-plugin-root>/scripts/run-unity-tests.sh" --project-path "<absolute-project-root>" --platform EditMode
   ```

   Replace both paths and the platform with the resolved values. Append `--category "<category>"` or `--filter "<filter>"` only when supplied. Run the script synchronously; allow up to ten minutes and keep the user informed through the host's progress mechanism.
4. Report the script's total, passed, failed, skipped, and duration values. Include failed test names and messages. Preserve failure diagnostics; an unavailable editor or runner is `NOT CHECKED`, not a pass.

If the host supports delegation, you may give a bounded worker this procedure, the project path, selected filters, and original request. Otherwise, run it directly. Never require a named agent or a host-specific argument placeholder.
