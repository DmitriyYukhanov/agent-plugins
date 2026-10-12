#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { validate } = require('./validator.cjs');
const md = require('./markdown.cjs');

const PLUGIN_ROOT = path.resolve(__dirname, '..');
const ASSETS = path.join(PLUGIN_ROOT, 'assets');

// Mermaid loads from a pinned CDN in the reader's browser; it is neither vendored nor
// inlined, which is what keeps a tour ~50 KB instead of 3.3 MB. A tour therefore needs
// network access to draw its diagrams (everything else in it works offline).
//
// The init call is this project's own snippet, not upstream mermaid's, and it is a
// SEPARATE classic script: classic scripts run in document order, so it is guaranteed to
// see the global the tag above defines. 11.x moves the API to `mermaid.default` and would
// silently no-op this guard, so DO NOT bump MERMAID_VERSION without rewriting the snippet
// and recomputing MERMAID_SRI (see assets/THIRD_PARTY.md).
//
// SRI, because this injects a third-party script into the reader's page: the hash pins the
// exact bytes, so a compromised or swapped CDN file refuses to execute rather than running
// whatever arrived. Recompute it with:
//   openssl dgst -sha384 -binary mermaid.min.js | openssl base64 -A
const MERMAID_VERSION = '10.9.1';
const MERMAID_CDN_URL = `https://cdn.jsdelivr.net/npm/mermaid@${MERMAID_VERSION}/dist/mermaid.min.js`;
const MERMAID_SRI = 'sha384-WmdflGW9aGfoBdHc4rRyWzYuAjEmDwMdGdiPNacbwfGKxBW/SO6guzuQ76qjnSlr';
const MERMAID_INIT = 'if(typeof mermaid!=="undefined"&&mermaid.initialize){mermaid.initialize({startOnLoad:true,securityLevel:"strict",theme:"default"});}';
const MERMAID_BLOCK =
  `<script src="${MERMAID_CDN_URL}" integrity="${MERMAID_SRI}" crossorigin="anonymous"></script>\n` +
  `<script>${MERMAID_INIT}</script>`;

function die(msg, code) { process.stderr.write(msg + '\n'); process.exit(code || 1); }
function warn(msg) { process.stderr.write(msg + '\n'); }

// Shape-agnostic ReDoS screen for an author-supplied cross_ref pattern: run the sticky
// match against adversarial runs in a child process bounded by a hard wall-clock timeout.
// A catastrophic pattern backtracks past the deadline and the child is killed (SIGTERM);
// a safe pattern finishes in microseconds. This is the robust complement to markdown.cjs's
// in-process structural/probe heuristics, which a fixed regex+probe cannot make complete.
function crossRefPatternIsSafe(src) {
  const probeCode =
    'var re=new RegExp(process.argv[1],"y");' +
    'var P=["a".repeat(80),"1".repeat(80),"Z".repeat(80),"aZ1".repeat(27),"1".repeat(60)+"."];' +
    'for(var i=0;i<P.length;i++){re.lastIndex=0;try{re.exec(P[i]);}catch(e){}}';
  let r;
  try {
    r = require('child_process').spawnSync(process.execPath, ['-e', probeCode, src],
      { timeout: 800, stdio: 'ignore' });
  } catch (e) { return true; } // spawn failure: do not block rendering
  return r.signal !== 'SIGTERM' && !(r.error && r.error.code === 'ETIMEDOUT');
}

function parseArgs(argv) {
  const args = { spec: null, outputDir: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--output-dir') args.outputDir = argv[++i];
    else if (!args.spec) args.spec = a;
  }
  return args;
}

function readJson(p, label) {
  let raw;
  try { raw = fs.readFileSync(p, 'utf8'); }
  catch (e) {
    if (e.code === 'ENOENT') die(`${label} not found: ${p}`);
    die(`failed to read ${label} (${p}): ${e.message}`);
  }
  try { return JSON.parse(raw); }
  catch (e) {
    die(`invalid JSON in ${label} (${p}): ${e.message}`);
  }
}

