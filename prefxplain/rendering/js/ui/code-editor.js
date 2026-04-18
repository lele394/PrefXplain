// ui/code-editor.js — in-place file editor modal.
// Space bar or double-click on a file card/explorer entry opens it.
// Cmd/Ctrl+S saves. Clicking the backdrop or pressing Escape prompts to
// save or discard when there are unsaved edits.
//
// Visuals: VS Code CSS variables (--vscode-editor-*) drive background,
// foreground, font, and selection so the editor matches the user's active
// theme inside a VS Code webview. Syntax highlighting is done with a small
// regex tokenizer layered as a <pre> behind a transparent <textarea>.
//
// Save/load transport:
//   - Inside the VS Code extension webview: postMessage to the extension host,
//     which reads/writes the file via node fs.
//   - Outside VS Code: best-effort fetch for read, File System Access API
//     (showSaveFilePicker) or download fallback for save.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

// ── Syntax tokenizer ──────────────────────────────────────────────────────
// Each language is an ordered list of [tokenType, regex-source] pairs. We
// compile sticky versions lazily on first use. The tokenizer tries each rule
// at the current offset; whichever matches first wins. Unmatched characters
// become plain text. This is deliberately simple — it gets ~80% of VS Code's
// highlighting without pulling Monaco/TextMate.
const _LANG_RULES_SRC = {
  python: [
    ['comment',    `#[^\\n]*`],
    ['string',     `"""[\\s\\S]*?"""|'''[\\s\\S]*?'''|[rRbBfFuU]{0,2}"(?:\\\\.|[^"\\\\\\n])*"|[rRbBfFuU]{0,2}'(?:\\\\.|[^'\\\\\\n])*'`],
    ['keyword',    `\\b(?:def|class|if|elif|else|for|while|return|import|from|as|with|try|except|finally|raise|pass|break|continue|yield|lambda|and|or|not|in|is|None|True|False|global|nonlocal|async|await)\\b`],
    ['builtin',    `\\b(?:self|cls|print|len|range|dict|list|tuple|set|str|int|float|bool|bytes|type|isinstance|hasattr|getattr|setattr|super|open|enumerate|zip|map|filter|sorted|reversed|any|all|sum|min|max|abs|round)\\b`],
    ['decorator',  `@[A-Za-z_][\\w.]*`],
    ['number',     `\\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO]?[0-7_]+|\\d[\\d_]*\\.?\\d*(?:[eE][+-]?\\d+)?|\\.\\d+(?:[eE][+-]?\\d+)?)\\b`],
    ['function',   `\\b[a-zA-Z_]\\w*(?=\\s*\\()`],
    ['type',       `\\b[A-Z]\\w*\\b`],
  ],
  javascript: [
    ['comment',    `\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/`],
    ['string',     `\`(?:\\\\[\\s\\S]|\\$\\{[^}]*\\}|[^\`\\\\])*\`|"(?:\\\\.|[^"\\\\\\n])*"|'(?:\\\\.|[^'\\\\\\n])*'`],
    ['keyword',    `\\b(?:var|let|const|function|class|extends|new|this|super|return|if|else|for|while|do|switch|case|break|continue|default|try|catch|finally|throw|import|export|from|as|async|await|yield|of|in|instanceof|typeof|void|delete|null|undefined|true|false|NaN|Infinity|static|get|set)\\b`],
    ['builtin',    `\\b(?:console|document|window|Math|Object|Array|String|Number|Boolean|JSON|Promise|Set|Map|Symbol|Error|RegExp|Date)\\b`],
    ['number',     `\\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|\\d[\\d_]*\\.?\\d*(?:[eE][+-]?\\d+)?|\\.\\d+(?:[eE][+-]?\\d+)?)\\b`],
    ['function',   `\\b[a-zA-Z_$][\\w$]*(?=\\s*\\()`],
    ['type',       `\\b[A-Z][\\w$]*\\b`],
  ],
  typescript: null, // share with javascript, filled in below
  json: [
    ['string',     `"(?:\\\\.|[^"\\\\])*"`],
    ['keyword',    `\\b(?:true|false|null)\\b`],
    ['number',     `-?(?:0|[1-9]\\d*)(?:\\.\\d+)?(?:[eE][+-]?\\d+)?`],
  ],
  css: [
    ['comment',    `\\/\\*[\\s\\S]*?\\*\\/`],
    ['string',     `"(?:\\\\.|[^"\\\\\\n])*"|'(?:\\\\.|[^'\\\\\\n])*'`],
    ['number',     `-?\\d*\\.?\\d+(?:px|em|rem|%|vh|vw|vmin|vmax|pt|cm|mm|in|ch|ex|s|ms|deg|rad|turn|fr)?\\b`],
    ['function',   `\\b[a-zA-Z_-][\\w-]*(?=\\s*\\()`],
    ['keyword',    `@\\w+|:[\\w-]+`],
    ['type',       `#[0-9a-fA-F]{3,8}\\b`],
  ],
  go: [
    ['comment',    `\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/`],
    ['string',     `\`[^\`]*\`|"(?:\\\\.|[^"\\\\\\n])*"`],
    ['keyword',    `\\b(?:package|import|func|var|const|type|struct|interface|map|chan|return|if|else|for|range|switch|case|default|break|continue|fallthrough|go|defer|select|goto)\\b`],
    ['builtin',    `\\b(?:make|new|len|cap|append|copy|delete|close|panic|recover|print|println|nil|true|false|iota|error|string|int|int8|int16|int32|int64|uint|uint8|uint16|uint32|uint64|byte|rune|bool|float32|float64|complex64|complex128)\\b`],
    ['number',     `\\b(?:0[xX][0-9a-fA-F]+|\\d+(?:\\.\\d+)?)\\b`],
    ['function',   `\\b[a-zA-Z_]\\w*(?=\\s*\\()`],
    ['type',       `\\b[A-Z]\\w*\\b`],
  ],
  rust: [
    ['comment',    `\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/`],
    ['string',     `"(?:\\\\.|[^"\\\\\\n])*"|'\\\\?.'|b"(?:\\\\.|[^"\\\\\\n])*"`],
    ['keyword',    `\\b(?:fn|let|mut|const|static|pub|mod|use|crate|struct|enum|trait|impl|for|where|as|dyn|ref|move|return|if|else|match|while|loop|break|continue|in|self|Self|super|async|await|true|false|unsafe|extern|type)\\b`],
    ['decorator',  `#\\[[^\\]]*\\]|#!\\[[^\\]]*\\]`],
    ['number',     `\\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|\\d[\\d_]*(?:\\.[\\d_]+)?(?:[eE][+-]?\\d+)?)(?:[uif](?:8|16|32|64|128|size)?)?\\b`],
    ['function',   `\\b[a-zA-Z_]\\w*(?=\\s*[(!<])`],
    ['type',       `\\b[A-Z]\\w*\\b`],
  ],
  shell: [
    ['comment',    `#[^\\n]*`],
    ['string',     `"(?:\\\\.|[^"\\\\])*"|'[^']*'`],
    ['keyword',    `\\b(?:if|then|else|elif|fi|case|esac|for|in|do|done|while|until|function|return|break|continue|export|local|readonly|declare|typeset|source|exit)\\b`],
    ['builtin',    `\\b(?:echo|printf|cd|pwd|ls|cat|grep|sed|awk|cut|tr|sort|uniq|wc|head|tail|find|xargs|test|true|false)\\b`],
    ['number',     `\\b\\d+\\b`],
    ['decorator',  `\\$\\w+|\\$\\{[^}]+\\}`],
  ],
  java: [
    ['comment',    `\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/`],
    ['string',     `"(?:\\\\.|[^"\\\\\\n])*"|'\\\\?.'`],
    ['keyword',    `\\b(?:public|private|protected|static|final|abstract|synchronized|native|transient|volatile|class|interface|enum|extends|implements|import|package|new|this|super|return|if|else|for|while|do|switch|case|break|continue|default|try|catch|finally|throw|throws|void|null|true|false|instanceof)\\b`],
    ['builtin',    `\\b(?:String|Integer|Long|Double|Float|Boolean|Object|List|Map|Set|Collection|Optional|System|Math)\\b`],
    ['decorator',  `@\\w+`],
    ['number',     `\\b\\d+(?:\\.\\d+)?[lLfFdD]?\\b`],
    ['function',   `\\b[a-zA-Z_]\\w*(?=\\s*\\()`],
    ['type',       `\\b[A-Z]\\w*\\b`],
  ],
  kotlin: [
    ['comment',    `\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/`],
    ['string',     `"""[\\s\\S]*?"""|"(?:\\\\.|[^"\\\\\\n])*"|'\\\\?.'`],
    ['keyword',    `\\b(?:fun|val|var|class|object|interface|enum|sealed|data|abstract|open|override|private|public|internal|protected|suspend|inline|operator|infix|companion|package|import|return|if|else|for|while|do|when|is|as|in|out|by|with|throw|try|catch|finally|break|continue|null|true|false|this|super)\\b`],
    ['decorator',  `@\\w+`],
    ['number',     `\\b\\d+(?:\\.\\d+)?[fLuU]?\\b`],
    ['function',   `\\b[a-zA-Z_]\\w*(?=\\s*\\()`],
    ['type',       `\\b[A-Z]\\w*\\b`],
  ],
  html: [
    ['comment',    `<!--[\\s\\S]*?-->`],
    ['string',     `"(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*'`],
    ['keyword',    `<\\/?[a-zA-Z][\\w-]*`],
    ['type',       `>|<|\\/>`],
    ['function',   `\\b[a-zA-Z-]+(?==)`],
  ],
  markdown: [
    ['comment',    `<!--[\\s\\S]*?-->`],
    ['string',     `\`[^\`\\n]*\`|\`\`\`[\\s\\S]*?\`\`\``],
    ['keyword',    `^#{1,6}\\s[^\\n]*`],
    ['type',       `\\*\\*[^*\\n]+\\*\\*|__[^_\\n]+__`],
    ['function',   `\\[[^\\]\\n]*\\]\\([^)\\n]*\\)`],
  ],
};
_LANG_RULES_SRC.typescript = _LANG_RULES_SRC.javascript;
_LANG_RULES_SRC.tsx = _LANG_RULES_SRC.javascript;
_LANG_RULES_SRC.jsx = _LANG_RULES_SRC.javascript;
_LANG_RULES_SRC.mjs = _LANG_RULES_SRC.javascript;
_LANG_RULES_SRC.cjs = _LANG_RULES_SRC.javascript;
_LANG_RULES_SRC.scss = _LANG_RULES_SRC.css;
_LANG_RULES_SRC.less = _LANG_RULES_SRC.css;
_LANG_RULES_SRC.bash = _LANG_RULES_SRC.shell;
_LANG_RULES_SRC.sh = _LANG_RULES_SRC.shell;
_LANG_RULES_SRC.zsh = _LANG_RULES_SRC.shell;
_LANG_RULES_SRC.kt = _LANG_RULES_SRC.kotlin;
_LANG_RULES_SRC.kts = _LANG_RULES_SRC.kotlin;
_LANG_RULES_SRC.md = _LANG_RULES_SRC.markdown;
_LANG_RULES_SRC.htm = _LANG_RULES_SRC.html;
_LANG_RULES_SRC.xml = _LANG_RULES_SRC.html;
_LANG_RULES_SRC.yaml = _LANG_RULES_SRC.python;
_LANG_RULES_SRC.yml = _LANG_RULES_SRC.python;

