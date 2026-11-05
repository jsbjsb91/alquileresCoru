/**
 * Alquileres Coruña — Frontend Application Logic
 * Integración con FastAPI, Leaflet.js y Machine Learning Valuation Pipeline
 */

// Global State
const state = {
  apiBaseUrl: (window.location.protocol === 'file:') ? 'http://127.0.0.1:8000' : (window.location.origin || ''),
  isOnline: false,
  allProperties: [],
  filteredProperties: [],
  marketSummary: null,
  neighborhoodStats: [],
  map: null,
  markerLayer: null,
  markersById: {},
  filters: {
    is_real: true, // Default: Real listings only
    verdict: '',
    neighborhood_id: '',
    max_price: 3000,
    rooms: null,
    has_elevator: false,
    has_parking: false,
    furnished: false,
    sort_by: 'opportunity',
  },
  sim: {
    rooms: 2,
    baths: 1,
  }
};

// Default fallback photo for listings without images
const FALLBACK_PHOTO = 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=600&q=80';

// Initialize App
document.addEventListener('DOMContentLoaded', async () => {
  initMap();
  setupFilterListeners();
  setupSimulator();
  await loadInitialData();
  applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
  if (window.lucide) {
    lucide.createIcons();
  }
});

/**
 * Initialize Leaflet Map
 */
function initMap() {
  // Center in A Coruña city center
  const corunaCoords = [43.3380, -8.3750];
  state.map = L.map('coruna-map', {
    center: corunaCoords,
    zoom: 12,
    scrollWheelZoom: true,
  });

  // CartoDB Voyager tiles for crisp aesthetic
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(state.map);

  state.markerLayer = L.layerGroup().addTo(state.map);

  // Recenter button
  const recenterBtn = document.getElementById('btn-recenter-map');
  if (recenterBtn) {
    recenterBtn.addEventListener('click', () => {
      state.map.flyTo(corunaCoords, 12, { duration: 1.2 });
    });
  }
}

/**
 * Load Initial Data (API first, graceful fallback to local JSON)
 */
async function loadInitialData() {
  const statusBadge = document.getElementById('api-status-badge');
  const statusText = document.getElementById('api-status-text');

  try {
    // 1. Health check & Fetch properties from API
    const res = await fetch(`${state.apiBaseUrl}/api/v1/properties?page_size=1000`, { cache: 'no-cache' });
    if (!res.ok) throw new Error('API properties returned error status');
    
    const propData = await res.json();
    state.allProperties = propData.items || [];
    state.isOnline = true;

    // Fetch market summary
    try {
      const sumRes = await fetch(`${state.apiBaseUrl}/api/v1/stats/market-summary`);
      if (sumRes.ok) state.marketSummary = await sumRes.json();

      const nRes = await fetch(`${state.apiBaseUrl}/api/v1/stats/neighborhoods`);
      if (nRes.ok) state.neighborhoodStats = await nRes.json();
    } catch (e) {
      console.warn('Stats endpoints fallback:', e);
    }

    if (statusBadge && statusText) {
      statusBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span class="text-emerald-300 font-semibold">API Online (${state.allProperties.length} inmuebles)</span>`;
    }
  } catch (err) {
    console.warn('API unreachable, activating local fallback dataset:', err);
    state.isOnline = false;

    if (statusBadge && statusText) {
      statusBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400"></span><span class="text-amber-300 font-semibold">Modo Local Fallback</span>`;
    }

    // Load from local fallback files
    try {
      const localProps = await fetch(`${state.apiBaseUrl}/data/properties_fallback.json`);
      state.allProperties = await localProps.json();

      const localSum = await fetch(`${state.apiBaseUrl}/data/market_summary.json`);
      state.marketSummary = await localSum.json();
    } catch (localErr) {
      console.error('Failed to load local fallback data:', localErr);
    }
  }

  updateKpis();
  renderNeighborhoodRanking();
}

/**
 * Update Header KPIs
 */
