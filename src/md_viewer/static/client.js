
document.querySelector('.nav-toggle').addEventListener('click', function () {
  var hidden = document.documentElement.classList.toggle('nav-hidden');
  try { localStorage.setItem('navHidden', hidden ? '1' : ''); } catch (e) {}
});

(function () {
  var here = decodeURIComponent(location.pathname);
  document.querySelectorAll('.tree-root a').forEach(function (a) {
    if (decodeURIComponent(a.getAttribute('href')) === here) {
      a.classList.add('current');
      var el = a.parentElement;
      while (el) {
        if (el.tagName === 'DETAILS') el.setAttribute('open', '');
        el = el.parentElement;
      }
      a.scrollIntoView({ block: 'center' });
    }
  });
})();

// Sidebar filter: hides non-matching files and empty folders without opening or closing any;
// a closed folder with matches turns accent-colored and shows its match count.
(function () {
  var input = document.querySelector('.tree-filter');
  if (!input) return;
  var files = Array.prototype.slice.call(document.querySelectorAll('.tree-root li:not(.dir)'));
  var dirs = Array.prototype.slice.call(document.querySelectorAll('.tree-root li.dir'));
  files.forEach(function (li) { li._name = li.firstElementChild.textContent; });
  dirs.forEach(function (li) {
    var badge = document.createElement('span');
    badge.className = 'match-count';
    li.querySelector('summary').appendChild(badge);
  });

  function apply() {
    var q = input.value.trim().toLowerCase();
    files.forEach(function (li) {
      var a = li.firstElementChild, name = li._name;
      var at = q ? name.toLowerCase().indexOf(q) : -1;
      li.hidden = q !== '' && at < 0;
      a.textContent = '';
      if (at < 0) { a.textContent = name; return; }
      var mark = document.createElement('mark');
      mark.textContent = name.slice(at, at + q.length);
      a.append(name.slice(0, at), mark, name.slice(at + q.length));
    });
    dirs.forEach(function (li) {
      var summary = li.querySelector('summary');
      var n = q ? li.querySelectorAll('li:not(.dir):not([hidden])').length : 0;
      li.hidden = q !== '' && n === 0;
      summary.classList.toggle('has-matches', n > 0);
      summary.lastElementChild.textContent = n ? '(' + n + ')' : '';
    });
  }

  input.addEventListener('input', apply);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { input.value = ''; apply(); input.blur(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target;
    if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
    e.preventDefault();
    document.documentElement.classList.remove('nav-hidden');
    input.focus();
    input.select();
  });
})();

