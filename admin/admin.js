(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var loginView = $('#loginView'), appView = $('#appView'), list = $('#list'), timer = null;

  function api(method, url, body) {
    var opts = { method: method, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(url, opts).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, data: j }; }); });
  }
  function toast(text) {
    var t = document.createElement('div'); t.className = 'toast'; t.textContent = text; document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2200);
  }
  function show(loggedIn) {
    loginView.hidden = loggedIn; appView.hidden = !loggedIn;
    clearInterval(timer);
    if (loggedIn) { load(); timer = setInterval(load, 30000); }
  }

  /* sign in / out */
  $('#loginForm').addEventListener('submit', function (e) {
    e.preventDefault(); var msg = $('#loginMsg'); msg.textContent = '';
    api('POST', '/api/admin/login', { password: $('#password').value }).then(function (r) {
      if (r.data.ok) { $('#password').value = ''; show(true); } else { msg.textContent = r.data.error || 'Could not sign in.'; }
    }).catch(function () { msg.textContent = 'Cannot reach the server.'; });
  });
  $('#logoutBtn').addEventListener('click', function () { api('POST', '/api/admin/logout').then(function () { show(false); }); });

  /* list */
  function fmt(iso) {
    var d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString([], { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
  function meta(label, value, href) {
    var s = el('span'); s.appendChild(el('b', '', label));
    if (href) { var a = el('a', '', value); a.href = href; s.appendChild(a); } else { s.appendChild(document.createTextNode(value)); }
    return s;
  }
  function card(e) {
    var c = el('article', 'card' + (e.status === 'new' ? ' is-new' : ''));
    var top = el('div', 'top'), who = el('div', 'who', e.name); who.appendChild(el('span', 'ref', e.ref));
    top.appendChild(who); top.appendChild(el('div', 'when', fmt(e.created_at))); c.appendChild(top);
    var m = el('div', 'meta');
    m.appendChild(meta('Phone', e.phone, 'tel:' + e.phone.replace(/[^\d+]/g, '')));
    if (e.email) m.appendChild(meta('Email', e.email, 'mailto:' + e.email));
    m.appendChild(meta('Service', e.service || '-')); c.appendChild(m);
    c.appendChild(el('div', 'text', e.message));
    var row = el('div', 'row'), sel = el('select');
    [['new', 'New'], ['contacted', 'Contacted'], ['closed', 'Closed']].forEach(function (o) { var op = el('option', '', o[1]); op.value = o[0]; if (o[0] === e.status) op.selected = true; sel.appendChild(op); });
    sel.addEventListener('change', function () { api('PATCH', '/api/admin/enquiries/' + e.id, { status: sel.value }).then(function (r) { toast(r.data.ok ? 'Status updated' : 'Could not update'); load(); }); });
    var note = el('input'); note.type = 'text'; note.placeholder = 'Add a note (saved when you click away)'; note.value = e.note || ''; note.maxLength = 1000;
    note.addEventListener('change', function () { api('PATCH', '/api/admin/enquiries/' + e.id, { note: note.value }).then(function (r) { toast(r.data.ok ? 'Note saved' : 'Could not save'); }); });
    var del = el('button', 'btn danger small', 'Delete'); del.type = 'button';
    del.addEventListener('click', function () { if (confirm('Delete the enquiry from ' + e.name + '? This cannot be undone.')) api('DELETE', '/api/admin/enquiries/' + e.id).then(function () { toast('Deleted'); load(); }); });
    row.appendChild(sel); row.appendChild(note); row.appendChild(del); c.appendChild(row);
    if (e.mail && e.mail !== 'sent') c.appendChild(el('div', 'mail', 'Email: ' + e.mail));
    return c;
  }
  function load() {
    var q = encodeURIComponent($('#search').value.trim()), s = $('#statusFilter').value;
    api('GET', '/api/admin/enquiries?q=' + q + '&status=' + s).then(function (r) {
      if (r.status === 401) { show(false); return; }
      var d = r.data, c = d.counts || {};
      $('#cNew').textContent = c.new || 0; $('#cContacted').textContent = c.contacted || 0; $('#cClosed').textContent = c.closed || 0;
      $('#cTotal').textContent = (c.new || 0) + (c.contacted || 0) + (c.closed || 0);
      $('#mailNotice').hidden = !!d.mail;
      list.textContent = '';
      (d.enquiries || []).forEach(function (e) { list.appendChild(card(e)); });
      $('#empty').hidden = (d.enquiries || []).length > 0;
      document.title = (c.new ? '(' + c.new + ') ' : '') + 'Enquiries | Matsyodari Renewables Admin';
    });
  }
  var debounce; $('#search').addEventListener('input', function () { clearTimeout(debounce); debounce = setTimeout(load, 300); });
  $('#statusFilter').addEventListener('change', load); $('#refreshBtn').addEventListener('click', load);

  api('GET', '/api/admin/me').then(function (r) { show(!!r.data.ok); }).catch(function () { show(false); });
})();