function updateKpis() {
  const kpiAvgPrice = document.getElementById('kpi-avg-price');
  const kpiMedianPrice = document.getElementById('kpi-median-price');
  const kpiAvgSqm = document.getElementById('kpi-avg-sqm');
  const kpiRealCount = document.getElementById('kpi-real-count');
  const kpiOppCount = document.getElementById('kpi-opportunities-count');

  const realListings = state.allProperties.filter(p => p.is_real);
  const opportunities = realListings.filter(p => (p.market_verdict || '').includes('Oportunidad'));

  if (state.marketSummary) {
    if (kpiAvgPrice) kpiAvgPrice.innerText = `${Math.round(state.marketSummary.avg_price)} €`;
    if (kpiMedianPrice) kpiMedianPrice.innerText = `Mediana: ${Math.round(state.marketSummary.median_price)} €/mes`;
    if (kpiAvgSqm) kpiAvgSqm.innerText = `${state.marketSummary.avg_price_sqm.toFixed(1)} €/m²`;
  } else if (state.allProperties.length > 0) {
    const avg = state.allProperties.reduce((acc, p) => acc + p.price_month, 0) / state.allProperties.length;
    const avgSqm = state.allProperties.reduce((acc, p) => acc + p.price_sqm, 0) / state.allProperties.length;
    if (kpiAvgPrice) kpiAvgPrice.innerText = `${Math.round(avg)} €`;
    if (kpiAvgSqm) kpiAvgSqm.innerText = `${avgSqm.toFixed(1)} €/m²`;
  }

  if (kpiRealCount) kpiRealCount.innerText = `${realListings.length} Verificados`;
  if (kpiOppCount) kpiOppCount.innerText = `${opportunities.length} Chollos`;
}

/**
 * Setup Event Listeners for Filters
 */