function applyLineHash(scroll) {
  var m = location.hash.match(/^#L-?(\d+)(?:-L-?(\d+))?$/);
  if (!m) return;
  var start = parseInt(m[1], 10);
  var end = m[2] ? parseInt(m[2], 10) : start;
  for (var i = start; i <= end; i++) {
    var el = document.getElementById('L-' + i) || document.getElementById('L' + i);
    if (el) el.classList.add('line-highlighted');
  }
  if (!scroll) return;
  var target = document.getElementById('L-' + start) || document.getElementById('L' + start);
  if (target) target.scrollIntoView({ block: 'center' });
}

applyLineHash(true);
window.addEventListener('hashchange', function () {
  document.querySelectorAll('.line-highlighted').forEach(function (el) {
    el.classList.remove('line-highlighted');
  });
  applyLineHash(true);
});

// Click a table header to sort by that column: ascending, descending, then the
// file's original order again. Empty cells stay last. A row's note row moves with it.
// A header with data-default-sort (from a default-sort comment) is sorted that way on load.
document.querySelectorAll('.content table').forEach(function (table) {
  var body = table.tBodies[0];
  if (!body) return;
  var original = Array.prototype.filter.call(body.rows, function (r) { return !r.classList.contains('md-note-row'); });
  var noteRows = new Map();
  Array.prototype.forEach.call(body.rows, function (r) {
    var prev = r.previousElementSibling;
    if (r.classList.contains('md-note-row') && prev) noteRows.set(prev, r);
  });
  var headers = table.querySelectorAll('thead th');
  // Sort by column `col` in direction `dir` ('asc', 'desc', or '' for file order).
  function sortBy(th, col, dir) {
    headers.forEach(function (h) { delete h.dataset.sort; });
    var rows = original.slice();
    if (dir) {
      th.dataset.sort = dir;
      rows.sort(function (a, b) {
        var x = a.cells[col] ? a.cells[col].textContent.trim() : '';
        var y = b.cells[col] ? b.cells[col].textContent.trim() : '';
        // Empty cells go last in both directions, as in spreadsheets.
        if (!x || !y) return (x ? 0 : 1) - (y ? 0 : 1);
        var c = x.localeCompare(y, undefined, { numeric: true, sensitivity: 'base' });
        return dir === 'asc' ? c : -c;
      });
    }
    rows.forEach(function (r) {
      body.appendChild(r);
      if (noteRows.has(r)) body.appendChild(noteRows.get(r));
    });
  }
  headers.forEach(function (th, col) {
    th.addEventListener('click', function () {
      sortBy(th, col, { '': 'asc', asc: 'desc', desc: '' }[th.dataset.sort || '']);
    });
    if (th.dataset.defaultSort) sortBy(th, col, th.dataset.defaultSort);
  });
});

// Upgrade the server's Pygments markup to VS Code-grade highlighting. Shiki runs
// the same TextMate grammars and themes VS Code ships, so this is a strict
// improvement -- and if the CDN is unreachable the Pygments markup just stays.
(async function () {
  var blocks = Array.prototype.slice.call(document.querySelectorAll('.code-block[data-lang]'));
  if (!blocks.length) return;
  var langs = Array.from(new Set(blocks.map(function (b) { return b.dataset.lang; })));
  var BASE = 'https://esm.sh/';
  var V = window.__shikiVersion;
  var THEME = window.__shikiTheme;
  try {
    var core = await import(BASE + 'shiki@' + V + '/core');
    var engineMod = await import(BASE + 'shiki@' + V + '/engine/javascript');
    var highlighter = await core.createHighlighterCore({
      themes: [import(BASE + '@shikijs/themes@' + V + '/' + THEME)],
      langs: langs.map(function (l) { return import(BASE + '@shikijs/langs@' + V + '/' + l); }),
      engine: engineMod.createJavaScriptRegexEngine({ forgiving: true }),
    });
    var loaded = new Set(highlighter.getLoadedLanguages());
    blocks.forEach(function (block) {
      var lang = block.dataset.lang;
      if (!loaded.has(lang)) return;
      var code = block.querySelector('code');
      if (!code) return;
      // Read the source back from the line spans: the markup carries no newlines
      // between them (they are display:block), so textContent would run together.
      var lines = code.querySelectorAll('.line');
      var text = lines.length
        ? Array.prototype.map.call(lines, function (l) { return l.textContent; }).join('\n')
        : code.textContent.replace(/\n$/, '');
      var html = highlighter.codeToHtml(text, {
        lang: lang,
        theme: THEME,
        transformers: [{
          // Keep the server's line shape so #L-n anchors keep resolving.
          line: function (node, line) { node.properties.id = 'L-' + line; },
          code: function (node) {
            node.children = node.children.filter(function (c) { return c.type === 'element'; });
          },
          pre: function (node) { node.properties.style = ''; node.properties.tabindex = '-1'; },
        }],
      });
      var parsed = new DOMParser().parseFromString(html, 'text/html');
      var fresh = parsed.querySelector('pre code');
      if (fresh) code.replaceWith(fresh);
    });
    document.querySelectorAll('.line-highlighted').forEach(function (el) {
      el.classList.remove('line-highlighted');
    });
    applyLineHash(false);
    document.documentElement.classList.add('shiki-ready');
  } catch (err) {
    console.warn('shiki upgrade skipped:', err);
  }
})();

// The sidebar header lists every running md-viewer by its root, fetched each time it opens.
(function () {
  var box = document.querySelector('.servers');
  if (!box) return;
  var list = box.querySelector('.server-list');
  function note(text) {
    var li = document.createElement('li');
    li.className = 'server-note';
    li.textContent = text;
    list.replaceChildren(li);
  }
  box.addEventListener('toggle', function () {
    if (!box.open) return;
    note('Looking…');
    fetch('/_servers').then(function (r) { return r.json(); }).then(function (servers) {
      var others = servers.filter(function (s) { return !s.current; });
      if (!others.length) { note('No other servers'); return; }
      list.replaceChildren.apply(list, others.map(function (s) {
        var li = document.createElement('li');
        var a = document.createElement('a');
        a.href = s.url;
        a.title = s.root;
        var name = document.createElement('span');
        name.className = 'server-name';
        name.textContent = s.root.split('/').filter(Boolean).pop() || s.root;
        var where = document.createElement('span');
        where.className = 'server-path';
        where.textContent = s.label;
        a.append(name, where);
        li.appendChild(a);
        return li;
      }));
    }).catch(function () { note('Could not list servers'); });
  });
})();

// The ⧉ buttons copy a path: the root beside the sidebar header (e.g. to start claude there), the
// open file's absolute path beside the path line.
document.querySelectorAll('button[data-copy]').forEach(function (button) {
  var label = button.textContent;
  button.addEventListener('click', function () {
    navigator.clipboard.writeText(button.dataset.copy).then(function () {
      button.textContent = '\u2713';
      setTimeout(function () { button.textContent = label; }, 1200);
    }).catch(function (err) { console.warn('copy failed:', err); });
  });
});

// The source control panel beside the diff hides like the sidebar, remembered per browser.
var scmToggle = document.querySelector('.scm-toggle');
if (scmToggle) {
  scmToggle.addEventListener('click', function () {
    var hidden = document.documentElement.classList.toggle('scm-hidden');
    try { localStorage.setItem('scmHidden', hidden ? '1' : ''); } catch (e) {}
  });
}

// Notes: on a rendered page, hovering a block without a note shows "+ note"; with text selected in
// a block it quotes the selection. A table's body rows are blocks; its header row stands for the
// table. Notes are saved into the file as comments, one per block, and shown as boxes with edit and
// delete. Every save reloads the page, so it always shows the file as it is.
(function () {
  var doc = document.querySelector('.markdown-body[data-notes-version]');
  if (!doc) return;
  var path = doc.dataset.notesPath;
  var fileVersion = doc.dataset.notesVersion;

  var add = document.createElement('button');
  add.className = 'note-add';
  add.type = 'button';
  add.textContent = '+ note';
  add.hidden = true;
  document.body.appendChild(add);
  var hovered = null;

  function place(block) {
    hovered = block;
    var rect = block.getBoundingClientRect();
    add.style.top = (rect.top + window.scrollY) + 'px';
    add.style.left = (rect.left + window.scrollX - add.offsetWidth - 6) + 'px';
  }

  document.addEventListener('mouseover', function (e) {
    if (e.target === add || doc.querySelector('.note-editor')) return;
    var block = e.target.closest && e.target.closest('[data-block]');
    if (block && (e.target.closest('.md-note, .md-note-row') || block.hasAttribute('data-noted'))) {
      add.hidden = true; hovered = null;
      return;
    }
    if (!block || !doc.contains(block)) {
      // Content that takes no notes (raw HTML, footnotes) hides the button, so it never seems to
      // belong there. Gaps between blocks and the margin keep it, so the pointer can reach it.
      if (e.target !== doc && doc.contains(e.target)) { add.hidden = true; hovered = null; }
      return;
    }
    add.hidden = false;
    place(block);
  });

  function selectionIn() {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed) return null;
    var node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    var block = node && node.closest('[data-block]');
    if (!block || !doc.contains(block) || block.hasAttribute('data-noted')) return null;
    return { block: block, quote: sel.toString().trim() };
  }

  // Keep the selection when the button is pressed.
  add.addEventListener('mousedown', function (e) { e.preventDefault(); });
  add.addEventListener('click', function () {
    var picked = selectionIn() || (hovered && { block: hovered, quote: '' });
    if (!picked) return;
    add.hidden = true;
    openEditor({ block: picked.block, quote: picked.quote, text: '' });
  });

  // method: PUT to set a block's note, DELETE to remove it.
  function send(method, body, editor) {
    body.path = path;
    body.version = fileVersion;
    return fetch('/_notes', {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (r.ok) { location.reload(); return; }
        var message = data.error || ('Error ' + r.status);
        if (editor) editor.querySelector('.note-error').textContent = message;
        else showError(message);
      });
    }).catch(function (err) {
      if (editor) editor.querySelector('.note-error').textContent = String(err);
      else showError(String(err));
    });
  }

  function showError(message) {
    var bar = document.querySelector('.note-flash') || document.createElement('div');
    bar.className = 'note-flash';
    bar.textContent = message;
    doc.parentElement.insertBefore(bar, doc);
  }

  // opts: { block, quote, text } for a new note, or { note, block, quote, text } to edit one, where
  // block is the block's element for a new note and its number for an edit.
  function openEditor(opts) {
    var existing = doc.querySelector('.note-editor');
    if (existing) existing.remove();
    var editor = document.createElement('div');
    editor.className = 'note-editor';
    if (opts.quote) {
      var q = document.createElement('div');
      q.className = 'md-note-quote';
      q.textContent = opts.quote;
      editor.appendChild(q);
    }
    var area = document.createElement('textarea');
    area.value = opts.text;
    area.placeholder = 'Note for the next Claude session';
    area.rows = 3;
    var row = document.createElement('div');
    row.className = 'note-actions';
    var save = document.createElement('button');
    save.type = 'button';
    save.textContent = 'Save';
    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'Cancel';
    var hint = document.createElement('span');
    hint.className = 'note-hint';
    hint.textContent = '⌘/Ctrl+Enter to save, Esc to cancel';
    var err = document.createElement('span');
    err.className = 'note-error';
    row.append(save, cancel, hint, err);
    editor.append(area, row);

    var holder = editor;  // what Cancel removes
    if (opts.note) {
      opts.note.hidden = true;
      opts.note.after(editor);
    } else if (opts.block.tagName === 'TR') {
      holder = document.createElement('tr');
      holder.className = 'md-note-row';
      var cell = document.createElement('td');
      cell.colSpan = opts.block.closest('table').querySelectorAll('thead th').length || 1;
      cell.appendChild(editor);
      holder.appendChild(cell);
      opts.block.after(holder);
    } else if (opts.block.tagName === 'LI') {
      opts.block.appendChild(editor);
    } else {
      var after = opts.block;
      while (after.nextElementSibling && after.nextElementSibling.classList.contains('md-note')) {
        after = after.nextElementSibling;
      }
      after.after(editor);
    }

    function close() {
      holder.remove();
      if (opts.note) opts.note.hidden = false;
    }
    function submit() {
      if (!area.value.trim()) { err.textContent = 'A note needs text.'; return; }
      save.disabled = true;
      var block = opts.note ? opts.block : parseInt(opts.block.dataset.block, 10);
      send('PUT', { block: block, quote: opts.quote, text: area.value }, editor)
        .then(function () { save.disabled = false; });
    }
    save.addEventListener('click', submit);
    cancel.addEventListener('click', close);
    area.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); }
      if (e.key === 'Escape') { e.preventDefault(); close(); }
    });
    area.focus();
  }

  doc.querySelectorAll('.md-note[data-note-block]').forEach(function (note) {
    var block = parseInt(note.dataset.noteBlock, 10);
    var tools = document.createElement('span');
    tools.className = 'md-note-tools';
    var edit = document.createElement('button');
    edit.type = 'button';
    edit.title = 'Edit note';
    edit.textContent = '✎';
    var del = document.createElement('button');
    del.type = 'button';
    del.title = 'Delete note';
    del.textContent = '×';
    tools.append(edit, del);
    note.prepend(tools);
    edit.addEventListener('click', function () {
      var quote = note.querySelector('.md-note-quote');
      openEditor({
        note: note,
        block: block,
        quote: quote ? quote.textContent : '',
        text: note.querySelector('.md-note-text').textContent,
      });
    });
    del.addEventListener('click', function () { send('DELETE', { block: block }); });
  });
})();

