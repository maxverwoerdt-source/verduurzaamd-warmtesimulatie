(() => {
  const form = document.getElementById('simulationForm');
  const calculateButton = document.getElementById('calculateButton');
  const resetButton = document.getElementById('resetButton');
  const loading = document.getElementById('loading');
  const errorMessage = document.getElementById('errorMessage');
  const emptyState = document.getElementById('emptyState');
  const chartWrap = document.getElementById('chartWrap');
  const legend = document.getElementById('legend');
  const tableCard = document.getElementById('tableCard');
  const methodNote = document.getElementById('methodNote');
  const density = document.getElementById('density');
  const apartments = document.getElementById('apartments');
  const sourceToggle = document.getElementById('toggleSources');
  const sourceChecks = [...form.querySelectorAll('input[name="sources"]')];
  let chart = null;
  let latestResults = [];

  const colors = {
    capital: '#66724e',
    maintenance: '#a68b6a',
    energy: '#d1b46f',
    co2: '#929b91',
    grid: '#657b83'
  };
  const series = [
    ['capital', 'Kapitaallasten'],
    ['maintenance', 'Beheer en onderhoud'],
    ['energy', 'Energiekosten'],
    ['co2', 'CO₂-uitstootkosten'],
    ['grid', 'Netverzwaringskosten']
  ];
  const euro = value => new Intl.NumberFormat('nl-NL', {style:'currency',currency:'EUR',maximumFractionDigits:0}).format(value);
  const number = value => new Intl.NumberFormat('nl-NL', {maximumFractionDigits:0}).format(value);

  function syncRanges() {
    document.getElementById('densityValue').textContent = `${density.value}%`;
    document.getElementById('apartmentsValue').textContent = `${apartments.value}%`;
  }
  density.addEventListener('input', syncRanges);
  apartments.addEventListener('input', syncRanges);

  function fillDefaults() {
    for (const [key, value] of Object.entries(window.DEFAULTS)) {
      const input = form.elements.namedItem(key);
      if (input) input.value = value;
    }
    syncRanges();
  }
  resetButton.addEventListener('click', () => {
    fillDefaults();
    sourceChecks.forEach(input => input.checked = true);
    updateSourceToggle();
    if (latestResults.length) renderChart(getChartResults());
    errorMessage.hidden = true;
    if (!latestResults.length) {
      emptyState.querySelector("h3").textContent = "Bereken jouw scenario";
      emptyState.querySelector("p").textContent = "Vul links de uitgangspunten in en klik op ‘Bereken kosten’ om de warmtebronnen te vergelijken.";
    }
  });
  function updateSourceToggle() {
    const checked = sourceChecks.filter(input => input.checked).length;
    sourceToggle.textContent = checked === sourceChecks.length ? 'Alles uit' : 'Alles aan';
  }
  sourceChecks.forEach(input => input.addEventListener('change', () => {
    updateSourceToggle();
    if (latestResults.length) renderChart(getChartResults());
  }));
  sourceToggle.addEventListener('click', () => {
    const turnOn = sourceChecks.some(input => !input.checked);
    sourceChecks.forEach(input => input.checked = turnOn);
    updateSourceToggle();
    if (latestResults.length) renderChart(getChartResults());
  });
  updateSourceToggle();
  fillDefaults();

  function showLoading(active) {
    loading.hidden = !active;
    calculateButton.disabled = active;
    calculateButton.querySelector('span:first-child').textContent = active ? 'Bezig met berekenen…' : 'Bereken kosten';
  }

  function getChartResults() {
    const selected = new Set(sourceChecks.filter(input => input.checked).map(input => input.value));
    return latestResults.filter(result => selected.has(result.key));
  }

  function renderChart(results) {
    if (!results.length) {
      if (chart) { chart.destroy(); chart = null; }
      chartWrap.hidden = true;
      legend.hidden = true;
      emptyState.hidden = false;
      emptyState.querySelector("h3").textContent = "Geen warmtebronnen geselecteerd";
      emptyState.querySelector("p").textContent = "Zet één of meer warmtebronnen aan om deze in de grafiek te tonen.";
      return;
    }
    emptyState.hidden = true;
    chartWrap.hidden = false;
    legend.hidden = false;
    const ctx = document.getElementById('costChart');
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: results.map(r => r.label),
        datasets: series.map(([key, label]) => ({
          label,
          data: results.map(r => r[key]),
          backgroundColor: colors[key],
          borderWidth: 0,
          borderRadius: 2,
          borderSkipped: false,
          stack: 'annual-costs',
          maxBarThickness: 46
        }))
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {
          legend: {display: false},
          tooltip: {
            backgroundColor: '#30382e',
            padding: 12,
            titleFont: {family: 'DM Sans', weight: '600'},
            bodyFont: {family: 'DM Sans'},
            callbacks: {label: item => `${item.dataset.label}: ${euro(item.raw)}`, footer: items => `Totaal: ${euro(items.reduce((sum, item) => sum + item.raw, 0))}`}
          }
        },
        scales: {
          x: {stacked: true, grid: {display: false}, ticks: {color: '#747c70', maxRotation: 48, minRotation: 0, font: {family:'DM Sans',size:10}}},
          y: {stacked: true, beginAtZero: true, grid: {color: '#edf0ea'}, border: {display:false}, ticks: {color:'#8a9186', font:{family:'DM Sans',size:10}, callback: value => euro(value)}}
        }
      }
    });
    legend.innerHTML = series.map(([key,label]) => `<span class="legend-item"><i class="legend-swatch" style="background:${colors[key]}"></i>${label}</span>`).join('');
  }

  function renderTable(results) {
    const tbody = document.querySelector('#resultsTable tbody');
    tbody.innerHTML = results.map(row => `
      <tr>
        <td title="${row.detail || ''}">${row.label}</td>
        <td>${euro(row.investment_total)}</td>
        <td>${number(row.electric_power_total)} kW</td>
        <td>${euro(row.capital)}</td>
        <td>${euro(row.maintenance)}</td>
        <td>${euro(row.energy)}</td>
        <td>${euro(row.co2)}</td>
        <td>${euro(row.grid)}</td>
        <td class="total-col">${euro(row.total)}</td>
      </tr>`).join('');
    tableCard.hidden = false;
    methodNote.hidden = false;
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    errorMessage.hidden = true;
    showLoading(true);
    const payload = {};
    for (const [key, value] of new FormData(form).entries()) {
      if (key !== 'sources') payload[key] = value;
    }
    payload.sources = sourceChecks.filter(input => input.checked).map(input => input.value);
    try {
      const response = await fetch(`/${encodeURIComponent(window.APP_SECRET)}/api/calculate`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'De berekening is niet gelukt.');
      latestResults = data.results;
      renderChart(getChartResults());
      renderTable(latestResults);
    } catch (error) {
      errorMessage.textContent = error.message || 'Er is iets misgegaan bij het berekenen.';
      errorMessage.hidden = false;
    } finally {
      showLoading(false);
    }
  });

  document.getElementById('downloadCsv').addEventListener('click', () => {
    if (!latestResults.length) return;
    const headers = ['Warmtebron','Investering totaal (€)','Elektrisch vermogen totaal (kW)','Kapitaallasten (€ / woning / jaar)','Beheer en onderhoud (€ / woning / jaar)','Energiekosten (€ / woning / jaar)','CO2-uitstootkosten (€ / woning / jaar)','Netverzwaringskosten (€ / woning / jaar)','Totaal (€ / woning / jaar)'];
    const rows = latestResults.map(r => [r.label,r.investment_total,r.electric_power_total,r.capital,r.maintenance,r.energy,r.co2,r.grid,r.total]);
    const csv = [headers, ...rows].map(row => row.map(v => `"${String(v).replaceAll('"','""')}"`).join(';')).join('\r\n');
    const blob = new Blob(['\ufeff' + csv], {type:'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'warmtesimulatie-resultaten.csv'; a.click(); URL.revokeObjectURL(url);
  });
})();