function loadSchema() {
  return readJson(path.join(ASSETS, 'tour-spec.schema.json'), 'schema');
}

function checkSchemaVersion(spec) {
  const supported = /^1\./;
  if (!spec.schema_version || !supported.test(spec.schema_version))
    die(`schema_version ${JSON.stringify(spec.schema_version)} is not supported by this plugin version (1.x); regenerate via analyze or upgrade/downgrade the plugin`);
}

function resolveOverrides(specDir) {
  const overrideRoot = path.join(specDir, '.learning-guide');
  return {
    root: overrideRoot,
    template: path.join(overrideRoot, 'template.html'),
    extraStyles: path.join(overrideRoot, 'extra-styles.css'),
    i18nDir: path.join(overrideRoot, 'i18n'),
    policy: path.join(overrideRoot, 'policy.json')
  };
}

function readTemplate(overrides, spec) {
  const userOverride = fs.existsSync(overrides.template);
  const templatePath = userOverride ? overrides.template : path.join(ASSETS, 'template.html');
  const text = fs.readFileSync(templatePath, 'utf8');
  const m = text.match(/template_compatibility_version:\s*(\S+)/);
  const declared = m ? m[1] : null;
  if (userOverride) {
    const required = (spec.renderer || {}).template_compatibility_version;
    if (!required)
      die(`template.html override exists but tour-spec.renderer.template_compatibility_version is missing; expected ${declared}`);
    if (required !== declared)
      die(`template.html override expects template_compatibility_version=${declared}, spec declares ${required}`);
  }
  return text;
}

function readI18n(overrides, lang) {
  const defaults = readJson(path.join(ASSETS, 'i18n', 'en.json'), 'default i18n');
  const baseLangPath = path.join(ASSETS, 'i18n', lang + '.json');
  const base = fs.existsSync(baseLangPath) ? readJson(baseLangPath, 'lang i18n') : {};
  const userPath = path.join(overrides.i18nDir, lang + '.json');
  const user = fs.existsSync(userPath) ? readJson(userPath, 'override i18n') : {};
  return Object.assign({}, defaults, base, user);
}

function readExtraStyles(overrides) {
  if (!fs.existsSync(overrides.extraStyles)) return '';
  return fs.readFileSync(overrides.extraStyles, 'utf8');
}

function readPolicy(overrides) {
  if (!fs.existsSync(overrides.policy)) return null;
  return readJson(overrides.policy, 'policy.json');
}

function resolveEmbeddedRoot(specDir, policy) {
  if (!policy || !policy.project_root) return specDir;
  return path.resolve(specDir, policy.project_root);
}

function isInside(parent, child) {
  const rel = path.relative(parent, child);
  return rel && !rel.startsWith('..') && !path.isAbsolute(rel);
}

function loadEmbeddedSources(spec, specDir, embeddedRoot) {
  const out = [];
  for (const src of (spec.embedded_sources || [])) {
    if (path.isAbsolute(src.path))
      die(`embedded source "${src.name}" uses absolute path "${src.path}"; use a path relative to the spec`);
    const resolved = path.resolve(specDir, src.path);
    if (!isInside(embeddedRoot, resolved) && resolved !== embeddedRoot)
      die(`embedded source "${src.name}" path "${src.path}" resolves outside project root ${embeddedRoot}`);
    if (!fs.existsSync(resolved))
      die(`embedded source "${src.name}" not found: ${resolved}`);
    // R15 — defeat symlink/junction escapes: re-check containment on the real paths.
    let realResolved, realRoot;
    try { realResolved = fs.realpathSync.native(resolved); } catch (e) { realResolved = resolved; }
    try { realRoot = fs.realpathSync.native(embeddedRoot); } catch (e) { realRoot = embeddedRoot; }
    if (!isInside(realRoot, realResolved) && realResolved !== realRoot)
      die(`embedded source "${src.name}" resolves via symlink outside project root ${realRoot}`);
    if (!fs.statSync(resolved).isFile())
      die(`embedded source "${src.name}" path "${src.path}" is not a regular file: ${resolved}`);
    const raw = md.normalizeLineEndings(fs.readFileSync(resolved, 'utf8'));
    out.push({ name: src.name, label: src.label, content: raw });
  }
  return out;
}

