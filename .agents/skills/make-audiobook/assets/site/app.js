/* make-audiobook — static web player.
   Vanilla ES2020. Reads book.json + chapters/<id>.json from the same directory. */

(function () {
  'use strict';

  /* ------------------------------------------------------------ helpers */

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var isNum = function (v) { return typeof v === 'number' && isFinite(v); };
  var clamp = function (v, a, b) { return v < a ? a : (v > b ? b : v); };
  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtClock(sec) {
    if (!isNum(sec) || sec < 0) sec = 0;
    sec = Math.floor(sec);
    var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return h ? h + ':' + pad(m) + ':' + pad(s) : m + ':' + pad(s);
  }

  /* ------------------------------------------------------------ i18n */

  var STR = {
    zh: {
      kicker: '有声书',
      contents: '目录',
      tocHeading: '目录',
      continueLabel: '继续收听',
      play: '播放', pause: '暂停',
      prevCh: '上一章', nextCh: '下一章',
      back15: '后退 15 秒', fwd30: '前进 30 秒',
      seek: '播放进度',
      speed: '播放速度',
      autoLabel: '连播',
      autoOn: '自动连播：开', autoOff: '自动连播：关',
      sleepLabel: '定时',
      sleepOff: '睡眠定时：关闭',
      sleepOn: function (m) { return '睡眠定时：' + m + ' 分钟后暂停'; },
      backToPlayback: '回到当前位置',
      noAudio: '这一章还没有生成音频，下面是文稿。',
      transcriptOnly: '仅文稿',
      endOfBook: '全书播放完毕。',
      endOfChapter: '本章播放完毕。',
      backToContents: '返回目录',
      finished: '已听完',
      listened: function (p) { return '已听 ' + p + '%'; },
      chapterCount: function (n) { return '共 ' + n + ' 章'; },
      duration: function (h, m) { return h ? h + ' 小时 ' + m + ' 分钟' : m + ' 分钟'; },
      about: function (s) { return '约 ' + s; },
      noDuration: '时长待定',
      notFound: '找不到这一章。',
      loadError: '加载失败',
      loading: '载入中…',
      audioError: '音频加载失败。',
      prevKicker: '上一章', nextKicker: '下一章'
    },
    en: {
      kicker: 'Audiobook',
      contents: 'Contents',
      tocHeading: 'Contents',
      continueLabel: 'Continue',
      play: 'Play', pause: 'Pause',
      prevCh: 'Previous chapter', nextCh: 'Next chapter',
      back15: 'Back 15 seconds', fwd30: 'Forward 30 seconds',
      seek: 'Seek',
      speed: 'Playback speed',
      autoLabel: 'Auto',
      autoOn: 'Autoplay next: on', autoOff: 'Autoplay next: off',
      sleepLabel: 'Timer',
      sleepOff: 'Sleep timer: off',
      sleepOn: function (m) { return 'Sleep timer: pause in ' + m + ' min'; },
      backToPlayback: 'Back to playback',
      noAudio: 'Audio has not been generated for this chapter yet — the transcript is below.',
      transcriptOnly: 'Transcript only',
      endOfBook: 'End of the book.',
      endOfChapter: 'End of this chapter.',
      backToContents: 'Back to contents',
      finished: 'Finished',
      listened: function (p) { return p + '% listened'; },
      chapterCount: function (n) { return n + (n === 1 ? ' chapter' : ' chapters'); },
      duration: function (h, m) { return h ? h + ' h ' + m + ' min' : m + ' min'; },
      about: function (s) { return 'about ' + s; },
      noDuration: 'Duration pending',
      notFound: 'Chapter not found.',
      loadError: 'Could not load',
      loading: 'Loading…',
      audioError: 'Audio failed to load.',
      prevKicker: 'Previous', nextKicker: 'Next'
    }
  };

  var T = STR.en;
  var lang = 'en';

  function fmtDuration(sec) {
    if (!isNum(sec) || sec <= 0) return T.noDuration;
    var total = Math.round(sec / 60);
    return T.duration(Math.floor(total / 60), total % 60);
  }

  /* ------------------------------------------------------------ storage */

  var NS = 'book';
  function key(k) { return 'audiobook:' + NS + ':' + k; }
  function lsGet(k, dflt) {
    try {
      var v = localStorage.getItem(key(k));
      return v == null ? dflt : JSON.parse(v);
    } catch (e) { return dflt; }
  }
  function lsSet(k, v) {
    try { localStorage.setItem(key(k), JSON.stringify(v)); } catch (e) { /* private mode */ }
  }

  /* ------------------------------------------------------------ dom refs */

  var view = $('#view'), topbar = $('#topbar'), topTitle = $('#topTitle'),
      backLabel = $('#backLabel'), player = $('#player'), audio = $('#audio'),
      pill = $('#pill'), pillLabel = $('#pillLabel'),
      seek = $('#seek'), scrubBuf = $('#scrubBuf'), scrubPlayed = $('#scrubPlayed'),
      tCur = $('#tCur'), tDur = $('#tDur'), barTitle = $('#barTitle'),
      btnPlay = $('#btnPlay'), btnPrev = $('#btnPrev'), btnNext = $('#btnNext'),
      btnBack15 = $('#btnBack15'), btnFwd30 = $('#btnFwd30'),
      btnSpeed = $('#btnSpeed'), btnAuto = $('#btnAuto'), btnSleep = $('#btnSleep');

  /* ------------------------------------------------------------ state */

  var book = null;
  var chapters = [];
  var manifests = {};            // id -> manifest
  var state = {
    viewId: null,                // chapter currently on screen
    audioId: null,               // chapter currently loaded in <audio>
    units: [],                   // timed highlight units of the viewed chapter
    segs: [],                    // segments of the viewed chapter
    active: -1,                  // index into units
    activeWord: -1
  };
  var SPEEDS = [0.8, 1.0, 1.2, 1.5, 1.75, 2.0];
  var speed = 1.0;
  var autoNext = true;
  var follow = true;
  var wantPlay = false;          // play as soon as the next chapter is ready
  var routeToken = 0;
  var pendingMath = null;
  var scrubbing = false;
  var sleepUntil = 0, sleepMin = 0, sleepTimer = null;
  var followTarget = null, programmaticUntil = 0;
  var rafId = 0, saveTimer = 0, lastPos = -1;

  /* ------------------------------------------------------------ boot */

  function boot() {
    fetch('book.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('book.json ' + r.status);
        return r.json();
      })
      .then(start)
      .catch(function (err) {
        view.innerHTML = '<div class="fatal">' + esc(T.loadError) +
          ' <code>book.json</code><br>' + esc(err && err.message || err) + '</div>';
      });
  }

  function start(data) {
    book = data || {};
    chapters = Array.isArray(book.chapters) ? book.chapters : [];
    lang = /^zh/i.test(book.language || '') ? 'zh' : 'en';
    T = STR[lang];
    // the book's own tag wins; `lang` is only the UI-string bucket (zh or en)
    document.documentElement.lang = book.language || (lang === 'zh' ? 'zh-Hans' : 'en');
    document.title = book.title || 'Audiobook';
    NS = String(book.title || 'book').slice(0, 80);

    speed = SPEEDS.indexOf(lsGet('speed', 1)) >= 0 ? lsGet('speed', 1) : 1.0;
    autoNext = lsGet('autoplay', true) !== false;

    applyStaticStrings();
    wireEvents();
    measurePlayer();
    window.addEventListener('hashchange', route);
    route();
  }

  function applyStaticStrings() {
    backLabel.textContent = T.contents;
    pillLabel.textContent = T.backToPlayback;
    seek.setAttribute('aria-label', T.seek);
    var label = function (el, s) { el.title = s; el.setAttribute('aria-label', s); };
    label(btnPrev, T.prevCh);
    label(btnNext, T.nextCh);
    label(btnBack15, T.back15);
    label(btnFwd30, T.fwd30);
    label(btnPlay, T.play);
    btnSpeed.setAttribute('aria-label', T.speed);
    btnAuto.textContent = T.autoLabel;
    updateSpeedChip();
    updateAutoChip();
    updateSleepChip();
  }

  /* ------------------------------------------------------------ routing */

  function route() {
    var h = location.hash || '#/';
    var m = h.match(/^#\/ch\/(.+)$/);
    routeToken++;
    if (m) showChapter(decodeURIComponent(m[1]));
    else showIndex();
  }

  function chapterById(id) {
    for (var i = 0; i < chapters.length; i++) if (chapters[i].id === id) return chapters[i];
    return null;
  }
  function chapterIndex(id) {
    for (var i = 0; i < chapters.length; i++) if (chapters[i].id === id) return i;
    return -1;
  }

  function goto(id, play) {
    wantPlay = !!play;
    if (location.hash === '#/ch/' + encodeURIComponent(id)) route();
    else location.hash = '#/ch/' + encodeURIComponent(id);
  }

  /* ------------------------------------------------------------ index view */

  function showIndex() {
    state.viewId = null;
    state.units = [];
    state.segs = [];
    state.active = -1;
    topbar.hidden = true;
    stopTick();

    var totalDur = 0, known = 0;
    chapters.forEach(function (c) { if (isNum(c.duration)) { totalDur += c.duration; known++; } });

    var pos = lsGet('pos', null);
    var resumeCh = pos && pos.chapterId ? chapterById(pos.chapterId) : null;

    var html = '<div class="cover">';
    html += '<div class="cover-kicker">' + esc(T.kicker) + '</div>';
    html += '<h1 class="cover-title">' + esc(book.title || '') + '</h1>';
    if (book.subtitle) html += '<p class="cover-sub">' + esc(book.subtitle) + '</p>';
    if (book.author) html += '<p class="cover-author">' + esc(book.author) + '</p>';
    html += '<hr class="cover-rule">';
    if (book.description) html += '<p class="cover-desc">' + esc(book.description) + '</p>';
    var meta = T.chapterCount(chapters.length);
    if (known) {
      meta += ' · ' + (known < chapters.length ? T.about(fmtDuration(totalDur)) : fmtDuration(totalDur));
    }
    html += '<p class="cover-meta">' + esc(meta) + '</p>';
    if (resumeCh) {
      html += '<button class="continue" id="btnContinue" type="button">' +
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">' +
        '<path d="M8.6 5.4v13.2a.6.6 0 0 0 .92.5l10.1-6.6a.6.6 0 0 0 0-1l-10.1-6.6a.6.6 0 0 0-.92.5z" fill="currentColor" stroke-linejoin="round"/></svg>' +
        '<span class="continue-label">' + esc(T.continueLabel + ' · ' + (resumeCh.title || '')) + '</span></button>';
    }
    html += '</div>';

    html += '<h2 class="toc-heading">' + esc(T.tocHeading) + '</h2><ol class="toc">';
    chapters.forEach(function (c, i) {
      var pr = lsGet('prog:' + c.id, null);
      var dur = isNum(c.duration) ? c.duration : (pr && isNum(pr.d) ? pr.d : null);
      var frac = (pr && isNum(pr.t) && isNum(dur) && dur > 0) ? clamp(pr.t / dur, 0, 1) : 0;
      var done = frac > 0.97;
      var sub = [];
      if (!c.audio) sub.push(T.transcriptOnly);
      else if (isNum(dur)) sub.push(fmtClock(dur));
      if (done) sub.push(T.finished);
      else if (frac > 0.005) sub.push(T.listened(Math.round(frac * 100)));
      var cls = 'toc-item' + (done ? ' done' : '') + (state.audioId === c.id ? ' current' : '');
      html += '<li><a class="' + cls + '" href="#/ch/' + encodeURIComponent(c.id) + '">' +
        '<span class="toc-num">' + (i + 1 < 10 ? '0' : '') + (i + 1) + '</span>' +
        '<span class="toc-body"><span class="toc-title">' + esc(c.title || c.id) + '</span>' +
        (sub.length ? '<span class="toc-sub">' + esc(sub.join(' · ')) + '</span>' : '') +
        '</span><span class="toc-mark" aria-hidden="true">&#10003;</span>' +
        '<span class="toc-progress"><i style="width:' + (done ? 100 : Math.round(frac * 100)) + '%"></i></span>' +
        '</a></li>';
    });
    html += '</ol>';

    view.innerHTML = html;
    if (resumeCh) {
      $('#btnContinue').addEventListener('click', function () {
        goto(resumeCh.id, true);
      });
    }
    window.scrollTo(0, 0);
    setPlayerVisible();
    hidePill();
  }

  /* ------------------------------------------------------------ chapter view */

  function showChapter(id) {
    var ch = chapterById(id);
    if (!ch) {
      view.innerHTML = '<div class="fatal">' + esc(T.notFound) +
        '<br><a href="#/" style="color:var(--accent)">' + esc(T.backToContents) + '</a></div>';
      topbar.hidden = true;
      return;
    }
    var token = routeToken;
    state.viewId = id;
    topbar.hidden = false;
    topTitle.textContent = book.title || '';
    view.innerHTML = '<div class="loading">' + esc(T.loading) + '</div>';

    loadManifest(ch).then(function (man) {
      if (token !== routeToken) return;
      renderChapter(ch, man);
    }).catch(function (err) {
      if (token !== routeToken) return;
      view.innerHTML = '<div class="fatal">' + esc(T.loadError) + ' <code>' +
        esc(ch.manifest || ('chapters/' + ch.id + '.json')) + '</code><br>' +
        esc(err && err.message || err) + '</div>';
    });
  }

  function loadManifest(ch) {
    if (manifests[ch.id]) return Promise.resolve(manifests[ch.id]);
    var url = ch.manifest || ('chapters/' + ch.id + '.json');
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
      return r.json();
    }).then(function (m) {
      manifests[ch.id] = m;
      return m;
    });
  }

  function renderChapter(ch, man) {
    var segments = Array.isArray(man.segments) ? man.segments : [];
    state.segs = segments;
    state.units = buildUnits(segments);
    state.active = -1;
    state.activeWord = -1;

    var art = document.createElement('article');
    art.className = 'chapter' + (ch.audio ? '' : ' no-audio');

    if (!ch.audio) {
      var notice = document.createElement('div');
      notice.className = 'notice';
      notice.innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">' +
        '<path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z"/><path d="M12 8v5"/><path d="M12 16.2v.1"/></svg>' +
        '<span>' + esc(T.noAudio) + '</span>';
      art.appendChild(notice);
    }

    art.appendChild(renderTranscript(segments));
    art.appendChild(renderChapterNav(ch));

    view.innerHTML = '';
    view.appendChild(art);
    typeset(art);

    ensureAudio(ch, wantPlay);
    wantPlay = false;
    setPlayerVisible();
    follow = true;
    hidePill();
    window.scrollTo(0, 0);
    syncHighlight(true);
    if (state.audioId === ch.id && !audio.paused) scrollToActive(false);
  }

  function renderTranscript(segments) {
    var root = document.createElement('div');
    root.className = 'transcript';
    root.id = 'transcript';
    var list = null, stanza = null;

    segments.forEach(function (seg) {
      var kind = seg.kind || 'para';
      if (kind !== 'item') list = null;
      if (kind !== 'line') stanza = null;

      var el = segElement(seg, kind);
      if (kind === 'item') {
        if (!list) {
          list = document.createElement('div');
          list.className = 'seg-list';
          root.appendChild(list);
        }
        list.appendChild(el);
      } else if (kind === 'line') {
        if (!stanza) {
          stanza = document.createElement('blockquote');
          stanza.className = 'stanza';
          root.appendChild(stanza);
        }
        stanza.appendChild(el);
      } else {
        root.appendChild(el);
      }
    });
    return root;
  }

  // Each segment becomes one wrapper element carrying data-i, with the
  // generated html inside it. `html` is produced locally by the build script.
  function segElement(seg, kind) {
    var tmp = document.createElement('div');
    tmp.innerHTML = String(seg.html == null ? '' : seg.html).trim();

    var el = document.createElement('div');
    var only = tmp.children.length === 1 && tmp.childNodes.length === 1 ? tmp.firstElementChild : null;
    if (only && only.tagName === 'LI') {           // tolerate <li> html too
      while (only.firstChild) el.appendChild(only.firstChild);
    } else {
      while (tmp.firstChild) el.appendChild(tmp.firstChild);
    }
    el.className = 'seg seg-' + kind;
    el.dataset.i = seg.i;

    if (kind === 'item') {
      // items arrive self-contained: <p class="item" data-depth="1" data-marker="•">
      var src = (only && only.hasAttribute && only.hasAttribute('data-depth')) ? only
        : el.querySelector('[data-depth], [data-marker]');
      var depth = parseInt((src && src.getAttribute('data-depth')) || seg.depth || 1, 10);
      if (!(depth >= 1)) depth = 1;
      el.style.setProperty('--d', depth - 1);
      el.setAttribute('data-marker',
        (src && src.getAttribute('data-marker')) || seg.marker || '\u2022');
    }
    return el;
  }

  function renderChapterNav(ch) {
    var i = chapterIndex(ch.id);
    var nav = document.createElement('nav');
    nav.className = 'chapter-nav';
    var prev = i > 0 ? chapters[i - 1] : null;
    var next = i >= 0 && i < chapters.length - 1 ? chapters[i + 1] : null;
    var html = '';
    if (prev) {
      html += '<a class="prev" href="#/ch/' + encodeURIComponent(prev.id) + '">' +
        '<span class="nav-kicker">&#8249; ' + esc(T.prevKicker) + '</span>' +
        '<span class="nav-title">' + esc(prev.title || prev.id) + '</span></a>';
    }
    if (next) {
      html += '<a class="next" href="#/ch/' + encodeURIComponent(next.id) + '">' +
        '<span class="nav-kicker">' + esc(T.nextKicker) + ' &#8250;</span>' +
        '<span class="nav-title">' + esc(next.title || next.id) + '</span></a>';
    }
    if (!html) {
      html = '<a class="prev" href="#/">' +
        '<span class="nav-kicker">&#8249;</span>' +
        '<span class="nav-title">' + esc(T.backToContents) + '</span></a>';
    }
    nav.innerHTML = html;
    return nav;
  }

  /* ------------------------------------------------------------ KaTeX */

  function typeset(el) {
    if (!el) return;
    if (typeof window.renderMathInElement !== 'function') { pendingMath = el; return; }
    try {
      window.renderMathInElement(el, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\[', right: '\\]', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\(', right: '\\)', display: false }
        ],
        throwOnError: false,
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option']
      });
    } catch (e) { /* CDN down or bad LaTeX: raw source stays visible */ }
  }

  window.addEventListener('load', function () {
    if (pendingMath) { var el = pendingMath; pendingMath = null; typeset(el); }
  });

  /* ------------------------------------------------------------ timing units */

  // A unit = one timed segment plus the display segments that trail it
  // (display blocks carry the end time of the spoken segment before them).
  function buildUnits(segments) {
    var units = [];
    segments.forEach(function (s) {
      var timed = isNum(s.start);
      if (s.kind === 'display') {
        if (units.length) { units[units.length - 1].idx.push(s.i); return; }
        if (!timed) return;
      }
      if (!timed) return;
      units.push({
        start: s.start,
        end: isNum(s.end) ? s.end : s.start,
        idx: [s.i],
        seg: s,
        wrapped: false
      });
    });
    units.sort(function (a, b) { return a.start - b.start; });
    return units;
  }

  // last unit whose start <= t (binary search)
  function findUnit(t) {
    var u = state.units, lo = 0, hi = u.length - 1, best = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (u[mid].start <= t) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return best;
  }

  function segEl(i) { return view.querySelector('.seg[data-i="' + i + '"]'); }

  function activeEl() {
    if (state.active < 0 || !state.units[state.active]) return null;
    return segEl(state.units[state.active].idx[0]);
  }

  function syncHighlight(force) {
    if (!state.units.length) return;
    if (state.audioId !== state.viewId) {            // reading a chapter that is not playing
      if (state.active >= 0) clearActive();
      return;
    }
    var t = audio.currentTime;
    var i = findUnit(t);
    if (i !== state.active || force) {
      clearActive();
      state.active = i;
      var u = state.units[i];
      if (u) {
        u.idx.forEach(function (n) {
          var el = segEl(n);
          if (el) el.classList.add('active');
        });
        if (follow) scrollToActive(true);
      }
      state.activeWord = -1;
    }
    syncWords(t);
  }

  function clearActive() {
    var els = view.querySelectorAll('.seg.active');
    for (var i = 0; i < els.length; i++) els[i].classList.remove('active');
    var ws = view.querySelectorAll('.w.on');
    for (var j = 0; j < ws.length; j++) ws[j].classList.remove('on');
    state.active = -1;
    state.activeWord = -1;
  }

  /* ------------------------------------------------------------ word highlight */

  function syncWords(t) {
    var u = state.units[state.active];
    if (!u || !u.seg || !Array.isArray(u.seg.words) || !u.seg.words.length) return;
    var el = segEl(u.idx[0]);
    if (!el) return;
    if (!u.wrapped) {
      u.wrapped = true;
      u.words = wrapWords(el, u.seg.words) ? u.seg.words : null;
    }
    if (!u.words) return;

    var w = u.words, lo = 0, hi = w.length - 1, best = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (w[mid][0] <= t) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    if (best >= 0 && t > w[best][1] + 0.9) best = -1;   // long gap: drop the highlight
    if (best === state.activeWord) return;
    state.activeWord = best;
    var on = el.querySelectorAll('.w.on');
    for (var i = 0; i < on.length; i++) on[i].classList.remove('on');
    if (best >= 0) {
      var next = el.querySelectorAll('.w[data-w="' + best + '"]');
      for (var j = 0; j < next.length; j++) next[j].classList.add('on');
    }
  }

  // Wrap each word of `words` in a span, but only when the segment's visible
  // text matches the concatenated word texts exactly (whitespace ignored).
  // Text inside KaTeX output is never touched.
  function wrapWords(el, words) {
    if (el.querySelector('.w')) return true;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.data) return NodeFilter.FILTER_REJECT;
        var p = n.parentNode;
        while (p && p !== el) {
          if (p.nodeType === 1) {
            var cl = p.className || '';
            if (typeof cl !== 'string') cl = '';
            if (/katex/.test(cl) || p.tagName === 'ANNOTATION') return NodeFilter.FILTER_REJECT;
          }
          p = p.parentNode;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    if (!nodes.length) return false;

    var chars = [];      // {node, off, ws}
    var visible = '';
    nodes.forEach(function (node) {
      for (var i = 0; i < node.data.length; i++) {
        var ch = node.data[i];
        var ws = /\s/.test(ch);
        chars.push({ node: node, off: i, ws: ws, w: -1 });
        if (!ws) visible += ch;
      }
    });

    var texts = words.map(function (w) { return String(w[2] == null ? '' : w[2]).replace(/\s+/g, ''); });
    if (texts.join('') !== visible) return false;

    var ci = 0;
    for (var wi = 0; wi < texts.length; wi++) {
      for (var k = 0; k < texts[wi].length; k++) {
        while (ci < chars.length && chars[ci].ws) ci++;
        if (ci >= chars.length) return false;
        chars[ci].w = wi;
        ci++;
      }
    }

    // rebuild each text node as runs of equal word index
    var byNode = new Map();
    chars.forEach(function (c) {
      if (!byNode.has(c.node)) byNode.set(c.node, []);
      byNode.get(c.node).push(c);
    });
    byNode.forEach(function (cs, node) {
      var frag = document.createDocumentFragment();
      var run = '', runW = cs.length ? cs[0].w : -1;
      var flush = function () {
        if (!run) return;
        if (runW < 0) frag.appendChild(document.createTextNode(run));
        else {
          var sp = document.createElement('span');
          sp.className = 'w';
          sp.setAttribute('data-w', runW);
          sp.textContent = run;
          frag.appendChild(sp);
        }
        run = '';
      };
      cs.forEach(function (c) {
        if (c.w !== runW) { flush(); runW = c.w; }
        run += c.node.data[c.off];
      });
      flush();
      if (node.parentNode) node.parentNode.replaceChild(frag, node);
    });
    return true;
  }

  /* ------------------------------------------------------------ follow / scroll */

  function scrollToActive(smooth) {
    var el = activeEl();
    if (!el) return;
    var r = el.getBoundingClientRect();
    var maxTop = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    var top = clamp(window.scrollY + r.top - window.innerHeight * 0.35, 0, maxTop);
    var dist = Math.abs(top - window.scrollY);
    if (dist < 4) return;
    followTarget = top;
    var anim = smooth && !REDUCED;
    programmaticUntil = performance.now() + (anim ? Math.min(2200, 420 + dist * 1.1) : 120);
    try {
      window.scrollTo({ top: top, behavior: anim ? 'smooth' : 'auto' });
    } catch (e) { window.scrollTo(0, top); }
  }

  function userScrolled() {
    if (!follow || !state.viewId) return;
    if (state.audioId !== state.viewId || state.active < 0) return;
    follow = false;
    if (!audio.paused || audio.currentTime > 0) showPill();
  }

  function showPill() { pill.hidden = false; }
  function hidePill() { pill.hidden = true; }

  /* ------------------------------------------------------------ audio */

  function ensureAudio(ch, play) {
    if (!ch.audio) {
      // transcript-only: leave whatever is loaded alone so playback continues
      updateBar();
      return;
    }
    var abs = new URL(ch.audio, location.href).href;
    if (state.audioId !== ch.id || audio.src !== abs) {
      saveProgress();
      state.audioId = ch.id;
      audio.src = ch.audio;
      audio.playbackRate = speed;
      var pr = lsGet('prog:' + ch.id, null);
      var d = isNum(ch.duration) ? ch.duration : (pr && isNum(pr.d) ? pr.d : null);
      var t = pr && isNum(pr.t) ? pr.t : 0;
      // only touch currentTime when there is something to resume from;
      // a freshly assigned src already starts at 0.
      var startAt = (t > 5 && (!isNum(d) || t < d - 5)) ? t : 0;
      if (startAt) seekWhenReady(startAt);
      // point "continue" at this chapter right away, without touching its
      // stored progress (currentTime is still 0 at this moment)
      lastPos = -1;
      lsSet('pos', { chapterId: ch.id, time: startAt, at: Date.now() });
    }
    updateBar();
    if (play) playAudio();
  }

  var pendingSeek = null;
  function seekWhenReady(t) {
    if (audio.readyState >= 1) {
      try { audio.currentTime = t; } catch (e) { /* ignore */ }
      updateTimes();
      return;
    }
    pendingSeek = t;
    audio.addEventListener('loadedmetadata', function () {
      if (pendingSeek === null) return;
      try { audio.currentTime = pendingSeek; } catch (e) { /* ignore */ }
      pendingSeek = null;
      updateTimes();
      syncHighlight(true);
    }, { once: true });
  }

  function playAudio() {
    var p = audio.play();
    if (p && p.catch) p.catch(function () { /* autoplay blocked; user can tap play */ });
  }

  function togglePlay() {
    if (!state.audioId) {
      var ch = state.viewId ? chapterById(state.viewId) : null;
      if (ch && ch.audio) { ensureAudio(ch, true); return; }
      return;
    }
    if (audio.paused) playAudio(); else audio.pause();
  }

  function nudge(delta) {
    if (!state.audioId) return;
    var d = isNum(audio.duration) ? audio.duration : Infinity;
    audio.currentTime = clamp(audio.currentTime + delta, 0, d - 0.25);
    syncHighlight(true);
    if (follow) scrollToActive(true);
  }

  function seekTo(t, play) {
    if (!state.audioId) return;
    t = Math.max(0, t);
    if (audio.readyState >= 1) {
      pendingSeek = null;
      audio.currentTime = t;
      syncHighlight(true);
    } else {
      seekWhenReady(t);
    }
    if (play && audio.paused) playAudio();
  }

  function siblingChapter(delta) {
    var id = state.viewId || state.audioId;
    var i = chapterIndex(id);
    if (i < 0) return null;
    var j = i + delta;
    return (j >= 0 && j < chapters.length) ? chapters[j] : null;
  }

  function gotoSibling(delta) {
    var c = siblingChapter(delta);
    if (!c) return;
    var playing = !audio.paused && !!state.audioId;
    goto(c.id, playing);
  }

  /* ------------------------------------------------------------ player bar */

  function setPlayerVisible() {
    var viewCh = state.viewId ? chapterById(state.viewId) : null;
    var hasAudio = !!state.audioId;
    if (!hasAudio && !viewCh) { player.hidden = true; measurePlayer(); return; }
    player.hidden = false;
    player.classList.toggle('no-audio', !hasAudio);
    seek.disabled = !hasAudio;
    updateBar();
    measurePlayer();
  }

  function updateBar() {
    var shownId = state.audioId || state.viewId;
    var ch = shownId ? chapterById(shownId) : null;
    barTitle.textContent = ch ? (ch.title || ch.id) : '';
    btnPrev.disabled = !siblingChapter(-1);
    btnNext.disabled = !siblingChapter(1);
    updateTimes();
  }

  function updateTimes() {
    var d = isNum(audio.duration) ? audio.duration : 0;
    var t = isNum(audio.currentTime) ? audio.currentTime : 0;
    if (!scrubbing) {
      seek.max = d || 0;
      seek.value = t;
      scrubPlayed.style.width = d ? (clamp(t / d, 0, 1) * 100) + '%' : '0%';
    }
    tCur.textContent = fmtClock(t);
    tDur.textContent = d ? fmtClock(d) : '--:--';
  }

  function updateBuffered() {
    var d = audio.duration;
    if (!isNum(d) || !d) { scrubBuf.style.width = '0%'; return; }
    var end = 0, t = audio.currentTime;
    for (var i = 0; i < audio.buffered.length; i++) {
      if (audio.buffered.start(i) <= t + 0.5 && audio.buffered.end(i) > end) end = audio.buffered.end(i);
    }
    scrubBuf.style.width = (clamp(end / d, 0, 1) * 100) + '%';
  }

  function measurePlayer() {
    var h = player.hidden ? 24 : player.offsetHeight;
    document.documentElement.style.setProperty('--player-h', h + 'px');
  }

  function updateSpeedChip() {
    var label = (Math.round(speed * 100) / 100).toString();
    if (label.indexOf('.') < 0) label += '.0';
    btnSpeed.textContent = label + '×';
    btnSpeed.classList.toggle('on', speed !== 1);
  }

  function cycleSpeed(dir) {
    var i = SPEEDS.indexOf(speed);
    if (i < 0) i = 1;
    i = (i + (dir || 1) + SPEEDS.length) % SPEEDS.length;
    speed = SPEEDS[i];
    audio.playbackRate = speed;
    lsSet('speed', speed);
    updateSpeedChip();
    updatePositionState();
  }

  function updateAutoChip() {
    btnAuto.classList.toggle('on', autoNext);
    btnAuto.setAttribute('aria-pressed', autoNext ? 'true' : 'false');
    btnAuto.setAttribute('aria-label', autoNext ? T.autoOn : T.autoOff);
    btnAuto.title = autoNext ? T.autoOn : T.autoOff;
  }

  function updateSleepChip() {
    if (!sleepMin) {
      btnSleep.textContent = T.sleepLabel;
      btnSleep.classList.remove('on');
      btnSleep.title = T.sleepOff;
      btnSleep.setAttribute('aria-label', T.sleepOff);
      return;
    }
    var left = Math.max(0, Math.ceil((sleepUntil - Date.now()) / 60000));
    btnSleep.textContent = left + (lang === 'zh' ? ' 分' : 'm');
    btnSleep.classList.add('on');
    btnSleep.title = T.sleepOn(sleepMin);
    btnSleep.setAttribute('aria-label', T.sleepOn(sleepMin));
  }

  var SLEEPS = [0, 15, 30, 45, 60];
  function cycleSleep() {
    var i = SLEEPS.indexOf(sleepMin);
    sleepMin = SLEEPS[(i + 1) % SLEEPS.length];
    if (sleepTimer) { clearInterval(sleepTimer); sleepTimer = null; }
    if (sleepMin) {
      sleepUntil = Date.now() + sleepMin * 60000;
      sleepTimer = setInterval(function () {
        if (Date.now() >= sleepUntil) {
          audio.pause();
          sleepMin = 0;
          clearInterval(sleepTimer);
          sleepTimer = null;
        }
        updateSleepChip();
      }, 1000);
    }
    updateSleepChip();
  }

  /* ------------------------------------------------------------ ticking / saving */

  function isPlaying() { return state.audioId && !audio.paused && !audio.ended; }

  function tick() {
    rafId = 0;
    if (!isPlaying()) return;
    syncHighlight(false);
    updateTimes();
    updatePositionState();
    rafId = requestAnimationFrame(tick);
  }
  function startTick() { if (!rafId) rafId = requestAnimationFrame(tick); }
  function stopTick() { if (rafId) { cancelAnimationFrame(rafId); rafId = 0; } }

  function saveProgress() {
    if (!state.audioId) return;
    var t = audio.currentTime, d = audio.duration;
    if (!isNum(t)) return;
    var r = Math.round(t * 10) / 10;
    if (r === lastPos) return;
    lastPos = r;
    lsSet('prog:' + state.audioId, { t: r, d: isNum(d) ? d : null, at: Date.now() });
    lsSet('pos', { chapterId: state.audioId, time: r, at: Date.now() });
  }

  function setPlaybackState(v) {
    if ('mediaSession' in navigator) {
      try { navigator.mediaSession.playbackState = v; } catch (e) { /* ignore */ }
    }
  }

  function updatePositionState() {
    if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;
    var d = audio.duration;
    if (!isNum(d) || d <= 0) return;
    try {
      navigator.mediaSession.setPositionState({
        duration: d,
        playbackRate: audio.playbackRate || 1,
        position: clamp(audio.currentTime, 0, d)
      });
    } catch (e) { /* ignore */ }
  }

  function setMediaSession(ch) {
    if (!('mediaSession' in navigator)) return;
    try {
      navigator.mediaSession.metadata = new window.MediaMetadata({
        title: ch.title || ch.id,
        artist: book.author || '',
        album: book.title || ''
      });
    } catch (e) { /* ignore */ }
    var set = function (action, fn) {
      try { navigator.mediaSession.setActionHandler(action, fn); } catch (e) { /* unsupported */ }
    };
    set('play', function () { playAudio(); });
    set('pause', function () { audio.pause(); });
    set('seekbackward', function (d) { nudge(-((d && d.seekOffset) || 15)); });
    set('seekforward', function (d) { nudge((d && d.seekOffset) || 30); });
    set('previoustrack', function () { gotoSibling(-1); });
    set('nexttrack', function () { gotoSibling(1); });
    set('seekto', function (d) { if (d && isNum(d.seekTime)) seekTo(d.seekTime, false); });
  }

  /* ------------------------------------------------------------ events */

  function wireEvents() {
    btnPlay.addEventListener('click', togglePlay);
    btnBack15.addEventListener('click', function () { nudge(-15); });
    btnFwd30.addEventListener('click', function () { nudge(30); });
    btnPrev.addEventListener('click', function () { gotoSibling(-1); });
    btnNext.addEventListener('click', function () { gotoSibling(1); });
    btnSpeed.addEventListener('click', function () { cycleSpeed(1); });
    btnAuto.addEventListener('click', function () {
      autoNext = !autoNext;
      lsSet('autoplay', autoNext);
      updateAutoChip();
    });
    btnSleep.addEventListener('click', cycleSleep);

    seek.addEventListener('input', function () {
      scrubbing = true;
      var v = parseFloat(seek.value) || 0;
      var d = isNum(audio.duration) ? audio.duration : 0;
      scrubPlayed.style.width = d ? (clamp(v / d, 0, 1) * 100) + '%' : '0%';
      tCur.textContent = fmtClock(v);
    });
    var commit = function () {
      if (!scrubbing) return;
      scrubbing = false;
      seekTo(parseFloat(seek.value) || 0, false);
      if (follow) scrollToActive(true);
    };
    seek.addEventListener('change', commit);
    seek.addEventListener('pointerup', commit);

    pill.addEventListener('click', function () {
      follow = true;
      hidePill();
      scrollToActive(true);
    });

    // tap a segment to seek there
    var downX = 0, downY = 0, dragged = false;
    view.addEventListener('pointerdown', function (e) {
      downX = e.clientX; downY = e.clientY; dragged = false;
    });
    view.addEventListener('pointerup', function (e) {
      dragged = Math.abs(e.clientX - downX) > 8 || Math.abs(e.clientY - downY) > 8;
    });
    view.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;
      if (e.target.closest('a, button')) return;
      var el = e.target.closest('.seg');
      if (!el || !view.contains(el)) return;
      if (dragged) return;
      var sel = window.getSelection && window.getSelection();
      if (sel && String(sel).length > 2) return;

      var i = parseInt(el.dataset.i, 10);
      var seg = null;
      for (var k = 0; k < state.segs.length; k++) if (state.segs[k].i === i) { seg = state.segs[k]; break; }
      if (!seg || !isNum(seg.start)) return;
      var ch = chapterById(state.viewId);
      if (!ch || !ch.audio) return;
      if (state.audioId !== ch.id) ensureAudio(ch, false);
      follow = true;
      hidePill();
      seekTo(seg.start + 0.01, true);
    });

    audio.addEventListener('play', function () {
      player.classList.add('playing');
      btnPlay.setAttribute('aria-label', T.pause);
      btnPlay.title = T.pause;
      setPlaybackState('playing');
      startTick();
      if (state.audioId) {
        var ch = chapterById(state.audioId);
        if (ch) setMediaSession(ch);
      }
      if (!saveTimer) saveTimer = setInterval(saveProgress, 5000);
      var ec = view.querySelector('.endcard');
      if (ec) ec.remove();
      syncHighlight(true);
    });
    audio.addEventListener('pause', function () {
      player.classList.remove('playing');
      btnPlay.setAttribute('aria-label', T.play);
      btnPlay.title = T.play;
      setPlaybackState('paused');
      stopTick();
      saveProgress();
      if (saveTimer) { clearInterval(saveTimer); saveTimer = 0; }
    });
    audio.addEventListener('timeupdate', function () {
      if (!rafId) { syncHighlight(false); updateTimes(); }
    });
    audio.addEventListener('seeked', function () { syncHighlight(true); updateTimes(); saveProgress(); });
    audio.addEventListener('progress', updateBuffered);
    audio.addEventListener('loadedmetadata', function () {
      updateTimes();
      updateBuffered();
      updatePositionState();
      audio.playbackRate = speed;
    });
    audio.addEventListener('ratechange', updateSpeedChip);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('error', function () {
      if (!audio.getAttribute('src')) return;
      barTitle.textContent = T.audioError;
    });

    ['wheel', 'touchmove'].forEach(function (ev) {
      window.addEventListener(ev, userScrolled, { passive: true });
    });
    window.addEventListener('scroll', function () {
      if (performance.now() < programmaticUntil) return;
      if (followTarget !== null && Math.abs(window.scrollY - followTarget) < 90) return;
      userScrolled();
    }, { passive: true });

    window.addEventListener('resize', measurePlayer);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') saveProgress();
    });
    window.addEventListener('pagehide', saveProgress);

    document.addEventListener('keydown', onKey);
  }

  function onEnded() {
    saveProgress();
    if (state.audioId) {
      var d = isNum(audio.duration) ? audio.duration : null;
      if (d) lsSet('prog:' + state.audioId, { t: d, d: d, at: Date.now() });
    }
    var i = chapterIndex(state.audioId);
    var next = (i >= 0 && i < chapters.length - 1) ? chapters[i + 1] : null;
    if (autoNext && next) {
      if (next.audio) { goto(next.id, true); return; }
      goto(next.id, false);
      return;
    }
    showEndCard(next);
  }

  function showEndCard(next) {
    if (state.viewId !== state.audioId) return;
    var art = view.querySelector('.chapter');
    if (!art || art.querySelector('.endcard')) return;
    var div = document.createElement('div');
    div.className = 'endcard';
    div.innerHTML = esc(next ? T.endOfChapter : T.endOfBook) + ' ' +
      (next
        ? '<a href="#/ch/' + encodeURIComponent(next.id) + '">' +
            esc(T.nextKicker + ' · ' + (next.title || next.id)) + '</a>'
        : '<a href="#/">' + esc(T.backToContents) + '</a>');
    art.appendChild(div);
    measurePlayer();
  }

  function onKey(e) {
    var t = e.target;
    if (t && (t.isContentEditable ||
      /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    switch (e.key) {
      case ' ': case 'Spacebar':
        e.preventDefault(); togglePlay(); break;
      case 'ArrowLeft': e.preventDefault(); nudge(-15); break;
      case 'ArrowRight': e.preventDefault(); nudge(15); break;
      case 'ArrowUp': case ']': e.preventDefault(); cycleSpeed(1); break;
      case 'ArrowDown': case '[': e.preventDefault(); cycleSpeed(-1); break;
      case 'n': case 'N': gotoSibling(1); break;
      case 'p': case 'P': gotoSibling(-1); break;
      case 'f': case 'F':
        follow = !follow;
        if (follow) { hidePill(); scrollToActive(true); }
        else if (state.active >= 0 && state.audioId === state.viewId) showPill();
        break;
      case 'PageUp': case 'PageDown': case 'Home': case 'End':
        userScrolled(); break;
      default: break;
    }
  }

  /* ------------------------------------------------------------ go */

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
