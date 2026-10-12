---
name: render
description: Renders an existing tour-spec.json to a single-file interactive HTML guide via the bundled Node renderer. Use when the user has hand-edited a tour-spec.json, when learning-guide:analyze hands off after drafting, or when the user explicitly asks to "render the tour", "regenerate the HTML", or "update the embedded sources". Idempotent for generated artifacts; preserves user-edited README and tour-spec.json.
---

# Render HTML

Take a `tour-spec.json` and produce a single-file `index.html` with the bundled `scripts/render.cjs`.

Locate this installed `SKILL.md` through the current host's skill metadata or file tools. Resolve `../..` from its directory to get the absolute plugin root. Replace `<absolute-plugin-root>` below with that path and verify `scripts/render.cjs` exists before running it. If the resource is unavailable, report the missing path and stop; do not assume a host environment variable supplies it.

## Trigger phrases

- "render the tour"
- "regenerate the HTML"
- "update the embedded sources"
- Auto-dispatched at the end of `learning-guide:analyze`

## Inputs

- **Spec path** — `tour-spec.json` location. Default: CWD; explicit path supported.
- **Output directory** — defaults to the spec's parent dir.

## Steps

1. **Locate the spec.** If the user provides a path, use it. Otherwise look for `tour-spec.json` in CWD. If neither, ask the user where the spec is. Do NOT scan the entire repository.

2. **Confirm Node is available.** Run `node --version`. If exit code is non-zero, tell the user Node.js must be on PATH and stop. Do not attempt fallback rendering.

3. **Inspect overrides.** Look for `<spec-dir>/.learning-guide/template.html`. If present, ensure `tour-spec.renderer.template_compatibility_version` matches the `<!-- template_compatibility_version: N -->` declaration on the override's first line. If missing or mismatched, ask the user to fix it before rendering.

4. **Run the renderer.**
   ```bash
   node "<absolute-plugin-root>/scripts/render.cjs" "<absolute-spec-path>"
   ```
   If `--output-dir` is needed, pass it explicitly.

5. **Surface output.** On success, print the renderer's stdout summary verbatim. On non-zero exit, print stderr verbatim and offer the troubleshooting table from `references/renderer-cli.md`.

6. **Confirm artifacts.** Verify `index.html` and `README.md` exist with non-zero size. If anything expected is missing, surface the discrepancy — do not retry blindly.

## Re-running from the shell

The user can re-render from the shell by running `node "<absolute-plugin-root>/scripts/render.cjs" "<absolute-spec-path>"` with the resolved paths.

## When NOT to use this skill

- The user wants new content, not a re-render. Dispatch `learning-guide:analyze` instead.
- The spec does not exist yet. Dispatch `learning-guide:analyze`.

## References

- `references/renderer-cli.md` — flags, exit codes, troubleshooting.
- `references/browser-compatibility.md` — `file://` constraints.
