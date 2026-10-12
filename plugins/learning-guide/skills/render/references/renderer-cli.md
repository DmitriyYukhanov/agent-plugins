# Renderer CLI

The renderer is the bundled `scripts/render.cjs`. It uses Node's standard library and needs no `npm install`.

Resolve the absolute plugin root from the installed skill location as described in [SKILL.md](../SKILL.md). Replace `<absolute-plugin-root>` in these commands with that path, verify the renderer exists, and use quoted absolute spec and output paths. These examples require no host environment variable.

## Usage

```bash
node "<absolute-plugin-root>/scripts/render.cjs" "<absolute-spec-path>" [--output-dir "<absolute-output-dir>"]
```

- `<absolute-spec-path>` is the required path to a valid tour spec.
- `--output-dir "<absolute-output-dir>"` defaults to the spec file's parent directory.

## Exit codes

- `0` — success. Prints a single-line summary to stdout.
- `1` — failure. Prints reason(s) to stderr.

## Common failures and fixes

| Stderr message contains | Cause | Fix |
|---|---|---|
| `not found` | spec path is wrong | confirm with `ls` |
| `invalid JSON` | spec is malformed | run `node -e "JSON.parse(require('fs').readFileSync(...))"` |
| `does not match pattern` | field violates schema | inspect the path in the error and consult `assets/tour-spec.schema.json` |
| `outside project root` | `embedded_sources[].path` resolves outside the spec's parent dir (including via a symlink) | move the source under the spec's directory OR widen with `.learning-guide/policy.json` `{"project_root":"<rel>"}` |
| `template_compatibility_version` | user `template.html` override mismatched | update `tour-spec.renderer.template_compatibility_version` to match the value in `<!-- template_compatibility_version: N -->` at the top of the override |
| `schema_version` | spec uses an unsupported major version | regenerate via `analyze` or upgrade/downgrade the plugin |
| `payload` | inlined content exceeds `max_inline_payload_kb` | soft warning only. Mermaid loads from a CDN rather than being inlined, so this measures content + embedded sources — trim oversized embedded sources or raise the cap |

Diagrams blank in the browser? The tour loads Mermaid from jsdelivr, so a reader with no
network sees the diagram source and nothing drawn. Everything else in the tour still works.
Set `renderer.include_mermaid: false` to render without diagrams at all.

## Quick recipes

- Re-render after editing the spec:
  ```bash
  node "<absolute-plugin-root>/scripts/render.cjs" "<absolute-spec-path>"
  ```
- Render to a different output directory:
  ```bash
  node "<absolute-plugin-root>/scripts/render.cjs" "<absolute-spec-path>" --output-dir "<absolute-output-dir>"
  ```
- Force-disable Mermaid even if a diagram is present: set `renderer.include_mermaid` to `false` in the spec.
