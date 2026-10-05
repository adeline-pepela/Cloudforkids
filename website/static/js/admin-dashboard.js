/* Admin dashboard charts (Chart.js). Colours follow the light/dark theme. */
(function () {
  if (!window.Chart) return;
  var data = JSON.parse(document.getElementById('c4k-charts').textContent);
  var palette = ['#1CA7EC', '#2FBF71', '#FFC93C', '#FF6B6B', '#8B6BE8', '#FF9F43', '#0D7FBF', '#3DD68C'];
  var charts = [];

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function theme() {
    return { text: css('--body-quiet-color') || '#6B7280', grid: css('--hairline-color') || '#E5EDF3', card: css('--c4k-card') || '#fff' };
  }

  function short(label) { label = String(label); return label.length > 24 ? label.slice(0, 23) + '…' : label; }

  function make(id, config) {
    var el = document.getElementById(id);
    if (!el) return;
    charts.push(new Chart(el, config));
  }

  function build() {
    charts.forEach(function (c) { c.destroy(); });
    charts = [];
    var t = theme();
    Chart.defaults.font.family = '"Poppins", "Segoe UI", sans-serif';
    Chart.defaults.color = t.text;
    var scales = {
      x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
      y: { beginAtZero: true, grid: { color: t.grid }, ticks: { precision: 0 } }
    };
    var noLegend = { legend: { display: false } };

    make('ch-signups', {
      type: 'line',
      data: { labels: data.signups.labels, datasets: [{ data: data.signups.values, borderColor: '#1CA7EC', backgroundColor: 'rgba(28,167,236,.18)', fill: true, tension: .35, pointRadius: 2 }] },
      options: { maintainAspectRatio: false, plugins: noLegend, scales: scales }
    });
    make('ch-completions', {
      type: 'bar',
      data: { labels: data.completions.labels, datasets: [{ data: data.completions.values, backgroundColor: '#2FBF71', borderRadius: 6 }] },
      options: { maintainAspectRatio: false, plugins: noLegend, scales: scales }
    });
    ['roles', 'tiers'].forEach(function (k) {
      var d = data[k];
      make('ch-' + k, {
        type: 'doughnut',
        data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: palette, borderColor: t.card, borderWidth: 3 }] },
        options: { maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } } } }
      });
    });
    make('ch-enrollments', {
      type: 'bar',
      data: { labels: data.enrollments.labels, datasets: [{ data: data.enrollments.values, backgroundColor: palette, borderRadius: 6 }] },
      options: { indexAxis: 'y', maintainAspectRatio: false, plugins: noLegend, scales: { x: scales.y, y: { grid: { display: false }, ticks: { callback: function (v) { return short(this.getLabelForValue(v)); } } } } }
    });
    make('ch-top', {
      type: 'bar',
      data: { labels: data.top_lessons.labels, datasets: [{ data: data.top_lessons.values, backgroundColor: '#8B6BE8', borderRadius: 6 }] },
      options: { indexAxis: 'y', maintainAspectRatio: false, plugins: noLegend, scales: { x: scales.y, y: { grid: { display: false }, ticks: { callback: function (v) { return short(this.getLabelForValue(v)); } } } } }
    });
  }

  build();
  window.addEventListener('c4k-theme', build);
})();