const _LANG_RULES_COMPILED = {};
function _rules(lang) {
  if (_LANG_RULES_COMPILED[lang]) return _LANG_RULES_COMPILED[lang];
  const src = _LANG_RULES_SRC[lang];
  if (!src) { _LANG_RULES_COMPILED[lang] = null; return null; }
  _LANG_RULES_COMPILED[lang] = src.map(([type, re]) => [type, new RegExp(re, 'y')]);
  return _LANG_RULES_COMPILED[lang];
}

// Map a file path to a tokenizer language.
const _EXT_MAP = {
  py: 'python', pyi: 'python',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript', jsx: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  json: 'json',
  css: 'css', scss: 'css', sass: 'css', less: 'css',
  html: 'html', htm: 'html', xml: 'html',
  md: 'markdown', markdown: 'markdown',
  sh: 'shell', bash: 'shell', zsh: 'shell',
  go: 'go',
  rs: 'rust',
  java: 'java',
  kt: 'kotlin', kts: 'kotlin',
  yaml: 'python', yml: 'python', // loose — good-enough string/number highlighting
};
function _detectLang(path) {
  const m = /\.([A-Za-z0-9]+)$/.exec(path || '');
  if (!m) return null;
  return _EXT_MAP[m[1].toLowerCase()] || null;
}