// Edit view: a textarea with the file's source, saved by ⌘S / Ctrl+S or the Save button only.
(function () {
  var area = document.querySelector('textarea.edit-text');
  if (!area) return;
  var save = document.querySelector('.edit-save');
  var status = document.querySelector('.edit-status');
  var fileVersion = area.dataset.version;
  var saved = area.value;
  var saving = false;

  function show(message, isError) {
    status.textContent = message;
    status.classList.toggle('error', !!isError);
  }

  function refresh() {
    if (!saving) show(area.value === saved ? '' : 'Unsaved');
  }

  function submit() {
    if (saving) return;
    var text = area.value;
    saving = true;
    save.disabled = true;
    show('Saving…');
    fetch('/_file', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: area.dataset.path, version: fileVersion, text: text }),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.error || ('Error ' + r.status));
        fileVersion = data.version;
        saved = text;
      });
    }).then(function () {
      saving = false;
      show(area.value === saved ? 'Saved' : 'Unsaved');
    }, function (err) {
      saving = false;
      show(err.message || String(err), true);
    }).then(function () { save.disabled = false; });
  }

  area.addEventListener('input', refresh);
  save.addEventListener('click', submit);
  document.addEventListener('keydown', function (e) {
    if (e.key === 's' && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });
  window.addEventListener('beforeunload', function (e) {
    if (area.value !== saved) { e.preventDefault(); e.returnValue = ''; }
  });
})();