function setupFilterListeners() {
  // Real only toggle
  const realToggle = document.getElementById('filter-real-only');
  if (realToggle) {
    realToggle.addEventListener('change', (e) => {
      state.filters.is_real = e.target.checked;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  // Neighborhood filter
  const nSelect = document.getElementById('filter-neighborhood');
  if (nSelect) {
    nSelect.addEventListener('change', (e) => {
      state.filters.neighborhood_id = e.target.value;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  // ML Verdict filter
  const vSelect = document.getElementById('filter-verdict');
  if (vSelect) {
    vSelect.addEventListener('change', (e) => {
      state.filters.verdict = e.target.value;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  // Max price slider
  const priceSlider = document.getElementById('filter-max-price');
  const priceLabel = document.getElementById('price-val-label');
  if (priceSlider) {
    priceSlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value);
      state.filters.max_price = val;
      if (priceLabel) {
        priceLabel.innerText = val >= 3000 ? 'Sin límite' : `Hasta ${val} €/mes`;
      }
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  // Rooms buttons
  const roomBtns = document.querySelectorAll('.room-btn');
  roomBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      roomBtns.forEach(b => {
        b.classList.remove('bg-emerald-600', 'text-white', 'active');
        b.classList.add('bg-slate-50', 'text-slate-700');
      });
      btn.classList.remove('bg-slate-50', 'text-slate-700');
      btn.classList.add('bg-emerald-600', 'text-white', 'active');

      const r = btn.getAttribute('data-rooms');
      state.filters.rooms = r ? parseInt(r) : null;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  });

  // Amenities
  const elElevator = document.getElementById('filter-elevator');
  if (elElevator) {
    elElevator.addEventListener('change', (e) => {
      state.filters.has_elevator = e.target.checked;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  const elParking = document.getElementById('filter-parking');
  if (elParking) {
    elParking.addEventListener('change', (e) => {
      state.filters.has_parking = e.target.checked;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  const elFurnished = document.getElementById('filter-furnished');
  if (elFurnished) {
    elFurnished.addEventListener('change', (e) => {
      state.filters.furnished = e.target.checked;
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  // Sorting
  const sortSelect = document.getElementById('filter-sort');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      state.filters.sort_by = e.target.value;
      const label = document.getElementById('current-sort-label');
      if (label) {
        const textMap = {
          opportunity: 'Mayor chollo (Descuento IA)',
          price_asc: 'Precio menor a mayor',
          price_desc: 'Precio mayor a menor',
          price_sqm_asc: '€/m² más económico',
          sqm_desc: 'Mayor superficie',
        };
        label.innerText = textMap[e.target.value] || e.target.value;
      }
      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }

  // Reset button
  const resetBtn = document.getElementById('btn-reset-filters');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      state.filters = {
        is_real: true,
        verdict: '',
        neighborhood_id: '',
        max_price: 3000,
        rooms: null,
        has_elevator: false,
        has_parking: false,
        furnished: false,
        sort_by: 'opportunity',
      };
      if (realToggle) realToggle.checked = true;
      if (nSelect) nSelect.value = '';
      if (vSelect) vSelect.value = '';
      if (priceSlider) priceSlider.value = 3000;
      if (priceLabel) priceLabel.innerText = 'Sin límite';
      if (elElevator) elElevator.checked = false;
      if (elParking) elParking.checked = false;
      if (elFurnished) elFurnished.checked = false;
      if (sortSelect) sortSelect.value = 'opportunity';

      roomBtns.forEach((b, idx) => {
        if (idx === 0) {
          b.classList.add('bg-emerald-600', 'text-white', 'active');
          b.classList.remove('bg-slate-50', 'text-slate-700');
        } else {
          b.classList.remove('bg-emerald-600', 'text-white', 'active');
          b.classList.add('bg-slate-50', 'text-slate-700');
        }
      });

      applyFiltersAndRender();
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 300);
  }
    });
  }
}

/**
 * Filter and Sort Properties
 */
function applyFiltersAndRender() {
  let list = [...state.allProperties];

  // 1. Real only
  if (state.filters.is_real) {
    list = list.filter(p => p.is_real === true);
  }

  // 2. Neighborhood
  if (state.filters.neighborhood_id) {
    list = list.filter(p => p.neighborhood_id === state.filters.neighborhood_id);
  }

  // 3. Verdict
  if (state.filters.verdict) {
    list = list.filter(p => (p.market_verdict || '').includes(state.filters.verdict));
  }

  // 4. Max price
  if (state.filters.max_price < 3000) {
    list = list.filter(p => p.price_month <= state.filters.max_price);
  }

  // 5. Rooms
  if (state.filters.rooms) {
    list = list.filter(p => p.rooms >= state.filters.rooms);
  }

  // 6. Amenities
  if (state.filters.has_elevator) {
    list = list.filter(p => p.has_elevator === true);
  }
  if (state.filters.has_parking) {
    list = list.filter(p => p.has_parking === true);
  }
  if (state.filters.furnished) {
    list = list.filter(p => p.furnished === true);
  }

  // 7. Sort
  list.sort((a, b) => {
    switch (state.filters.sort_by) {
      case 'opportunity':
        return (a.deviation_pct ?? 0) - (b.deviation_pct ?? 0);
      case 'price_asc':
        return a.price_month - b.price_month;
      case 'price_desc':
        return b.price_month - a.price_month;
      case 'price_sqm_asc':
        return a.price_sqm - b.price_sqm;
      case 'sqm_desc':
        return b.sqm - a.sqm;
      default:
        return 0;
    }
  });

  state.filteredProperties = list;

  // Update counter badge
  const countBadge = document.getElementById('results-count-badge');
  if (countBadge) {
    countBadge.innerText = `${list.length} ${list.length === 1 ? 'vivienda' : 'viviendas'}`;
  }

  // Render Map Markers and Cards Grid
  renderMapMarkers(list);
  renderPropertyCards(list);
}

/**
 * Render Leaflet Markers
 */
function renderMapMarkers(properties) {
  if (!state.markerLayer) return;
  state.markerLayer.clearLayers();
  state.markersById = {};

  const bounds = [];

  properties.forEach(p => {
    if (!p.lat || !p.lon) return;

    // Verdict color & styling
    let markerClass = 'marker-fair';
    let iconSymbol = '⚖️';
    let verdictLabel = 'En Precio de mercado';
    let badgeClass = 'bg-blue-100 text-blue-800 border-blue-200';

    if ((p.market_verdict || '').includes('Oportunidad')) {
      markerClass = 'marker-opportunity';
      iconSymbol = '⭐';
      const saving = p.deviation_pct ? Math.abs(Math.round(p.deviation_pct)) : 20;
      verdictLabel = `🌟 Oportunidad -${saving}%`;
      badgeClass = 'bg-emerald-100 text-emerald-800 border-emerald-300';
    } else if ((p.market_verdict || '').includes('Sobreprecio')) {
      markerClass = 'marker-overpriced';
      iconSymbol = '📈';
      const over = p.deviation_pct ? Math.round(p.deviation_pct) : 15;
      verdictLabel = `⚠️ Sobreprecio +${over}%`;
      badgeClass = 'bg-amber-100 text-amber-800 border-amber-300';
    }

    const customIcon = L.divIcon({
      className: 'custom-div-icon',
      html: `
        <div class="marker-pin ${markerClass}" title="${p.title} - ${p.price_month}€">
          <span>${iconSymbol}</span>
        </div>
      `,
      iconSize: [38, 38],
      iconAnchor: [19, 38],
      popupAnchor: [0, -38],
    });

    const marker = L.marker([p.lat, p.lon], { icon: customIcon });

    // Popup Content
    const photo = p.photo_url || FALLBACK_PHOTO;
    const portalUrl = p.url || `https://www.google.com/search?q=alquiler+pisos+coruna+${encodeURIComponent(p.title)}`;

    const popupHtml = `
      <div class="w-72 overflow-hidden rounded-2xl bg-white font-sans text-slate-900">
        <div class="relative h-40 w-full overflow-hidden bg-slate-900">
          <img src="${photo}" alt="${p.title}" class="h-full w-full object-cover transition-transform duration-300 hover:scale-105" onerror="this.src='${FALLBACK_PHOTO}'" />
          <div class="absolute top-2.5 left-2.5">
            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase shadow bg-slate-900/90 text-white backdrop-blur border border-white/20">
              ${p.is_real ? '✓ 100% REAL' : 'Simulado'}
            </span>
          </div>
          <div class="absolute top-2.5 right-2.5">
            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border shadow ${badgeClass}">
              ${verdictLabel}
            </span>
          </div>
        </div>

        <div class="p-3.5">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">${p.neighborhood}</div>
          <h4 class="text-sm font-bold text-slate-900 line-clamp-1 mt-0.5">${p.title}</h4>

          <div class="flex items-baseline justify-between mt-2.5 pb-2.5 border-b border-slate-100">
            <div>
              <span class="text-xl font-extrabold text-slate-900">${p.price_month} €</span>
              <span class="text-xs text-slate-500">/mes</span>
            </div>
            <span class="text-xs font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">
              ${p.price_sqm.toFixed(1)} €/m²
            </span>
          </div>

          <div class="grid grid-cols-3 gap-1.5 py-2 text-center text-xs text-slate-600">
            <div class="bg-slate-50 py-1 rounded"><strong>${p.sqm}</strong> m²</div>
            <div class="bg-slate-50 py-1 rounded"><strong>${p.rooms}</strong> hab</div>
            <div class="bg-slate-50 py-1 rounded">${p.has_elevator ? 'Ascensor' : 'Sin asc.'}</div>
          </div>

          ${p.predicted_price ? `
            <div class="text-[11px] bg-emerald-50 text-emerald-900 px-2.5 py-1.5 rounded-lg border border-emerald-100 mt-1 flex justify-between items-center">
              <span>Tasación IA: <strong>${Math.round(p.predicted_price)} €/mes</strong></span>
              ${p.deviation_pct ? `<span class="font-bold ${p.deviation_pct < 0 ? 'text-emerald-700' : 'text-amber-700'}">${p.deviation_pct < 0 ? 'Ahorro ' + Math.abs(Math.round(p.deviation_pct)) + '%' : '+' + Math.round(p.deviation_pct) + '%'}</span>` : ''}
            </div>
          ` : ''}

          <div class="mt-3">
            <a href="${portalUrl}" target="_blank" rel="noopener noreferrer" class="block w-full text-center py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-sm transition-colors">
              Ver Anuncio Original en Portal ↗
            </a>
          </div>
        </div>
      </div>
    `;

    marker.bindPopup(popupHtml, { maxWidth: 300, minWidth: 280, closeButton: false });
    state.markerLayer.addLayer(marker);
    state.markersById[p.id] = marker;
    bounds.push([p.lat, p.lon]);
  });

  // Fit bounds if we have results
  if (bounds.length > 0 && properties.length < 100) {
    try {
      state.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
    } catch (e) {
      // Ignore if bounds error
    }
  }
}

/**
 * Render Property Cards Grid
 */
function renderPropertyCards(properties) {
  const grid = document.getElementById('properties-grid');
  const emptyState = document.getElementById('empty-state');
  if (!grid) return;

  if (properties.length === 0) {
    grid.innerHTML = '';
    if (emptyState) emptyState.classList.remove('hidden');
    return;
  }

  if (emptyState) emptyState.classList.add('hidden');

  const cardsHtml = properties.map(p => {
    const photo = p.photo_url || FALLBACK_PHOTO;
    const portalUrl = p.url || `https://www.google.com/search?q=alquiler+pisos+coruna+${encodeURIComponent(p.title)}`;

    let verdictBadge = '';
    let verdictStyle = 'bg-blue-50 text-blue-700 border-blue-200';
    let savingsHtml = '';

    if ((p.market_verdict || '').includes('Oportunidad')) {
      const saving = p.deviation_pct ? Math.abs(Math.round(p.deviation_pct)) : 20;
      verdictBadge = `🌟 Chollo -${saving}%`;
      verdictStyle = 'bg-emerald-500 text-white shadow-emerald-500/25';
      savingsHtml = `
        <div class="flex items-center justify-between text-xs font-semibold text-emerald-800 bg-emerald-50 px-3 py-1.5 rounded-xl border border-emerald-100">
          <span class="flex items-center gap-1">
            <i data-lucide="trending-down" class="w-3.5 h-3.5 text-emerald-600"></i>
            Tasación IA: ${Math.round(p.predicted_price || (p.price_month * 1.25))} €/mes
          </span>
          <span class="font-extrabold text-emerald-700">Ahorras ~${saving}%</span>
        </div>
      `;
    } else if ((p.market_verdict || '').includes('Sobreprecio')) {
      const over = p.deviation_pct ? Math.round(p.deviation_pct) : 15;
      verdictBadge = `📈 Sobreprecio +${over}%`;
      verdictStyle = 'bg-amber-500 text-white shadow-amber-500/25';
      savingsHtml = `
        <div class="flex items-center justify-between text-xs font-semibold text-amber-800 bg-amber-50 px-3 py-1.5 rounded-xl border border-amber-100">
          <span class="flex items-center gap-1">
            <i data-lucide="trending-up" class="w-3.5 h-3.5 text-amber-600"></i>
            Tasación IA: ${Math.round(p.predicted_price || (p.price_month * 0.85))} €/mes
          </span>
          <span class="font-bold text-amber-700">+${over}% s/mercado</span>
        </div>
      `;
    } else {
      verdictBadge = `⚖️ En Precio`;
      verdictStyle = 'bg-blue-600 text-white shadow-blue-500/25';
      savingsHtml = `
        <div class="flex items-center justify-between text-xs font-semibold text-slate-700 bg-slate-100 px-3 py-1.5 rounded-xl">
          <span>Tasación IA: ${Math.round(p.predicted_price || p.price_month)} €/mes</span>
          <span class="text-slate-500">Precio equilibrado</span>
        </div>
      `;
    }

    return `
      <div class="property-card group bg-white rounded-3xl overflow-hidden shadow-sm hover:shadow-xl border border-slate-200/90 transition-all duration-300 flex flex-col justify-between">
        
        <!-- Image & Floating Badges -->
        <div class="relative h-56 w-full overflow-hidden bg-slate-900 cursor-pointer" onclick="focusPropertyOnMap('${p.id}')">
          <img 
            src="${photo}" 
            alt="${p.title}" 
            class="property-img w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" 
            onerror="this.src='${FALLBACK_PHOTO}'"
            loading="lazy"
          />
          <div class="absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-black/20"></div>

          <!-- Top Badges -->
          <div class="absolute top-3 left-3 flex flex-wrap gap-2">
            ${p.is_real ? `
              <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md">
                <i data-lucide="shield-check" class="w-3.5 h-3.5"></i> 100% REAL
              </span>
            ` : `
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-900/80 text-slate-300 backdrop-blur">
                Simulado
              </span>
            `}
          </div>

          <div class="absolute top-3 right-3">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-black shadow-md ${verdictStyle}">
              ${verdictBadge}
            </span>
          </div>

          <!-- Price overlay at bottom of image -->
          <div class="absolute bottom-3 left-3 right-3 flex items-baseline justify-between text-white">
            <div class="flex items-baseline gap-1">
              <span class="text-2xl sm:text-3xl font-black drop-shadow">${p.price_month} €</span>
              <span class="text-xs font-medium text-slate-200 drop-shadow">/mes</span>
            </div>
            <span class="text-xs font-bold bg-white/20 backdrop-blur px-2.5 py-1 rounded-lg text-white border border-white/20">
              ${p.price_sqm.toFixed(1)} €/m²
            </span>
          </div>
        </div>

        <!-- Card Body -->
        <div class="p-5 flex-1 flex flex-col justify-between">
          <div>
            <!-- Neighborhood -->
            <div class="flex items-center gap-1.5 text-xs font-bold text-emerald-700 uppercase tracking-wider mb-1">
              <i data-lucide="map-pin" class="w-3.5 h-3.5 text-emerald-600"></i>
              <span>${p.neighborhood}</span>
            </div>

            <!-- Title -->
            <h4 class="text-base font-bold text-slate-900 line-clamp-1 mb-3 group-hover:text-emerald-700 transition-colors" title="${p.title}">
              ${p.title}
            </h4>

            <!-- Specs Grid -->
            <div class="grid grid-cols-4 gap-2 py-3 border-y border-slate-100 text-center text-xs mb-3">
              <div class="bg-slate-50 p-1.5 rounded-xl">
                <div class="font-extrabold text-slate-800">${p.sqm}</div>
                <div class="text-[10px] text-slate-400 uppercase">m² útiles</div>
              </div>
              <div class="bg-slate-50 p-1.5 rounded-xl">
                <div class="font-extrabold text-slate-800">${p.rooms}</div>
                <div class="text-[10px] text-slate-400 uppercase">Hab.</div>
              </div>
              <div class="bg-slate-50 p-1.5 rounded-xl">
                <div class="font-extrabold text-slate-800">${p.bathrooms || 1}</div>
                <div class="text-[10px] text-slate-400 uppercase">Baños</div>
              </div>
              <div class="bg-slate-50 p-1.5 rounded-xl">
                <div class="font-bold text-slate-800">${p.has_elevator ? 'Sí' : 'No'}</div>
                <div class="text-[10px] text-slate-400 uppercase">Ascensor</div>
              </div>
            </div>

            <!-- ML Verdict Box -->
            <div class="mb-4">
              ${savingsHtml}
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="grid grid-cols-2 gap-2 pt-2">
            <button 
              type="button" 
              onclick="focusPropertyOnMap('${p.id}')" 
              class="py-2.5 px-3 rounded-xl border border-slate-200 hover:border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700 font-bold text-xs flex items-center justify-center gap-1.5 transition-colors"
            >
              <i data-lucide="map" class="w-3.5 h-3.5 text-slate-500"></i>
              Ver en Mapa
            </button>

            <a 
              href="${portalUrl}" 
              target="_blank" 
              rel="noopener noreferrer" 
              class="py-2.5 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs flex items-center justify-center gap-1.5 shadow-sm transition-all hover:shadow"
            >
              <span>Ver Anuncio</span>
              <i data-lucide="external-link" class="w-3.5 h-3.5 text-emerald-400"></i>
            </a>
          </div>

        </div>

      </div>
    `;
  }).join('');

  grid.innerHTML = cardsHtml;
  if (window.lucide) {
    lucide.createIcons();
  }
}

/**
 * Focus and zoom to property on Leaflet map
 */
window.focusPropertyOnMap = function(propertyId) {
  const p = state.allProperties.find(x => x.id === propertyId);
  if (!p || !p.lat || !p.lon || !state.map) return;

  // Smooth scroll to map
  const mapElement = document.getElementById('mapa-section');
  if (mapElement) {
    mapElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  setTimeout(() => {
    state.map.flyTo([p.lat, p.lon], 16, { duration: 1.0 });
    const marker = state.markersById[propertyId];
    if (marker) {
      setTimeout(() => marker.openPopup(), 1100);
    }
  }, 300);
};

/**
 * Setup Predictive Valuation Simulator
 */
function setupSimulator() {
  const form = document.getElementById('calculator-form');
  const sqmSlider = document.getElementById('sim-sqm');
  const sqmLabel = document.getElementById('sim-sqm-label');

  if (sqmSlider && sqmLabel) {
    sqmSlider.addEventListener('input', (e) => {
      sqmLabel.innerText = `${e.target.value} m²`;
    });
  }

  // Simulator Room Selector
  const simRoomBtns = document.querySelectorAll('.sim-room-btn');
  simRoomBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      simRoomBtns.forEach(b => {
        b.classList.remove('bg-emerald-600', 'text-white', 'border-emerald-500', 'active');
        b.classList.add('bg-slate-900', 'text-slate-300', 'border-slate-700');
      });
      btn.classList.remove('bg-slate-900', 'text-slate-300', 'border-slate-700');
      btn.classList.add('bg-emerald-600', 'text-white', 'border-emerald-500', 'active');
      state.sim.rooms = parseInt(btn.getAttribute('data-sim-rooms') || '2');
    });
  });

  // Simulator Bath Selector
  const simBathBtns = document.querySelectorAll('.sim-bath-btn');
  simBathBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      simBathBtns.forEach(b => {
        b.classList.remove('bg-emerald-600', 'text-white', 'border-emerald-500', 'active');
        b.classList.add('bg-slate-900', 'text-slate-300', 'border-slate-700');
      });
      btn.classList.remove('bg-slate-900', 'text-slate-300', 'border-slate-700');
      btn.classList.add('bg-emerald-600', 'text-white', 'border-emerald-500', 'active');
      state.sim.baths = parseInt(btn.getAttribute('data-sim-baths') || '1');
    });
  });

  // Form Submit
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await runSimulation();
    });
  }

  // Pre-calculate initial simulation after load
  setTimeout(() => {
    runSimulation();
  }, 600);
}

