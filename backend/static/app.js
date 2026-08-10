/* Minimal front-end glue: upload + polling, chat, briefings, item actions.
   No framework — keeps the app lightweight and easy to maintain. */

function $(sel, root = document) { return root.querySelector(sel); }
function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
function esc(s) { return (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

/* very small markdown: **bold**, headings, - lists, [#id] links */
function mdToHtml(md) {
  if (!md) return '';
  const lines = md.split('\n'); let out = ''; let inList = false;
  for (let raw of lines) {
    let line = esc(raw);
    line = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    line = line.replace(/\[#(\d+)\]/g, '<a href="/conversation/$1">[#$1]</a>');
    if (/^\s*[-*]\s+/.test(raw)) {
      if (!inList) { out += '<ul>'; inList = true; }
      out += '<li>' + line.replace(/^\s*[-*]\s+/, '') + '</li>';
    } else {
      if (inList) { out += '</ul>'; inList = false; }
      if (/^###\s+/.test(raw)) out += '<h3>' + line.replace(/^###\s+/, '') + '</h3>';
      else if (/^##\s+/.test(raw)) out += '<h2>' + line.replace(/^##\s+/, '') + '</h2>';
      else if (/^#\s+/.test(raw)) out += '<h2>' + line.replace(/^#\s+/, '') + '</h2>';
      else if (raw.trim() === '') out += '';
      else out += '<p>' + line + '</p>';
    }
  }
  if (inList) out += '</ul>';
  return out;
}
function isRtl(s) { return /[؀-ۿ]/.test(s || ''); }

/* ---- Add conversation modal ---- */
function openAdd() { $('#addModal').classList.add('open'); }
function closeAdd() { $('#addModal').classList.remove('open'); }

async function submitConversation(ev) {
  ev.preventDefault();
  const form = ev.target;
  const btn = $('#addSubmit'); btn.disabled = true; btn.textContent = 'Uploading…';
  const fd = new FormData(form);
  try {
    const r = await fetch('/api/conversations', { method: 'POST', body: fd });
    if (!r.ok) { const t = await r.text(); throw new Error(t); }
    const data = await r.json();
    closeAdd();
    trackProcessing(data.id);
  } catch (e) {
    alert('Could not add conversation: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Add & analyze';
  }
}

function trackProcessing(id) {
  const banner = $('#procBanner');
  if (banner) { banner.style.display = 'flex'; $('#procText').textContent = 'Processing conversation #' + id + '…'; }
  const poll = setInterval(async () => {
    try {
      const r = await fetch(`/api/conversations/${id}/status`);
      const s = await r.json();
      if (s.status === 'done') { clearInterval(poll); location.href = '/conversation/' + id; }
      else if (s.status === 'error') { clearInterval(poll); if (banner) $('#procText').textContent = 'Error: ' + (s.error || 'failed'); }
      else if (banner) { $('#procText').textContent = 'Working… (' + s.status + ') — you can keep using the app'; }
    } catch (e) { clearInterval(poll); }
  }, 2000);
}

/* ---- Chat ---- */
async function sendChat(q) {
  const input = $('#chatInput');
  const query = q || (input && input.value.trim());
  if (!query) return;
  if (input) input.value = '';
  const log = $('#chatLog');
  log.appendChild(msgEl('user', esc(query)));
  const thinking = msgEl('ai', '<span class="faint">Searching your memory…</span>');
  log.appendChild(thinking); log.scrollTop = log.scrollHeight;
  try {
    const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) });
    const data = await r.json();
    let html = mdToHtml(data.answer);
    if (data.sources && data.sources.length) {
      html += '<div class="sources"><strong>Sources:</strong> ' + data.sources.map(s =>
        `<a href="/conversation/${s.id}">#${s.id} ${esc(s.title)}</a>`).join(' · ') + '</div>';
    }
    thinking.innerHTML = html;
    if (isRtl(data.answer)) thinking.classList.add('rtl');
  } catch (e) {
    thinking.innerHTML = '<span class="err">Something went wrong. Try again.</span>';
  }
  log.scrollTop = log.scrollHeight;
}
function msgEl(role, html) { const m = el('div', 'msg ' + role, html); return m; }
function chatKey(ev) { if (ev.key === 'Enter') { ev.preventDefault(); sendChat(); } }

/* ---- Briefing ---- */
async function loadBriefing(kind, id) {
  const box = $('#briefingBox');
  box.innerHTML = '<span class="faint">Preparing your briefing…</span>';
  try {
    const r = await fetch(`/api/briefing/${kind}/${id}`);
    const data = await r.json();
    box.innerHTML = mdToHtml(data.briefing);
    if (isRtl(data.briefing)) box.classList.add('rtl');
  } catch (e) { box.innerHTML = '<span class="err">Could not generate briefing.</span>'; }
}

/* ---- Item status ---- */
async function setItem(id, status, ev) {
  const fd = new FormData(); fd.append('status', status);
  await fetch('/api/items/' + id, { method: 'POST', body: fd });
  const li = ev.target.closest('[data-item]');
  if (li) { if (status === 'open') li.classList.remove('doneline'); else li.remove(); }
}

async function delConversation(id) {
  if (!confirm('Delete this conversation and everything extracted from it?')) return;
  await fetch('/api/conversations/' + id, { method: 'DELETE' });
  location.href = '/conversations';
}
async function reprocess(id) {
  await fetch('/api/conversations/' + id + '/reprocess', { method: 'POST' });
  trackProcessing(id);
}