function _highlight(code, lang) {
  const rules = _rules(lang);
  if (!rules) return PX.escapeXml(code);
  const n = code.length;
  let i = 0;
  let out = '';
  while (i < n) {
    let best = null;
    for (const [type, rx] of rules) {
      rx.lastIndex = i;
      const m = rx.exec(code);
      if (m && m.index === i) { best = { type, text: m[0] }; break; }
    }
    if (best) {
      out += `<span class="px-t-${best.type}">${PX.escapeXml(best.text)}</span>`;
      i += best.text.length;
    } else {
      // Consume a run of plain characters (space/punct/identifier) up to the
      // next potential token start, to keep the DOM compact.
      const start = i;
      while (i < n) {
        const c = code.charCodeAt(i);
        // Break on characters likely to start a token.
        if (c === 34 || c === 39 || c === 96 ||          // quotes
            c === 47 || c === 35 || c === 64 ||           // / # @
            (c >= 48 && c <= 57) ||                       // digits
            (c >= 65 && c <= 90) || (c >= 97 && c <= 122) || c === 95) {
          break;
        }
        i++;
      }
      if (i === start) { out += PX.escapeXml(code[i]); i++; }
      else out += PX.escapeXml(code.slice(start, i));
    }
  }
  // Trailing newline keeps pre height in sync with textarea during empty final line.
  if (!out.endsWith('\n')) out += '\n';
  return out;
}