function htmlEscape(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
function attrEscape(s) { return htmlEscape(s); }
// Embed JSON safely inside a <script> element: neutralise `<` so `</script>` can't break out,
// while keeping the text JSON.parse-able (unlike HTML-entity escaping).
function jsonForScript(obj) {
  return JSON.stringify(obj).replace(/</g, '\\u003c');
}
// Inline JS/CSS into <script>/<style> without letting a literal close-tag sequence end the
// element early. `<\/script` / `<\/style` are equivalent inside JS strings/regexes and CSS.
function inlineJs(s) { return String(s).replace(/<\/script/gi, '<\\/script'); }
function inlineCss(s) { return String(s).replace(/<\/style/gi, '<\\/style'); }

function buildToc(navItems) {
  return navItems.map(n => {
    const cls = n.level >= 2 ? ' class="lvl2"' : '';
    return `<li><a href="#${attrEscape(n.id)}" data-id="${attrEscape(n.id)}"${cls}>` +
      `<span class="dot"></span>${htmlEscape(n.title)}</a></li>`;
  }).join('\n');
}

function renderQuiz(quiz, idPrefix) {
  if (!quiz || !quiz.length) return '';
  const out = [];
  for (let i = 0; i < quiz.length; i++) {
    const q = quiz[i];
    const groupName = idPrefix + '-q' + i;
    const opts = q.options.map((opt, idx) =>
      `<label><input type="radio" name="${attrEscape(groupName)}" value="${idx}"> ${htmlEscape(opt)}</label>`
    ).join('');
    out.push(
      `<div class="quiz" data-answer="${q.answer_index}">` +
      `<fieldset><legend>${htmlEscape(q.question)}</legend>` +
      `<div class="options">${opts}</div></fieldset>` +
      `<div class="quiz-status" role="status" aria-live="polite"></div>` +
      (q.explanation ? `<div class="reveal" aria-live="polite">${md.renderBody(q.explanation, {})}</div>` : '') +
      `</div>`
    );
  }
  return out.join('\n');
}

// R13 — pager prev/next are <button> (keyboard-operable, Enter/Space). The mark-read
// control follows the progress tracker, not the pager (CF10), so disabling the pager does
// not strand the tracker with no way to mark sections read.
function sectionFooter(prevId, nextId, sectionId, i18n, includePager, includeProgress) {
  const markRead = includeProgress
    ? `<button type="button" class="mark-read" data-section="${attrEscape(sectionId)}" aria-pressed="false">${htmlEscape(i18n.markRead || 'Mark as read')}</button>`
    : '';
  if (!includePager) return markRead ? `<div class="pager">${markRead}</div>` : '';
  return `<div class="pager">` +
    (prevId
      ? `<button type="button" class="prev" data-target="${attrEscape(prevId)}">${htmlEscape(i18n.prev || 'Previous')}</button>`
      : `<span class="disabled"></span>`) +
    (markRead || `<span class="disabled"></span>`) +
    (nextId
      ? `<button type="button" class="next" data-target="${attrEscape(nextId)}">${htmlEscape(i18n.next || 'Next')}</button>`
      : `<span class="disabled"></span>`) +
    `</div>`;
}

function buildGlossary(glossary, i18n, pager) {
  const items = glossary.map(g =>
    `<dt>${htmlEscape(g.term)}</dt><dd>${md.renderBody(g.definition, {})}</dd>`
  ).join('');
  return `<section class="section" id="glossary"><h1>${htmlEscape(i18n.glossary || 'Glossary')}</h1>` +
    `<dl class="glossary">${items}</dl>${pager}</section>`;
}

function buildEmbeddedSources(sources) {
  if (!sources.length) return '';
  return sources.map(s =>
    `<script type="text/markdown" data-name="${attrEscape(s.name)}" data-label="${attrEscape(s.label)}">\n${md.escapeForScriptTag(s.content)}\n</script>`
  ).join('\n');
}

function buildSidePanel(sources, i18n) {
  if (!sources.length) return '';
  // R12 — accessible dialog: labelled, modal, toggled aria-hidden by runtime.js on open/close.
  return (
    `<div id="md-viewer-backdrop" class="md-viewer-backdrop"></div>` +
    `<aside id="md-viewer" class="md-viewer" role="dialog" aria-modal="true" ` +
    `aria-label="${attrEscape(i18n.sourcePanel || 'Source document')}" aria-hidden="true">` +
    `<div class="md-viewer-header"><span></span>` +
    `<button type="button" id="md-viewer-close" class="md-viewer-btn">${htmlEscape(i18n.panelClose || 'Close')}</button></div>` +
    `<div class="md-viewer-content" tabindex="0"></div>` +
    `</aside>`
  );
}

function buildProgressBlock(spec, i18n) {
  if (spec.renderer && spec.renderer.include_progress_tracker === false) return '';
  return (
    `<div class="progress" aria-label="${attrEscape(i18n.progressLabel || 'Progress')}">` +
    `${htmlEscape(i18n.progressLabel || 'Progress')}: <span id="progress-text">0 / 0</span>` +
    `<div class="bar"><div id="progress-bar" style="width:0"></div></div>` +
    `<button type="button" class="reset" id="reset-progress">${htmlEscape(i18n.resetProgress || 'Reset progress')}</button>` +
    `</div>`
  );
}

function buildReadme(spec, lang) {
  const title = spec.title;
  return [
    `# ${title}`,
    '',
    `Generated by [learning-guide](https://github.com/DmitriyYukhanov/agent-plugins) as a single-file interactive tour.`,
    '',
    `## Open`,
    '',
    `Open \`index.html\` directly in any modern browser.`,
    '',
    `## Re-render after editing the spec`,
    '',
    `1. Edit \`tour-spec.json\`.`,
    `2. Run \`node <plugin-path>/scripts/render.cjs tour-spec.json\` from this directory.`,
    `3. Reload \`index.html\` in your browser (Ctrl+F5).`,
    '',
    `## Persistence`,
    '',
    `Progress and "Mark as read" state live in your browser's \`localStorage\`. They are local to your machine and are lost when you share the file with someone else.`,
    '',
    `## Customization`,
    '',
    `Drop overrides under \`./.learning-guide/\`:`,
    '',
    `- \`template.html\` (set \`renderer.template_compatibility_version\` in the spec)`,
    `- \`i18n/${lang}.json\` (shallow-merged over plugin defaults)`,
    `- \`extra-styles.css\` (appended after default styles)`,
    `- \`policy.json\` — \`{ "project_root": "<relative-path>" }\` widens embedded-source resolution.`,
    ''
  ].join('\n');
}

function fillTemplate(template, vars) {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? vars[key] : ''
  );
}