// Read aloud: on a rendered page, a selection shows a 🔊 button by its end; clicking it speaks the
// selection with the browser's speech, always with a Chinese voice (English too, with its accent).
// Text with hanzi speaks only its Chinese runs. While speaking the button shows ⏹ and stays, so a click always stops it.
(function () {
  var doc = document.querySelector('.markdown-body[data-notes-version]');
  if (!doc || !window.speechSynthesis) return;
  var synth = window.speechSynthesis;
  synth.getVoices(); // Chrome fills the list asynchronously; ask early so it's ready at click time.

  var button = document.createElement('button');
  button.className = 'speak-button';
  button.type = 'button';
  button.hidden = true;
  document.body.appendChild(button);
  var speaking = false;
  var run = 0; // Bumped per speak, so events from cancelled speech are ignored.
  var utterances = []; // Held so Chrome can't collect them before they end.

  var HAN = /\p{Script=Han}/u;
  // Hanzi with the punctuation and digits that sit among them.
  var CHINESE = /[\p{Script=Han}0-9　-〿！-＠…—·]+/gu;
  var NOT_READ = '.md-note, .md-note-row, .note-editor, .note-add, .speak-button';

  function show(label) {
    button.textContent = label;
    button.title = label === '⏹' ? 'Stop' : 'Read aloud';
  }

  function selectedRange() {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    var active = document.activeElement;
    if (active && /^(TEXTAREA|INPUT)$/.test(active.tagName)) return null;
    var range = sel.getRangeAt(0);
    var common = range.commonAncestorContainer;
    if (common.nodeType !== 1) common = common.parentElement;
    if (!common || !(doc === common || doc.contains(common))) return null;
    return range;
  }

  // The range's text as laid out (cells and blocks apart), minus note boxes and editors.
  function textOf(range) {
    var holder = document.createElement('div');
    holder.style.cssText = 'position:absolute;left:-99999px;top:0;white-space:pre-wrap';
    holder.appendChild(range.cloneContents());
    holder.querySelectorAll(NOT_READ).forEach(function (el) { el.remove(); });
    document.body.appendChild(holder);
    var text = holder.innerText;
    holder.remove();
    return text.trim();
  }

  function place(range) {
    var rects = range.getClientRects();
    var rect = rects.length ? rects[rects.length - 1] : range.getBoundingClientRect();
    button.hidden = false;
    button.style.top = (rect.top + window.scrollY - button.offsetHeight - 4) + 'px';
    button.style.left = (rect.right + window.scrollX - button.offsetWidth / 2) + 'px';
  }

  function update() {
    if (speaking) return;
    var range = selectedRange();
    if (!range || !textOf(range)) { button.hidden = true; return; }
    show('🔊');
    place(range);
  }

  function chineseVoice() {
    var voices = synth.getVoices().filter(function (v) { return v.lang === 'zh-CN'; });
    var ranks = [/Premium/, /Enhanced/, /Google/, /Tingting/];
    for (var i = 0; i < ranks.length; i++) {
      var hit = voices.find(function (v) { return ranks[i].test(v.name); });
      if (hit) return hit;
    }
    return voices[0] || null;
  }

  // Sentences, one utterance each: Chrome cuts off a long utterance without an end event.
  function chunks(text) {
    return (text.match(/[^。！？.!?\n]+[。！？.!?]*/g) || [])
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s; });
  }

  function finish(id) {
    if (id !== run) return;
    speaking = false;
    utterances = [];
    update();
  }

  function speak(text) {
    synth.cancel();
    var id = ++run;
    var chinese = HAN.test(text);
    var parts;
    if (chinese) {
      parts = [];
      (text.match(CHINESE) || []).forEach(function (piece) {
        if (HAN.test(piece)) parts = parts.concat(chunks(piece));
      });
    } else {
      parts = chunks(text);
    }
    if (!parts.length) return;
    var voice = chineseVoice();
    utterances = parts.map(function (part, i) {
      var u = new SpeechSynthesisUtterance(part);
      u.lang = 'zh-CN';
      if (voice) u.voice = voice;
      u.rate = chinese ? 0.85 : 1;
      u.onerror = function () { finish(id); };
      if (i === parts.length - 1) u.onend = function () { finish(id); };
      return u;
    });
    speaking = true;
    show('⏹');
    utterances.forEach(function (u) { synth.speak(u); });
  }

  // Keep the selection when the button is pressed.
  button.addEventListener('mousedown', function (e) { e.preventDefault(); });
  button.addEventListener('click', function () {
    if (speaking) {
      run++;
      synth.cancel();
      speaking = false;
      utterances = [];
      update();
      return;
    }
    var range = selectedRange();
    if (range) speak(textOf(range));
  });

  ['mouseup', 'keyup'].forEach(function (type) {
    document.addEventListener(type, function (e) {
      if (e.target === button) return;
      setTimeout(update, 0); // After the click has collapsed or set the selection.
    });
  });
  window.addEventListener('pagehide', function () { synth.cancel(); });
})();