// One VS Code API handle per webview; acquireVsCodeApi throws if called twice.
let _vscode = null;
function _getVsCodeApi() {
  if (_vscode) return _vscode;
  try {
    if (typeof acquireVsCodeApi === 'function') {
      _vscode = acquireVsCodeApi();
      return _vscode;
    }
  } catch { /* already acquired by something else this session */ }
  return null;
}

// Pending request registry for postMessage correlation.
const _pending = new Map();
let _msgCounter = 0;
function _rpc(type, payload, timeoutMs = 15000) {
  const api = _getVsCodeApi();
  if (!api) return Promise.reject(new Error('host-unavailable'));
  return new Promise((resolve, reject) => {
    const id = `px-${Date.now()}-${++_msgCounter}`;
    const timer = setTimeout(() => {
      _pending.delete(id);
      reject(new Error('host-timeout'));
    }, timeoutMs);
    _pending.set(id, { resolve, reject, timer });
    api.postMessage({ type, id, ...payload });
  });
}

window.addEventListener('message', (event) => {
  const msg = event.data;
  if (!msg || !msg.id || !_pending.has(msg.id)) return;
  const { resolve, reject, timer } = _pending.get(msg.id);
  _pending.delete(msg.id);
  clearTimeout(timer);
  if (msg.ok) resolve(msg);
  else reject(new Error(msg.error || 'host-error'));
});

async function _loadFile(relPath) {
  // Prefer the VS Code host so we always read from disk, even in a webview
  // whose base href is webview://…
  try {
    const res = await _rpc('prefxplain:load-file', { path: relPath });
    return { content: res.content, mode: 'vscode' };
  } catch (err) {
    if (err.message !== 'host-unavailable') throw err;
  }
  // Fallback for plain browser contexts.
  const res = await fetch(relPath);
  if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
  return { content: await res.text(), mode: 'fetch' };
}

async function _saveFile(relPath, content) {
  try {
    await _rpc('prefxplain:save-file', { path: relPath, content });
    return { mode: 'vscode' };
  } catch (err) {
    if (err.message !== 'host-unavailable') throw err;
  }
  // Plain browser fallback: offer a download so the user can replace the file.
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = relPath.split('/').pop() || 'file.txt';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { mode: 'download' };
}