function main() {
  const args = parseArgs(process.argv);
  if (!args.spec) die('usage: render.cjs <spec-path> [--output-dir <dir>]');

  const specPath = path.resolve(args.spec);
  const specDir = path.dirname(specPath);
  const outputDir = path.resolve(args.outputDir || specDir);

  const spec = readJson(specPath, 'spec');
  if (!spec || typeof spec !== 'object' || Array.isArray(spec))
    die(`spec must be a JSON object: ${specPath}`);
  checkSchemaVersion(spec);

  const schema = loadSchema();
  const errs = validate(spec, schema);
  if (errs.length) {
    for (const e of errs) process.stderr.write(`  ${e.path}: ${e.message}\n`);
    die(`spec validation failed (${errs.length} error${errs.length > 1 ? 's' : ''})`);
  }

  // Cross-field checks the per-node JSON Schema validator cannot express.
  for (const s of spec.sections)
    if (s.level >= 2 && !s.parent)
      die(`section "${s.id}" has level ${s.level} but no parent`);
  const allQuizzes = [];
  for (const s of spec.sections) for (const q of (s.quiz || [])) allQuizzes.push([s.id, q]);
  for (const q of (spec.final_quiz || [])) allQuizzes.push(['final_quiz', q]);
  for (const [sid, q] of allQuizzes)
    if (q.answer_index >= q.options.length)
      die(`quiz in "${sid}" has answer_index ${q.answer_index} but only ${q.options.length} options`);
  for (const p of (spec.cross_ref_patterns || [])) {
    try { new RegExp(p.pattern, 'y'); }
    catch (e) { die(`cross_ref pattern ${JSON.stringify(p.pattern)} is not a valid regex: ${e.message}`); }
    if (!crossRefPatternIsSafe(p.pattern))
      die(`cross_ref pattern ${JSON.stringify(p.pattern)} is too slow (catastrophic backtracking); simplify it`);
  }

  const overrides = resolveOverrides(specDir);
  const policy = readPolicy(overrides);
  const embeddedRoot = resolveEmbeddedRoot(specDir, policy);
  const i18n = readI18n(overrides, spec.lang);
  const extraStyles = readExtraStyles(overrides);
  const template = readTemplate(overrides, spec);
  const styles = fs.readFileSync(path.join(ASSETS, 'styles.css'), 'utf8');
  const runtime = fs.readFileSync(path.join(ASSETS, 'runtime.js'), 'utf8');

  const sources = loadEmbeddedSources(spec, specDir, embeddedRoot);

  const includePager = !spec.renderer || spec.renderer.include_pager !== false;
  const includeProgress = !spec.renderer || spec.renderer.include_progress_tracker !== false;
  const hasFinalQuiz = !!(spec.final_quiz && spec.final_quiz.length);
  const hasGlossary = !!(spec.glossary && spec.glossary.length);

  // The renderer injects reserved 'final-quiz'/'glossary' sections; an author section using
  // the same id would collide (duplicate DOM ids, mis-wired nav). Reject it.
  for (const s of spec.sections) {
    if (hasFinalQuiz && s.id === 'final-quiz') die(`section id "final-quiz" is reserved when final_quiz is present; rename the section`);
    if (hasGlossary && s.id === 'glossary') die(`section id "glossary" is reserved when glossary is present; rename the section`);
  }

  // R4/R5 — final_quiz and glossary are real, navigable sections in the nav order.
  const navItems = spec.sections.map(s => ({ id: s.id, title: s.title, level: s.level }));
  if (hasFinalQuiz) navItems.push({ id: 'final-quiz', title: i18n.finalQuiz || 'Self-check', level: 1 });
  if (hasGlossary) navItems.push({ id: 'glossary', title: i18n.glossary || 'Glossary', level: 1 });
  const navIds = navItems.map(n => n.id);

  const sectionsHtml = [];
  for (let idx = 0; idx < spec.sections.length; idx++) {
    const s = spec.sections[idx];
    const meta = s.estimated_minutes
      ? `<p class="meta">${s.estimated_minutes} ${htmlEscape(i18n.minutes || 'min')}</p>` : '';
    const body = md.renderBody(s.body_md, spec);
    const quiz = renderQuiz(s.quiz, s.id);
    const pager = sectionFooter(navIds[idx - 1], navIds[idx + 1], s.id, i18n, includePager, includeProgress);
    sectionsHtml.push(
      `<section class="section" id="${attrEscape(s.id)}"><h1>${htmlEscape(s.title)}</h1>${meta}${body}${quiz}${pager}</section>`
    );
  }
  if (hasFinalQuiz) {
    const i = navIds.indexOf('final-quiz');
    const fq = renderQuiz(spec.final_quiz, 'final');
    const pager = sectionFooter(navIds[i - 1], navIds[i + 1], 'final-quiz', i18n, includePager, includeProgress);
    sectionsHtml.push(
      `<section class="section" id="final-quiz"><h1>${htmlEscape(i18n.finalQuiz || 'Self-check')}</h1>${fq}${pager}</section>`
    );
  }
  if (hasGlossary) {
    const i = navIds.indexOf('glossary');
    const pager = sectionFooter(navIds[i - 1], navIds[i + 1], 'glossary', i18n, includePager, includeProgress);
    sectionsHtml.push(buildGlossary(spec.glossary, i18n, pager));
  }
  const sectionsJoined = sectionsHtml.join('\n');

  // R6 — Mermaid detection is a post-process count of rendered mermaid divs (body_md only),
  // never a raw-fence regex (which false-positives on fenced code examples).
  const renderedMermaidCount = (sectionsJoined.match(/<div class="mermaid">/g) || []).length;
  const explicitMermaid = (spec.renderer || {}).include_mermaid;
  const includeMermaid = explicitMermaid === true ? true
    : explicitMermaid === false ? false
    : renderedMermaidCount > 0;

  const mermaidBlock = includeMermaid ? MERMAID_BLOCK : '';

  const tocItems = buildToc(navItems);
  const embeddedSourcesHtml = buildEmbeddedSources(sources);
  const sidePanelHtml = buildSidePanel(sources, i18n);
  const progressBlock = buildProgressBlock(spec, i18n);
  const subtitleBlock = spec.subtitle
    ? `<div class="subtitle">${htmlEscape(spec.subtitle)}</div>` : '';

  const tourId = require('crypto').createHash('sha1')
    .update((spec.title || '') + '|' + (spec.subtitle || '')).digest('hex').slice(0, 12);
  const tourMeta = { tourId, sections: navIds };

  const html = fillTemplate(template, {
    LANG: htmlEscape(spec.lang),
    TITLE_HTML: htmlEscape(spec.title),
    STYLES: inlineCss(styles),
    EXTRA_STYLES_BLOCK: extraStyles ? `<style>${inlineCss(extraStyles)}</style>` : '',
    MERMAID_BLOCK: mermaidBlock,
    I18N_NAV_LABEL: attrEscape(i18n.navLabel || 'Navigation'),
    I18N_TOC_LABEL: attrEscape(i18n.tocLabel || 'Table of contents'),
    SUBTITLE_BLOCK: subtitleBlock,
    TOC_ITEMS: tocItems,
    PROGRESS_BLOCK: progressBlock,
    SECTIONS: sectionsJoined,
    SIDE_PANEL_BLOCK: sidePanelHtml,
    EMBEDDED_SOURCES: embeddedSourcesHtml,
    I18N_JSON: jsonForScript(i18n),
    TOUR_META_JSON: jsonForScript(tourMeta),
    RUNTIME: inlineJs(runtime)
  });

  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(path.join(outputDir, 'index.html'), html, 'utf8');

  const readmePath = path.join(outputDir, 'README.md');
  if (!fs.existsSync(readmePath))
    fs.writeFileSync(readmePath, buildReadme(spec, spec.lang), 'utf8');

  // R7 — soft payload warning. Mermaid needs no exclusion any more: it is two script tags,
  // not 3.2 MB of inlined bundle, so the measured size is the content the author controls.
  const cap = (spec.renderer || {}).max_inline_payload_kb;
  if (cap != null) {
    const contentKB = Buffer.byteLength(html, 'utf8') / 1024;
    if (contentKB > cap)
      warn(`max_inline_payload_kb=${cap} exceeded by inlined content: ${contentKB.toFixed(1)} KB`);
  }

  const sizeKB = (Buffer.byteLength(html, 'utf8') / 1024).toFixed(1);
  process.stdout.write(
    `Tour rendered to ${outputDir}/index.html (${sizeKB} KB, ${spec.sections.length} sections, Mermaid ${includeMermaid ? 'yes' : 'no'}).\n`
  );
}

main();
