(function () {
  var root = document.documentElement;
  var TKEY = 'cp-theme';
  var SKEY = 'cp-stars-v1';
  var TTL = 3600 * 1000;
  var ORDER = ['auto', 'light', 'dark'];
  var LABELS = { auto: '主题：跟随系统', light: '主题：浅色', dark: '主题：深色' };

  function currentTheme() {
    return root.getAttribute('data-theme') || 'auto';
  }

  function setTheme(t) {
    root.setAttribute('data-theme', t);
    try { localStorage.setItem(TKEY, t); } catch (e) {}
  }

  function formatStars(n) {
    return n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n);
  }

  function paintStars(map) {
    var nodes = document.querySelectorAll('[data-repo]');
    for (var i = 0; i < nodes.length; i++) {
      var v = map[nodes[i].getAttribute('data-repo')];
      if (typeof v === 'number') nodes[i].textContent = formatStars(v);
    }
  }

  function loadStars() {
    var nodes = document.querySelectorAll('[data-repo]');
    if (!nodes.length) return;

    var cached = null;
    try { cached = JSON.parse(localStorage.getItem(SKEY) || 'null'); } catch (e) {}
    if (cached && cached.d && Date.now() - cached.t < TTL) {
      paintStars(cached.d);
      return;
    }

    var repos = [];
    for (var i = 0; i < nodes.length; i++) {
      var r = nodes[i].getAttribute('data-repo');
      if (repos.indexOf(r) === -1) repos.push(r);
    }

    var map = {};
    var pending = repos.map(function (repo) {
      return fetch('https://api.github.com/repos/' + repo, {
        headers: { Accept: 'application/vnd.github+json' }
      })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (d) { if (d && typeof d.stargazers_count === 'number') map[repo] = d.stargazers_count; })
        .catch(function () {});
    });

    Promise.all(pending).then(function () {
      if (Object.keys(map).length === 0) return;
      paintStars(map);
      try { localStorage.setItem(SKEY, JSON.stringify({ t: Date.now(), d: map })); } catch (e) {}
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      var label = function () {
        var txt = LABELS[currentTheme()] || LABELS.auto;
        btn.setAttribute('title', txt);
        btn.setAttribute('aria-label', txt);
      };
      label();
      btn.addEventListener('click', function () {
        var t = currentTheme();
        setTheme(ORDER[(ORDER.indexOf(t) + 1) % ORDER.length]);
        label();
      });
    }
    loadStars();
  });
})();