/**
 * Execute Simulation (API with fallback)
 */
async function runSimulation() {
  const neighborhoodId = document.getElementById('sim-neighborhood')?.value || 'pescaderia_ensanche';
  const sqm = parseFloat(document.getElementById('sim-sqm')?.value || '85');
  const propertyType = document.getElementById('sim-type')?.value || 'piso';
  const hasElevator = document.getElementById('sim-elevator')?.checked ?? true;
  const hasParking = document.getElementById('sim-parking')?.checked ?? false;
  const furnished = document.getElementById('sim-furnished')?.checked ?? false;
  const isExterior = document.getElementById('sim-exterior')?.checked ?? true;
  const offeredPriceInput = document.getElementById('sim-offered-price')?.value;
  const offeredPrice = offeredPriceInput ? parseFloat(offeredPriceInput) : null;

  const payload = {
    neighborhood_id: neighborhoodId,
    sqm: sqm,
    rooms: state.sim.rooms,
    bathrooms: state.sim.baths,
    property_type: propertyType,
    has_elevator: hasElevator,
    has_parking: hasParking,
    furnished: furnished,
    is_exterior: isExterior,
    offered_price: offeredPrice,
  };

  let result = null;

  // Try API first
  try {
    const res = await fetch(`${state.apiBaseUrl}/api/v1/valuation/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      result = await res.json();
    }
  } catch (err) {
    console.warn('Simulation API offline, using mathematical ML approximation:', err);
  }

  // Fallback ML Mathematical Approximation
  if (!result) {
    result = calculateFallbackValuation(payload);
  }

  renderSimulationResult(result);
}

/**
 * Offline Mathematical Valuation Approximation matching the trained model
 */
function calculateFallbackValuation(p) {
  // Base neighborhood €/m² reference
  const neighborhoodRates = {
    pescaderia_ensanche: 17.3,
    ciudad_vieja: 15.1,
    monte_alto: 14.8,
    riazor_ciudad_jardin: 14.2,
    cuatro_caminos: 13.6,
    matogrande: 12.8,
    los_mallos: 12.1,
    sagrada_familia: 11.4,
    elvina: 11.0,
    agras_del_orzán: 10.8,
  };

  const baseRate = neighborhoodRates[p.neighborhood_id] || 13.5;
  let price = p.sqm * baseRate;

  // Feature coefficients
  if (p.has_elevator) price *= 1.07;
  if (p.has_parking) price += 85.0;
  if (p.furnished) price *= 1.04;
  if (!p.is_exterior) price *= 0.92;
  if (p.rooms > 2) price += (p.rooms - 2) * 45;
  if (p.bathrooms > 1) price += (p.bathrooms - 1) * 60;

  const predicted = Math.round(price);
  const minRange = Math.round(predicted * 0.90);
  const maxRange = Math.round(predicted * 1.10);
  const predSqm = (predicted / p.sqm).toFixed(2);

  let verdict = 'Precio de mercado';
  let devPct = null;

  if (p.offered_price) {
    devPct = ((p.offered_price - predicted) / predicted) * 100;
    if (devPct < -12.0) {
      verdict = 'Oportunidad / Muy buen precio';
    } else if (devPct > 12.0) {
      verdict = 'Sobreprecio';
    }
  }

  return {
    predicted_price: predicted,
    price_range_min: minRange,
    price_range_max: maxRange,
    predicted_price_sqm: parseFloat(predSqm),
    market_verdict: verdict,
    deviation_pct: devPct ? parseFloat(devPct.toFixed(1)) : null,
    offered_price: p.offered_price,
    neighborhood_id: p.neighborhood_id,
    sqm: p.sqm,
    model_version: '1.0.0 (Fallback)',
  };
}

/**
 * Render Simulation Outputs on UI
 */
function renderSimulationResult(res) {
  const priceDisplay = document.getElementById('sim-res-price');
  const sqmDisplay = document.getElementById('sim-res-sqm-price');
  const rangeDisplay = document.getElementById('sim-res-range');
  const verdictBox = document.getElementById('sim-verdict-box');
  const verdictIcon = document.getElementById('sim-verdict-icon');
  const verdictTitle = document.getElementById('sim-verdict-title');
  const verdictDesc = document.getElementById('sim-verdict-desc');

  if (priceDisplay) priceDisplay.innerText = `${Math.round(res.predicted_price)} €/mes`;
  if (sqmDisplay) sqmDisplay.innerText = `Estimado: ${res.predicted_price_sqm} €/m²`;
  if (rangeDisplay) rangeDisplay.innerText = `${Math.round(res.price_range_min)} € - ${Math.round(res.price_range_max)} €`;

  if (!verdictBox || !verdictTitle || !verdictDesc) return;

  if (res.offered_price) {
    const dev = res.deviation_pct ?? 0;
    if (res.market_verdict.includes('Oportunidad')) {
      verdictBox.className = 'p-5 rounded-2xl border bg-emerald-950/60 border-emerald-500/50 text-center transition-all';
      verdictIcon.className = 'w-12 h-12 rounded-full mx-auto flex items-center justify-center mb-2 bg-emerald-500 text-slate-950';
      verdictIcon.innerHTML = `<i data-lucide="sparkles" class="w-6 h-6"></i>`;
      verdictTitle.innerHTML = `<span class="text-emerald-300">🌟 ¡Gran Oportunidad Detectada!</span>`;
      verdictDesc.innerHTML = `El precio ofertado (<strong>${res.offered_price} €</strong>) está un <strong class="text-emerald-400">${Math.abs(Math.round(dev))}% por debajo</strong> de su valor estimado de mercado (${Math.round(res.predicted_price)} €). Es un precio excelente.`;
    } else if (res.market_verdict.includes('Sobreprecio')) {
      verdictBox.className = 'p-5 rounded-2xl border bg-rose-950/60 border-rose-500/50 text-center transition-all';
      verdictIcon.className = 'w-12 h-12 rounded-full mx-auto flex items-center justify-center mb-2 bg-rose-500 text-white';
      verdictIcon.innerHTML = `<i data-lucide="alert-triangle" class="w-6 h-6"></i>`;
      verdictTitle.innerHTML = `<span class="text-rose-300">⚠️ Alerta de Sobreprecio</span>`;
      verdictDesc.innerHTML = `El precio ofertado (<strong>${res.offered_price} €</strong>) supera en un <strong class="text-rose-400">+${Math.round(dev)}%</strong> la tasación recomendada (${Math.round(res.predicted_price)} €). Intenta negociar a la baja.`;
    } else {
      verdictBox.className = 'p-5 rounded-2xl border bg-blue-950/60 border-blue-500/50 text-center transition-all';
      verdictIcon.className = 'w-12 h-12 rounded-full mx-auto flex items-center justify-center mb-2 bg-blue-500 text-white';
      verdictIcon.innerHTML = `<i data-lucide="scale" class="w-6 h-6"></i>`;
      verdictTitle.innerHTML = `<span class="text-blue-300">⚖️ Precio Justo de Mercado</span>`;
      verdictDesc.innerHTML = `La renta de <strong>${res.offered_price} €</strong> se encuentra dentro del rango de tolerancia normal del mercado (desviación: ${dev > 0 ? '+' : ''}${dev}%).`;
    }
  } else {
    verdictBox.className = 'p-5 rounded-2xl border bg-slate-900/60 border-slate-700 text-center';
    verdictIcon.className = 'w-12 h-12 rounded-full mx-auto flex items-center justify-center mb-2 bg-slate-800 text-emerald-400';
    verdictIcon.innerHTML = `<i data-lucide="check-circle" class="w-6 h-6"></i>`;
    verdictTitle.innerText = `Tasación Estimada: ${Math.round(res.predicted_price)} €/mes`;
    verdictDesc.innerHTML = `Introduce un precio ofertado en el formulario para obtener un diagnóstico comparativo inmediato.`;
  }

  if (window.lucide) {
    lucide.createIcons();
  }
}

/**
 * Render Neighborhoods Ranking & Comparison Cards
 */
function renderNeighborhoodRanking() {
  const container = document.getElementById('neighborhoods-ranking');
  if (!container) return;

  const neighborhoods = state.neighborhoodStats.length > 0 ? state.neighborhoodStats : [
    { neighborhood: 'Pescadería - Ensanche - Cantones', avg_price: 1350, avg_price_sqm: 17.29, count: 120 },
    { neighborhood: 'Ciudad Vieja', avg_price: 1180, avg_price_sqm: 15.12, count: 65 },
    { neighborhood: 'Monte Alto - Zalaeta - Orzán', avg_price: 1050, avg_price_sqm: 14.85, count: 140 },
    { neighborhood: 'Riazor - Los Rosales - Ciudad Jardín', avg_price: 1100, avg_price_sqm: 14.20, count: 115 },
    { neighborhood: 'Cuatro Caminos - Nuevos Ministerios', avg_price: 990, avg_price_sqm: 13.62, count: 130 },
    { neighborhood: 'Matogrande - Eirís', avg_price: 940, avg_price_sqm: 12.80, count: 70 },
    { neighborhood: 'Los Mallos - Estación', avg_price: 820, avg_price_sqm: 12.10, count: 95 },
    { neighborhood: 'Sagrada Familia', avg_price: 760, avg_price_sqm: 11.40, count: 55 },
    { neighborhood: 'Elviña - Castro - Flores', avg_price: 740, avg_price_sqm: 11.02, count: 60 },
    { neighborhood: 'Agra del Orzán - Ventorrillo', avg_price: 710, avg_price_sqm: 10.85, count: 90 },
  ];

  const maxSqm = Math.max(...neighborhoods.map(n => n.avg_price_sqm));

  const itemsHtml = neighborhoods.map((n, idx) => {
    const pct = (n.avg_price_sqm / maxSqm) * 100;
    return `
      <div class="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 hover:bg-white hover:shadow-md transition-all">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span class="w-6 h-6 rounded-lg bg-slate-200 text-slate-700 font-extrabold text-xs flex items-center justify-center">
              #${idx + 1}
            </span>
            <span class="font-bold text-slate-900 text-sm">${n.neighborhood}</span>
          </div>
          <div class="text-right">
            <span class="text-sm font-black text-emerald-700">${n.avg_price_sqm.toFixed(1)} €/m²</span>
          </div>
        </div>

        <div class="w-full bg-slate-200 h-2 rounded-full overflow-hidden mb-2">
          <div class="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full" style="width: ${pct}%"></div>
        </div>

        <div class="flex justify-between text-xs text-slate-500">
          <span>Renta media: <strong>${Math.round(n.avg_price)} €/mes</strong></span>
          <span>${n.count} ofertas registradas</span>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = itemsHtml;
}