// Tiny confirm dialog used when closing with unsaved edits.
function _confirmDialog({ message, onSave, onDiscard, onCancel }) {
  const T = PX.T;
  const overlay = document.createElement('div');
  overlay.style.cssText = `position:fixed;inset:0;background:rgba(1,4,9,0.92);z-index:120;display:flex;align-items:center;justify-content:center;font-family:${T.ui};backdrop-filter:blur(4px)`;
  overlay.innerHTML = `
    <div role="dialog" aria-modal="true" style="background:${T.panel};border:1px solid ${T.border};border-radius:8px;width:min(440px,92vw);padding:20px 22px;box-shadow:0 24px 80px rgba(0,0,0,0.6)">
      <div style="font-size:14px;font-weight:600;color:${T.ink};margin-bottom:6px">Unsaved changes</div>
      <div style="font-size:12.5px;color:${T.ink2};line-height:1.55;margin-bottom:18px">${PX.escapeXml(message)}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button data-act="cancel" style="font-family:${T.ui};font-size:12px;padding:6px 12px;background:transparent;color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;cursor:pointer">Cancel</button>
        <button data-act="discard" style="font-family:${T.ui};font-size:12px;padding:6px 12px;background:transparent;color:${T.danger};border:1px solid ${T.danger};border-radius:4px;cursor:pointer">Discard</button>
        <button data-act="save" style="font-family:${T.ui};font-size:12px;padding:6px 12px;background:${T.accent};color:#0d1117;border:1px solid ${T.accent};border-radius:4px;cursor:pointer;font-weight:600">Save</button>
      </div>
    </div>
  `;
  const close = () => overlay.remove();
  overlay.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const act = btn.getAttribute('data-act');
    close();
    if (act === 'save') onSave && onSave();
    else if (act === 'discard') onDiscard && onDiscard();
    else onCancel && onCancel();
  });
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); onCancel && onCancel(); window.removeEventListener('keydown', onKey, true); }
  };
  window.addEventListener('keydown', onKey, true);
  document.body.appendChild(overlay);
  overlay.querySelector('button[data-act="save"]').focus();
}

