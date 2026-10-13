'use strict';

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  availableMonths: [],
  geojson: null,
  geojsonLayer: null,
  pricesByMonth: {},   // cache: month_str -> payload
  currentMonth: null,
};

// ── Map init ───────────────────────────────────────────────────────────────
const map = L.map('map', {
  center: [38.5, -96],
  zoom: 4,
  zoomSnap: 0.5,
  minZoom: 3,
  maxZoom: 8,
  attributionControl: true,
});

// OpenStreetMap tiles — no API key, no domain restrictions.
// CSS dark filter applied in style.css (.leaflet-tile-pane) to match the theme.
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

// ── Color scale ────────────────────────────────────────────────────────────
// Fixed absolute thresholds ($/gal) - consistent across all months.
const BREAKS = [2.50, 3.00, 3.50, 4.00, 4.50, 5.00];
const COLORS = ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026', '#67000d'];

function priceToColor(price) {
  if (price == null) return '#1a2419'; // forest-dark "no data"
  for (let i = BREAKS.length - 1; i >= 0; i--) {
    if (price >= BREAKS[i]) return COLORS[i];
  }
  return COLORS[0];
}

// ── GeoJSON style helpers ──────────────────────────────────────────────────
function featureStyle(priceMap) {
  return function (feature) {
    const name = feature.properties.name.toLowerCase();
    const price = priceMap[name];
    return {
      fillColor: priceToColor(price),
      fillOpacity: 0.84,
      color: 'rgba(139,174,102,0.22)',
      weight: 0.7,
      opacity: 1,
    };
  };
}

function bindTooltip(layer, priceMap) {
  const name    = layer.feature.properties.name;
  const price   = priceMap[name.toLowerCase()];
  const priceText = price != null
    ? `<strong>$${price.toFixed(3)}</strong> / gal`
    : '<em style="color:#8b949e">No data</em>';
  layer.bindTooltip(
    `<span style="font-weight:600">${name}</span><br>${priceText}`,
    { sticky: true, opacity: 1 }
  );
}

// ── Build price lookup from API payload ───────────────────────────────────
// EIA returns area_name in ALL CAPS; GeoJSON uses Title Case — normalise to lowercase for matching.
function buildPriceMap(payload) {
  const map = {};
  for (const s of payload.states) {
    map[s.area_name.toLowerCase()] = s.avg_price;
  }
  return map;
}

// ── Render choropleth for a loaded payload ─────────────────────────────────
function renderMonth(payload) {
  const priceMap = buildPriceMap(payload);

  if (state.geojsonLayer) {
    state.geojsonLayer.setStyle(featureStyle(priceMap));
    state.geojsonLayer.eachLayer(layer => {
      layer.unbindTooltip();
      bindTooltip(layer, priceMap);
    });
  } else {
    state.geojsonLayer = L.geoJSON(state.geojson, {
      style: featureStyle(priceMap),
      onEachFeature(feature, layer) {
        bindTooltip(layer, priceMap);
        layer.on({
          mouseover(e) {
            e.target.setStyle({ weight: 1.8, color: '#EBD5AB', fillOpacity: 0.95 });
            const name  = e.target.feature.properties.name;
            const price = priceMap[name.toLowerCase()];
            const card  = document.getElementById('hover-state');
            card.style.opacity = '1';
            document.getElementById('hover-value').textContent =
              price != null ? `$${price.toFixed(3)}` : 'No data';
            document.getElementById('hover-name').textContent = name;
          },
          mouseout(e) {
            state.geojsonLayer.resetStyle(e.target);
            bindTooltip(e.target, priceMap);
            document.getElementById('hover-state').style.opacity = '0.45';
            document.getElementById('hover-value').textContent = '—';
            document.getElementById('hover-name').textContent = '—';
          },
        });
      },
    }).addTo(map);
  }

  updateStats(payload);
}

// ── Stats panel ────────────────────────────────────────────────────────────
function updateStats(payload) {
  const s = payload.stats;

  setCard('national-avg',
    s.national_avg != null ? `$${s.national_avg.toFixed(3)}` : '-',
    'National Avg ($/gal)', 'amber'
  );
  setCard('cheapest-state',
    s.state_min != null ? `$${s.state_min.toFixed(3)}` : '-',
    `Cheapest · ${s.state_min_name ?? ''}`, 'green'
  );
  setCard('priciest-state',
    s.state_max != null ? `$${s.state_max.toFixed(3)}` : '-',
    `Priciest · ${s.state_max_name ?? ''}`, 'red'
  );
}

