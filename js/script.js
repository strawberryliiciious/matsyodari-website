(function () {
  'use strict';
  var $ = function (s, c) { return (c || document).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };

  /* header: scrolled state, back-to-top, active link */
  var header = $('.site-header'), toTop = $('#toTop');
  function onScroll() {
    var y = window.scrollY || document.documentElement.scrollTop;
    header.classList.toggle('scrolled', y > 40);
    toTop.classList.toggle('show', y > 600);
  }
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll();

  /* mobile menu */
  var menuBtn = $('#menuBtn'), nav = $('#nav');
  function closeMenu() { nav.classList.remove('open'); menuBtn.setAttribute('aria-expanded', 'false'); menuBtn.setAttribute('aria-label', 'Open menu'); }
  menuBtn.addEventListener('click', function () {
    var open = nav.classList.toggle('open');
    menuBtn.setAttribute('aria-expanded', String(open));
    menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  });
  $$('a', nav).forEach(function (a) { a.addEventListener('click', closeMenu); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeMenu(); closeLightbox(); } });

  /* active nav link */
  var links = $$('.nav a[href^="#"]:not(.btn)');
  var sections = links.map(function (a) { return $(a.getAttribute('href')); }).filter(Boolean);
  if ('IntersectionObserver' in window) {
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          links.forEach(function (a) { a.classList.toggle('active', a.getAttribute('href') === '#' + en.target.id); });
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    sections.forEach(function (s) { spy.observe(s); });
  }

  /* reveal on scroll */
  var reveals = $$('.reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { var t = en.target; t.classList.add('in'); io.unobserve(t); setTimeout(function () { t.classList.remove('reveal', 'in'); t.style.transitionDelay = ''; }, 1100); } });
    }, { threshold: 0.12 });
    reveals.forEach(function (el, i) { el.style.transitionDelay = (i % 3) * 80 + 'ms'; io.observe(el); });
  } else { reveals.forEach(function (el) { el.classList.add('in'); }); }

  /* counters */
  var counters = $$('[data-count]');
  function runCounter(el) {
    var target = parseInt(el.getAttribute('data-count'), 10), start = null, dur = 1400;
    function step(t) {
      if (!start) start = t;
      var p = Math.min((t - start) / dur, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  if ('IntersectionObserver' in window) {
    var co = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { runCounter(en.target); co.unobserve(en.target); } });
    }, { threshold: 0.6 });
    counters.forEach(function (c) { co.observe(c); });
  } else { counters.forEach(function (c) { c.textContent = c.getAttribute('data-count'); }); }

  /* tabs */
  var tabs = $$('[role="tab"]');
  function selectTab(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      $('#' + t.getAttribute('aria-controls')).hidden = !on;
    });
    if (focus) tab.focus();
  }
  tabs.forEach(function (tab, i) {
    tab.addEventListener('click', function () { selectTab(tab); });
    tab.addEventListener('keydown', function (e) {
      var n = null;
      if (e.key === 'ArrowRight') n = tabs[(i + 1) % tabs.length];
      if (e.key === 'ArrowLeft') n = tabs[(i - 1 + tabs.length) % tabs.length];
      if (n) { e.preventDefault(); selectTab(n, true); }
    });
  });
  $$('[data-tab]').forEach(function (a) {
    a.addEventListener('click', function () { var t = $('#tab-' + a.getAttribute('data-tab')); if (t) selectTab(t); });
  });

  /* FAQ: one open at a time */
  var faqs = $$('.faq details');
  faqs.forEach(function (d) {
    d.addEventListener('toggle', function () { if (d.open) faqs.forEach(function (o) { if (o !== d) o.open = false; }); });
  });

  /* lightbox */
  var lb = $('#lightbox'), lbImg = $('img', lb), lbCap = $('p', lb);
  function closeLightbox() { lb.hidden = true; document.body.style.overflow = ''; }
  $$('.gallery button').forEach(function (b) {
    b.addEventListener('click', function () {
      lbImg.src = b.getAttribute('data-full'); lbImg.alt = b.getAttribute('data-alt'); lbCap.textContent = b.getAttribute('data-alt');
      lb.hidden = false; document.body.style.overflow = 'hidden';
    });
  });
  lb.addEventListener('click', function (e) { if (e.target === lb || e.target.classList.contains('lb-close')) closeLightbox(); });

  /* quote form: saved by the backend (server.py); WhatsApp and email stay as backups */
  var form = $('#quoteForm'), status = $('#formStatus'), sendBtn = $('#sendBtn');
  var WA = '919423712487', MAIL = 'matsyodaripvtltd@rediffmail.com';
  /* Where the backend lives. Same server by default. If the site is opened with VS Code
     Live Server (port 5500) the backend is expected on http://127.0.0.1:8000 (python server.py). */
  var API = (typeof window.MATSYODARI_API === 'string') ? window.MATSYODARI_API : (location.port === '5500' ? 'http://127.0.0.1:8000' : '');
  var DARK = '#0a4a8f', OK = '#0b6bcb';
  function setErr(id, msg) {
    var f = $('#' + id), e = $('.err[data-for="' + id + '"]');
    f.closest('.field').classList.toggle('invalid', !!msg); if (e) e.textContent = msg || '';
    return !msg;
  }
  function val(id) { return $('#' + id).value.trim(); }
  function validate() {
    var ok = true;
    ok = setErr('name', val('name').length < 2 ? 'Please enter your name.' : '') && ok;
    ok = setErr('phone', !/^[+\d][\d\s-]{7,17}$/.test(val('phone')) ? 'Enter a valid phone number.' : '') && ok;
    ok = setErr('email', val('email') && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val('email')) ? 'Enter a valid email address.' : '') && ok;
    ok = setErr('service', !val('service') ? 'Please choose a service.' : '') && ok;
    ok = setErr('message', val('message').length < 10 ? 'Please add a few details (at least 10 characters).' : '') && ok;
    return ok;
  }
  function buildText() {
    return 'Hello Matsyodari Renewables,\n\nI would like a quotation.\n\nName: ' + val('name') + '\nPhone: ' + val('phone') +
      (val('email') ? '\nEmail: ' + val('email') : '') + '\nService: ' + val('service') + '\nDetails: ' + val('message');
  }
  function say(text, good) { status.style.color = good ? OK : DARK; status.textContent = text; }
  function openWhatsApp() { window.open('https://wa.me/' + WA + '?text=' + encodeURIComponent(buildText()), '_blank', 'noopener'); }
  $$('input,select,textarea', form).forEach(function (el) {
    el.addEventListener('input', function () { status.textContent = ''; if (el.closest('.field').classList.contains('invalid')) validate(); });
  });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!validate()) { say('Please fix the highlighted fields.'); return; }
    sendBtn.disabled = true; var label = sendBtn.textContent; sendBtn.textContent = 'Sending...'; say('');
    var payload = { name: val('name'), phone: val('phone'), email: val('email'), service: val('service'), message: val('message'), website: $('#website').value };
    var ctl = ('AbortController' in window) ? new AbortController() : null, to = ctl ? setTimeout(function () { ctl.abort(); }, 15000) : null;
    fetch(API + '/api/enquiries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, status: r.status, j: j }; }); })
      .then(function (res) {
        if (res.ok && res.j.ok) {
          form.reset(); say('Thank you! Your enquiry ' + (res.j.ref || '') + ' has been received. We will contact you shortly.', true);
        } else if (res.j.errors) {
          Object.keys(res.j.errors).forEach(function (k) { setErr(k, res.j.errors[k]); }); say('Please fix the highlighted fields.');
        } else { say(res.j.error || 'Sorry, something went wrong. Please try WhatsApp or Email below.'); }
      })
      .catch(function () { say('We could not reach our server. Please use the WhatsApp or Email button, or call +91 94237 12487.'); })
      .then(function () { if (to) clearTimeout(to); sendBtn.disabled = false; sendBtn.textContent = label; });
  });
  $('#waBtn').addEventListener('click', function () {
    if (!validate()) { say('Please fix the highlighted fields.'); return; }
    openWhatsApp(); say('WhatsApp is opening with your request. Just press send.', true);
  });
  $('#mailBtn').addEventListener('click', function () {
    if (!validate()) { say('Please fix the highlighted fields.'); return; }
    window.location.href = 'mailto:' + MAIL + '?subject=' + encodeURIComponent('Quotation request: ' + val('service')) + '&body=' + encodeURIComponent(buildText());
    say('Your email app is opening with your request.', true);
  });

  /* tilt cards + interactive logo (mouse and pen only) */
  var fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  var calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (fine && !calm) {
    $$('.cards .card, .process li, .team .person').forEach(function (el) {
      el.classList.add('tilt');
      el.addEventListener('pointermove', function (e) {
        var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        el.style.transform = 'perspective(900px) rotateX(' + ((0.5 - y) * 9).toFixed(2) + 'deg) rotateY(' + ((x - 0.5) * 11).toFixed(2) + 'deg) translateY(-6px)';
        el.style.setProperty('--mx', (x * 100).toFixed(1) + '%'); el.style.setProperty('--my', (y * 100).toFixed(1) + '%');
      });
      el.addEventListener('pointerleave', function () { el.style.transform = ''; });
    });
    var hero = $('.hero'), logo = $('#heroLogo'), tilt = $('.logo-tilt'), halo = $('.halo');
    if (hero && logo) {
      hero.addEventListener('pointermove', function (e) {
        var r = logo.getBoundingClientRect(), dx = (e.clientX - (r.left + r.width / 2)) / (window.innerWidth / 2), dy = (e.clientY - (r.top + r.height / 2)) / (window.innerHeight / 2);
        dx = Math.max(-1, Math.min(1, dx)); dy = Math.max(-1, Math.min(1, dy));
        tilt.style.transform = 'rotateY(' + (dx * 18).toFixed(2) + 'deg) rotateX(' + (-dy * 16).toFixed(2) + 'deg) translate(' + (dx * 10).toFixed(1) + 'px,' + (dy * 8).toFixed(1) + 'px)';
        halo.style.transform = 'translate(' + (-dx * 14).toFixed(1) + 'px,' + (-dy * 12).toFixed(1) + 'px)';
      });
      hero.addEventListener('pointerleave', function () { tilt.style.transform = ''; halo.style.transform = ''; });
    }
  }

  $('#year').textContent = new Date().getFullYear();
})();