PX.ui.codeEditor = async function codeEditor({ nodeId, graph, index }) {
  const T = PX.T;
  const n = (index && index.byId && index.byId[nodeId])
    || (graph.nodes || []).find(node => node.id === nodeId);
  if (!n) return null;
  const lang = _detectLang(n.id);

  const overlay = document.createElement('div');
  overlay.style.cssText = `position:fixed;inset:0;background:rgba(1,4,9,0.88);z-index:110;display:flex;align-items:stretch;justify-content:center;padding:3vh 3vw;font-family:${T.ui};backdrop-filter:blur(6px)`;

  overlay.innerHTML = `
    <div id="px-editor-card" style="background:${T.panel};border:1px solid ${T.border};border-radius:8px;width:100%;max-width:1180px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,0.65)">
      <div style="padding:12px 18px;border-bottom:1px solid ${T.border};display:flex;align-items:center;gap:10px;background:${T.panelAlt};flex-shrink:0">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">Editor</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        <span style="font-family:${T.mono};font-size:13px;color:${T.ink};font-weight:600">${PX.escapeXml(n.label)}</span>
        <span style="font-family:${T.mono};font-size:10.5px;color:${T.inkFaint};overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${PX.escapeXml(n.id)}</span>
        <span data-dirty style="font-family:${T.mono};font-size:10px;color:${T.warn};display:none">\u25cf unsaved</span>
        <span data-status style="font-family:${T.mono};font-size:10px;color:${T.inkFaint}"></span>
        <span style="flex:1"></span>
        <span style="font-family:${T.mono};font-size:10px;color:${T.inkFaint}">\u2318/Ctrl+S to save \u00b7 Esc to close</span>
        <button data-act="save" style="font-family:${T.ui};font-size:11.5px;font-weight:600;padding:5px 12px;background:${T.accent};color:#0d1117;border:1px solid ${T.accent};border-radius:4px;cursor:pointer">Save</button>
        <button data-act="close" title="Close" style="background:transparent;border:1px solid ${T.border};color:${T.inkMuted};font-family:${T.mono};font-size:13px;width:26px;height:26px;border-radius:3px;cursor:pointer">\u00d7</button>
      </div>
      <div class="px-editor-surface" style="position:relative;flex:1;min-height:0;overflow:hidden">
        <div data-highlight-layer aria-hidden="true" style="position:absolute;inset:0;overflow:hidden;pointer-events:none">
          <pre data-highlight style="margin:0;padding:14px 18px;font-family:inherit;font-size:inherit;line-height:inherit;white-space:pre;color:inherit;tab-size:4;-moz-tab-size:4;min-height:100%;box-sizing:border-box;will-change:transform"></pre>
        </div>
        <textarea data-editor class="px-editor-textarea" spellcheck="false" wrap="off"
          style="position:absolute;inset:0;width:100%;height:100%;margin:0;padding:14px 18px;resize:none;border:none;outline:none;background:transparent;color:transparent;caret-color:var(--vscode-editor-foreground,#d4d4d4);font-family:inherit;font-size:inherit;line-height:inherit;white-space:pre;overflow:auto;tab-size:4;-moz-tab-size:4;-webkit-text-fill-color:transparent"></textarea>
      </div>
    </div>
  `;

  const surface = overlay.querySelector('.px-editor-surface');
  const textarea = overlay.querySelector('textarea[data-editor]');
  const preHighlight = overlay.querySelector('pre[data-highlight]');
  const dirtyDot = overlay.querySelector('[data-dirty]');
  const statusSpan = overlay.querySelector('[data-status]');
  const saveBtn = overlay.querySelector('button[data-act="save"]');

  let original = '';
  let closed = false;

  const setStatus = (msg, tone) => {
    statusSpan.textContent = msg || '';
    statusSpan.style.color = tone === 'err' ? T.danger : tone === 'ok' ? T.good : T.inkFaint;
  };
  const isDirty = () => textarea.value !== original;
  const refreshDirty = () => { dirtyDot.style.display = isDirty() ? 'inline' : 'none'; };
  const rehighlight = () => { preHighlight.innerHTML = _highlight(textarea.value, lang); };
  const syncScroll = () => {
    preHighlight.style.transform =
      `translate(${-textarea.scrollLeft}px, ${-textarea.scrollTop}px)`;
  };

  const doClose = () => {
    if (closed) return;
    closed = true;
    window.removeEventListener('keydown', onKey, true);
    overlay.remove();
  };

  const tryClose = () => {
    if (!isDirty()) { doClose(); return; }
    _confirmDialog({
      message: 'You have unsaved changes in this file. Would you like to save them before closing?',
      onSave: async () => { const ok = await doSave(); if (ok) doClose(); },
      onDiscard: () => doClose(),
      onCancel: () => textarea.focus(),
    });
  };

  const doSave = async () => {
    if (!isDirty()) { setStatus('nothing to save'); return true; }
    saveBtn.disabled = true;
    const prevLabel = saveBtn.textContent;
    saveBtn.textContent = 'Saving\u2026';
    setStatus('saving\u2026');
    try {
      const res = await _saveFile(n.id, textarea.value);
      original = textarea.value;
      refreshDirty();
      setStatus(res.mode === 'download' ? 'downloaded (no host)' : 'saved', 'ok');
      return true;
    } catch (err) {
      setStatus(`save failed: ${err.message}`, 'err');
      return false;
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = prevLabel;
    }
  };

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) { tryClose(); return; }
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const act = btn.getAttribute('data-act');
    if (act === 'save') doSave();
    else if (act === 'close') tryClose();
  });

  const onKey = (e) => {
    // Cmd/Ctrl+S save inside the editor.
    if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      e.stopPropagation();
      doSave();
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      tryClose();
    }
  };
  // Capture-phase so the shell's global Escape handler doesn't fire first.
  window.addEventListener('keydown', onKey, true);

  textarea.addEventListener('input', () => { refreshDirty(); rehighlight(); });
  textarea.addEventListener('scroll', syncScroll, { passive: true });
  // Tab inside the textarea inserts a tab character instead of moving focus.
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const value = textarea.value;
      textarea.value = value.slice(0, start) + '\t' + value.slice(end);
      textarea.selectionStart = textarea.selectionEnd = start + 1;
      refreshDirty();
      rehighlight();
    }
  });

  document.body.appendChild(overlay);
  textarea.focus();
  rehighlight();

  setStatus('loading\u2026');
  try {
    const res = await _loadFile(n.id);
    original = res.content || '';
    textarea.value = original;
    refreshDirty();
    rehighlight();
    syncScroll();
    setStatus(res.mode === 'fetch' ? 'read-only host' : '');
    textarea.setSelectionRange(0, 0);
  } catch (err) {
    textarea.value = '';
    original = '';
    rehighlight();
    setStatus(`load failed: ${err.message}`, 'err');
  }

  return { close: doClose, element: overlay };
};