function setCard(id, value, sub, colorClass) {
  const el = document.getElementById(id);
  if (!el) return;
  el.querySelector('.value').textContent = value;
  el.querySelector('.value').className = `value ${colorClass}`;
  el.querySelector('.sub').textContent = sub;
}

// ── Month loading (with in-memory cache) ───────────────────────────────────
async function loadMonth(monthStr) {
  showLoading(true);
  try {
    if (!state.pricesByMonth[monthStr]) {
      const resp = await fetch(`data/prices_${monthStr}.json`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      state.pricesByMonth[monthStr] = await resp.json();
    }
    state.currentMonth = monthStr;
    renderMonth(state.pricesByMonth[monthStr]);
    document.getElementById('month-display').textContent = formatMonth(monthStr);
  } catch (err) {
    console.error('Failed to load month', monthStr, err);
  } finally {
    showLoading(false);
  }
}

function formatMonth(str) {
  const [y, m] = str.split('-');
  const d = new Date(+y, +m - 1, 1);
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

// ── Autoplay ───────────────────────────────────────────────────────────────
const PLAY_SPEED_MS = 900;
let playTimer = null;

function stopPlay() {
  clearInterval(playTimer);
  playTimer = null;
  const btn = document.getElementById('play-btn');
  btn.classList.remove('playing');
  btn.innerHTML = '&#9654;';
  btn.title = 'Play through all months';
}

function startPlay() {
  const slider = document.getElementById('month-slider');
  const btn    = document.getElementById('play-btn');

  // If already at the end, restart from the beginning
  if (+slider.value >= +slider.max) {
    slider.value = 0;
    syncSliderFill(slider);
  }

  btn.classList.add('playing');
  btn.innerHTML = '&#9646;&#9646;';
  btn.title = 'Pause';

  playTimer = setInterval(() => {
    const next = +slider.value + 1;
    if (next > +slider.max) {
      stopPlay();
      return;
    }
    slider.value = next;
    syncSliderFill(slider);
    const month = state.availableMonths[next];
    document.getElementById('month-display').textContent = formatMonth(month);
    loadMonth(month);
  }, PLAY_SPEED_MS);
}

function togglePlay() {
  if (playTimer) { stopPlay(); } else { startPlay(); }
}

// Exposed to the onclick in HTML
window.togglePlay = togglePlay;

// ── Slider wiring ──────────────────────────────────────────────────────────
function syncSliderFill(slider) {
  const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
  slider.style.setProperty('--fill', `${pct}%`);
}

function initSlider(months) {
  const slider = document.getElementById('month-slider');
  slider.min = 0;
  slider.max = months.length - 1;
  slider.value = months.length - 1;

  document.querySelector('.slider-labels span:first-child').textContent =
    formatMonth(months[0]);
  document.querySelector('.slider-labels span:last-child').textContent =
    formatMonth(months[months.length - 1]);

  syncSliderFill(slider);

  let debounce;
  slider.addEventListener('input', () => {
    if (playTimer) stopPlay();   // manual drag cancels autoplay
    clearTimeout(debounce);
    syncSliderFill(slider);
    const month = months[+slider.value];
    document.getElementById('month-display').textContent = formatMonth(month);
    debounce = setTimeout(() => loadMonth(month), 120);
  });
}

// ── Loading overlay ────────────────────────────────────────────────────────
function showLoading(visible) {
  document.getElementById('loading').classList.toggle('hidden', !visible);
}

// ── Boot ───────────────────────────────────────────────────────────────────
async function init() {
  showLoading(true);
  try {
    const [manifestResp, geojsonResp] = await Promise.all([
      fetch('data/manifest.json'),
      fetch('data/us-states.geojson'),
    ]);

    if (!manifestResp.ok) throw new Error('manifest.json not found - run the pipeline first');
    if (!geojsonResp.ok)  throw new Error('us-states.geojson not found - run the pipeline first');

    const manifest = await manifestResp.json();
    state.geojson = await geojsonResp.json();
    state.availableMonths = manifest.available_months;

    document.getElementById('last-updated').textContent =
      `Last updated: ${new Date(manifest.last_updated).toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
      })}`;

    initSlider(state.availableMonths);
    await loadMonth(manifest.latest_month);
  } catch (err) {
    showLoading(false);
    document.getElementById('loading').textContent = `Error: ${err.message}`;
    document.getElementById('loading').classList.remove('hidden');
    console.error(err);
  }
}

init();
