
const DATA = JSON.parse(document.getElementById('review-data').textContent);
const KEY = 'gkreview:' + DATA.episode + ':' + (DATA.fingerprint || '').slice(0, 8);
let anns = {};
try { anns = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { anns = {}; }
anns = Object.assign({}, DATA.annotations || {}, anns);
function save() { try { localStorage.setItem(KEY, JSON.stringify(anns)); } catch (e) {} }
function parseExpected(text) {
  const out = {};
  (text || '').split(';').forEach(function (part) {
    part = part.trim();
    if (!part || part.indexOf('=') < 0) return;
    const i = part.indexOf('=');
    const k = part.slice(0, i).trim(), raw = part.slice(i + 1).trim();
    if (!k) return;
    try { out[k] = JSON.parse(raw); } catch (e) { out[k] = raw; }
  });
  return out;
}
function expectedText(exp) {
  return Object.keys(exp || {}).map(function (k) {
    const v = exp[k];
    return k + '=' + (typeof v === 'string' ? v : JSON.stringify(v));
  }).join(';');
}
function renderControls() {
  document.querySelectorAll('tr[data-ann-id]').forEach(function (tr) {
    const id = tr.getAttribute('data-ann-id');
    const cell = tr.querySelector('td.ann');
    if (!cell || cell.dataset.wired) return;
    cell.dataset.wired = '1';
    const a = anns[id] || {};
    const sel = document.createElement('select');
    ['', 'ok', 'bad', 'unsure'].forEach(function (v) {
      const o = document.createElement('option');
      o.value = v; o.textContent = v || '—';
      if ((a.verdict || '') === v) o.selected = true;
      sel.appendChild(o);
    });
    const comment = document.createElement('input');
    comment.type = 'text'; comment.placeholder = '评论'; comment.value = a.comment || '';
    const exp = document.createElement('input');
    exp.type = 'text'; exp.placeholder = 'expected: k=v;k=v'; exp.value = expectedText(a.expected);
    function upd() {
      const e = parseExpected(exp.value);
      if (!sel.value && !comment.value && !Object.keys(e).length) { delete anns[id]; }
      else { anns[id] = { verdict: sel.value, comment: comment.value, expected: e }; }
      save();
      tr.classList.toggle('bad', sel.value === 'bad');
    }
    sel.addEventListener('change', upd);
    comment.addEventListener('input', upd);
    exp.addEventListener('input', upd);
    cell.appendChild(sel); cell.appendChild(comment); cell.appendChild(exp);
    if (a.verdict === 'bad') tr.classList.add('bad');
  });
}
function exportAnnotations() {
  const list = [];
  document.querySelectorAll('tr[data-ann-id]').forEach(function (tr) {
    const id = tr.getAttribute('data-ann-id');
    const a = anns[id];
    if (!a || !a.verdict) return;
    list.push({ id: id, target: tr.getAttribute('data-target'),
                key: isNaN(+tr.getAttribute('data-key')) ? tr.getAttribute('data-key') : +tr.getAttribute('data-key'),
                verdict: a.verdict, comment: a.comment || '', expected: a.expected || {} });
  });
  const payload = { schema: DATA.schema, episode: DATA.episode, fingerprint: DATA.fingerprint,
                    exported_at: new Date().toISOString(), annotations: list };
  const blob = new Blob([JSON.stringify(payload, null, 1)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'annotations_' + DATA.episode + '.json';
  link.click();
  URL.revokeObjectURL(link.href);
}
function importAnnotations(file) {
  const reader = new FileReader();
  reader.onload = function () {
    try {
      const payload = JSON.parse(String(reader.result));
      if (payload.schema !== DATA.schema || payload.episode !== DATA.episode) {
        alert('schema/episode 不符，拒绝导入'); return;
      }
      (payload.annotations || []).forEach(function (a) {
        if (a && a.id && a.verdict) {
          anns[a.id] = { verdict: a.verdict, comment: a.comment || '', expected: a.expected || {} };
        }
      });
      save();
      document.querySelectorAll('td.ann').forEach(function (c) { c.innerHTML = ''; delete c.dataset.wired; });
      renderControls();
    } catch (e) { alert('导入失败: ' + e); }
  };
  reader.readAsText(file);
}
document.getElementById('btn-export').addEventListener('click', exportAnnotations);
document.getElementById('btn-import').addEventListener('click', function () {
  document.getElementById('file-import').click();
});
document.getElementById('file-import').addEventListener('change', function (ev) {
  if (ev.target.files && ev.target.files[0]) importAnnotations(ev.target.files[0]);
  ev.target.value = '';
});
document.getElementById('btn-clear').addEventListener('click', function () {
  if (!confirm('清除本局全部标注？')) return;
  anns = {}; save();
  document.querySelectorAll('td.ann').forEach(function (c) { c.innerHTML = ''; delete c.dataset.wired; });
  document.querySelectorAll('tr.bad').forEach(function (tr) { tr.classList.remove('bad'); });
  renderControls();
});
renderControls();
