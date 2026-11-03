"use strict";

// One category shared by Forecasts, Models and History; subscribers only render.
const sharedCategory = (() => {
  let value = 'Action';
  const listeners = new Set();
  const valid = new Set(['Action', 'Strategy', 'RPG', 'Massively Multiplayer', 'Indie']);
  return {
    get: () => value,
    subscribe: listener => listeners.add(listener),
    set(next) {
      if (!valid.has(next) || next === value) return false;
      value = next;
      listeners.forEach(listener => listener(next));
      return true;
    }
  };
})();


(() => {
  const views = [...document.querySelectorAll("[data-view]")];
  const navigation = document.getElementById("primary-nav");
  const menu = document.querySelector(".menu-toggle");
  const main = document.getElementById("main");
  const routes = new Set(views.map((view) => view.dataset.view));
  const narrowScreen = window.matchMedia("(max-width: 640px)");
  const titles = {
    overview: "Overview",
    forecasts: "Forecast explorer",
    history: "Historical activity",
    models: "Model comparison",
    methods: "Methodology",
  };

  function closeMenu() {
    menu.setAttribute("aria-expanded", "false");
    navigation.hidden = narrowScreen.matches;
  }

  let activeView;

  function showView(moveFocus = false) {
    const requested = window.location.hash.slice(1);
    const current = routes.has(requested) ? requested : "overview";
    for (const view of views) {
      view.hidden = view.dataset.view !== current;
      view.classList.toggle("screen-enter", Boolean(activeView && activeView !== current && !view.hidden));
    }
    activeView = current;
    for (const link of navigation.querySelectorAll("[data-route]")) {
      if (link.dataset.route === current) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    document.title = `${titles[current]} · Steam Genre Forecast 2027: a fixed-cohort activity study`;
    closeMenu();
    main.scrollTop = 0;
    if (moveFocus) main.focus({ preventScroll: true });
  }

  menu.addEventListener("click", () => {
    const expanded = menu.getAttribute("aria-expanded") === "true";
    menu.setAttribute("aria-expanded", String(!expanded));
    navigation.hidden = expanded;
  });

  document.querySelector(".skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    main.focus({ preventScroll: true });
    main.scrollIntoView({ block: "start", behavior: "auto" });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.getAttribute("aria-expanded") === "true") {
      closeMenu();
      menu.focus();
    }
  });

  // Re-selecting the current route still returns focus to the content.
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-route]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (window.location.hash === link.hash) showView(true);
  });

  window.addEventListener("hashchange", () => {
    // The skip link targets the main landmark rather than a routed section.
    if (window.location.hash !== "#main") showView(true);
  });
  narrowScreen.addEventListener("change", closeMenu);
  showView();
  document.documentElement.classList.add("js");
})();

(() => {
  const annual = JSON.parse(document.getElementById('study-data').textContent);
  const monthly = JSON.parse(document.getElementById('monthly-data').textContent);
  document.querySelector('.overview-finding p').textContent = heroFindingCopy(annual);
  const panel = document.getElementById('forecasts');
  const slider = document.getElementById('forecast-month');
  const categories = ['Action', 'Strategy', 'RPG', 'Massively Multiplayer', 'Indie'];
  const colors = ['#805499', '#397b64', '#956231', '#376f8e', '#9b4f78'];
  const policies = ['Provisional v2 policy', 'Last-value reference'];
  const state = {category: sharedCategory.get(), policy: policies[0], lead: 1};
  const label = category => category === 'Massively Multiplayer' ? 'MMO' : category;
  const approach = () => state.policy === policies[0] ? 'Selected models' : 'Last-value reference';
  const number = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});
  const detail = new Intl.NumberFormat('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const date = month => new Intl.DateTimeFormat('en-US', {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(new Date(month + 'T00:00:00Z'));
  const NS = 'http://www.w3.org/2000/svg';
  const make = (tag, attrs = {}, content) => {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (content !== undefined) node.textContent = content;
    return node;
  };
  const text = (x, y, value, attrs = {}) => make('text', {x, y, ...attrs}, value);
  const aSvg = document.getElementById('annual-live');
  const mSvg = document.getElementById('monthly-live');
  const aTip = document.getElementById('annual-tooltip');
  const mTip = document.getElementById('monthly-tooltip');
  const aMax = 4050000;
  let aLeft = 136, aWidth = 620, chartWidth = 890;
  const compact = () => window.matchMedia("(max-width:1100px)").matches;
  const phone = () => window.matchMedia("(max-width:640px)").matches;
  const aX = value => aLeft + Number(value) / aMax * aWidth;
  let mLeft = 95, mWidth = 700, mTop = 45, mHeight = 300;
  const mX = lead => mLeft + (lead - 1) / 22 * mWidth;
  let annualEvidence = null;
  const missingWapes = new Set();
  const rows = new Map();
  let series = [], ceiling = 1, tipsDismissed = false;
  const mY = value => mTop + mHeight - Number(value) / ceiling * mHeight;
  const annualRow = category => annual.find(r => r.category === category && r.policy === state.policy);
  const monthlyRow = lead => series.find(r => Number(r.lead) === Number(lead));

  function tip(node, value) {
    node.textContent = value;
    node.hidden = false;
  }
  function annualTip(category) {
    if (tipsDismissed) return;
    const row = annualRow(category);
    tip(aTip, `${label(category)} · 2027 annual mean · ${approach()} · ${row.model} · ${formatStudyNumber(row.projected_mean_activity)} average concurrent activity. Display rounded to three significant figures.`);
  }
  function monthTip(lead) {
    if (tipsDismissed) return;
    const row = monthlyRow(lead);
    tip(mTip, `${label(state.category)} · ${date(row.month)} · ${approach()} · ${detail.format(row.prediction)} average concurrent activity. Projected activity; display rounded to two decimals.`);
  }
  function hideTips() { aTip.hidden = true; mTip.hidden = true; }
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { hideTips(); tipsDismissed = true; } });
  for (const node of [aTip, mTip]) node.addEventListener('pointerleave', () => { node.hidden = true; });

  // Stable SVG groups retain focus and selection when approach changes reorder rows.
  aSvg.append(make('title', {id: 'annual-live-title'}, '2027 annual comparison: projected annual mean activity'));
  const desc = make('desc', {id: 'annual-live-desc'}, 'Five overlapping Steam categories. Choose a category using its row or the category buttons. Bars use a shared zero-based linear scale.');
  aSvg.append(desc);
  const defs = make('defs');
  categories.forEach((category, index) => {
    const pattern = make('pattern', {id: `forecast-segment-${index}`, width: 6, height: 12, patternUnits: 'userSpaceOnUse'});
    pattern.append(make('path', {d: 'M0 0V12', stroke: '#eee5f7', 'stroke-width': 1}));
    defs.append(pattern);
  });
  aSvg.append(defs);
  const annualGrid = make('g');
  const annualUnits = text(450, 311, 'Projected annual mean concurrent activity · millions', {'text-anchor': 'middle', class: 'chart-axis'});
  aSvg.append(annualGrid, annualUnits);
  categories.forEach((category, index) => {
    const group = make('g', {role: 'button', tabindex: 0, 'data-annual-category': category, 'aria-describedby': 'annual-tooltip'});
    const hit = make('rect', {x: 8, y: -21, width: 870, height: 42, fill: 'transparent', class: 'annual-hit'});
    const bracket = make('path', {d: 'M20 -17H10V-8 M10 8V17H20 M866 -17H876V-8 M876 8V17H866', class: 'selection-brackets', fill: 'none'});
    const name = text(26, 6, label(category), {class: 'chart-category'});
    const bar = make('rect', {x: aLeft, y: -6, height: 12, fill: colors[index], 'data-annual-bar': category});
    const division = make('rect', {x: aLeft, y: -6, height: 12, fill: `url(#forecast-segment-${index})`});
    const cap = make('path', {stroke: colors[index], 'stroke-width': 1});
    const value = text(852, 6, '', {'text-anchor': 'end', class: 'chart-value'});
    group.append(hit, bracket, name, bar, division, cap, value);
    group.addEventListener('click', () => { tipsDismissed = false; selectCategory(category); annualTip(category); });
    group.addEventListener('focus', () => { tipsDismissed = false; annualTip(category); });
    group.addEventListener('pointerenter', event => { tipsDismissed = false; if (event.pointerType !== 'touch') annualTip(category); });
    // Keep the information window open across the gap below the chart so it can be hovered.
    group.addEventListener('blur', () => { aTip.hidden = true; });
    group.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectCategory(category); annualTip(category); }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const ordered = sortedAnnual();
        const next = (ordered.findIndex(r => r.category === category) + (event.key === 'ArrowDown' ? 1 : 4)) % 5;
        rows.get(ordered[next].category).group.focus();
      }
    });
    aSvg.append(group);
    rows.set(category, {group, hit, bracket, name, bar, division, cap, value});
  });
  function sortedAnnual() { return annual.filter(r => r.policy === state.policy).sort((a, b) => Number(b.projected_mean_activity) - Number(a.projected_mean_activity)); }
  function renderAnnual() {
    const ordered = sortedAnnual();
    const order = ordered.map(r => r.category).join('|');
    const focused = document.activeElement;
    ordered.forEach((record, index) => {
      const row = rows.get(record.category), width = aX(record.projected_mean_activity) - aLeft;
      const narrow = compact(), twoLine = phone();
      const rowY = twoLine ? 36 + index * 58 : 52 + index * 43;
      row.group.setAttribute('transform', `translate(0 ${rowY})`);
      row.hit.setAttribute('width', narrow ? chartWidth - 16 : 870);
      row.hit.setAttribute('y', twoLine ? -24 : -21);
      row.hit.setAttribute('height', twoLine ? 59 : 42);
      row.name.setAttribute('x', twoLine ? 18 : narrow ? 18 : 26);
      row.name.setAttribute('y', twoLine ? -2 : 6);
      row.value.setAttribute('x', chartWidth - (narrow ? 14 : 38));
      row.value.setAttribute('y', twoLine ? -2 : 6);
      row.bar.setAttribute('x', aLeft); row.division.setAttribute('x', aLeft);
      row.bar.setAttribute('y', twoLine ? 12 : -6); row.division.setAttribute('y', twoLine ? 12 : -6);
      const right = chartWidth - (narrow ? 6 : 14), left = twoLine ? 5 : 10;
      const bottom = twoLine ? 33 : 17, top = twoLine ? -22 : -17;
      row.bracket.setAttribute('d', `M${left+10} ${top}H${left}V${top+9} M${left} ${bottom-9}V${bottom}H${left+10} M${right-10} ${top}H${right}V${top+9} M${right} ${bottom-9}V${bottom}H${right-10}`);
      row.group.setAttribute('aria-pressed', String(record.category === state.category));
      row.group.setAttribute('aria-label', `${label(record.category)}, ${approach()}, 2027 annual mean ${formatStudyNumber(record.projected_mean_activity)} average concurrent activity, rank ${index + 1}`);
      row.bar.setAttribute('width', width); row.division.setAttribute('width', width);
      row.bar.setAttribute('data-value', record.projected_mean_activity);
      row.cap.setAttribute('d', `M${aX(record.projected_mean_activity)} ${phone() ? 12 : -6}V${phone() ? 24 : 6}`);
      row.value.textContent = formatStudyNumber(record.projected_mean_activity);
      if (narrow) {
        // Measure the actual label/value/bar union, then add the same padding on every side.
        const bounds = [row.name, row.value, row.bar].map(node => node.getBBox());
        const pad = 5, l = Math.min(...bounds.map(b => b.x)) - pad, r = Math.max(...bounds.map(b => b.x + b.width)) + pad;
        const t = Math.min(...bounds.map(b => b.y)) - pad, b = Math.max(...bounds.map(b => b.y + b.height)) + pad;
        row.bracket.setAttribute('d', `M${l+8} ${t}H${l}V${t+8} M${l} ${b-8}V${b}H${l+8} M${r-8} ${t}H${r}V${t+8} M${r} ${b-8}V${b}H${r-8}`);
        row.bracket.dataset.bounds = JSON.stringify({left:l,right:r,top:t,bottom:b,padding:pad});
        row.hit.setAttribute('x', l); row.hit.setAttribute('y', t); row.hit.setAttribute('width', r-l); row.hit.setAttribute('height', b-t);
      } else row.hit.setAttribute('x', 8);

      row.bracket.hidden = record.category !== state.category;
      row.bracket.setAttribute('visibility', record.category === state.category ? 'visible' : 'hidden');
    });
    aSvg.dataset.policy = state.policy;
    if (aSvg.dataset.order !== order) {
      ordered.forEach(record => aSvg.append(rows.get(record.category).group));
      if (aSvg.contains(focused)) focused.focus({preventScroll: true});
    }
    aSvg.dataset.order = order;
    document.getElementById('annual-approach-note').textContent = compact() ? '2027 projected annual means · categories overlap.' : `${approach()} · projected annual means for 2027 · corner brackets mark the selected category. Categories overlap. On narrow screens, scroll within the chart to see all values.`;
    table('annual-values', ordered.map((r, i) => [i + 1, label(r.category), approach(), r.model, String(r.projected_mean_activity)]));
    if (annualEvidence) {
      const pairs = annualNearTies(annual, state.policy, annualEvidence);
      const ties = pairs.filter(pair => pair.nearTie);
      const caveat = document.getElementById('annual-near-ties');
      const runs = renderNearTieCaveats(caveat, pairs, label);
      renderTypicalErrorNote(document.getElementById('annual-typical-error'), annualEvidence, state.policy, categories);
      for (const [category, row] of rows) {
        const near = ties.some(pair => pair.higher === category || pair.lower === category);
        row.group.dataset.nearTie = String(near);
        const run = runs.find(run => run.categories.includes(category));
        row.group.setAttribute('aria-describedby', run ? `annual-tooltip ${run.id}` : 'annual-tooltip');
      }
      for (const pair of pairs) {
        for (const category of [pair.higher, pair.lower]) {
          if (pair.wapes[category] === null && !missingWapes.has(category + state.policy)) {
            missingWapes.add(category + state.policy);
            console.warn('Long-horizon WAPE unavailable; no near-tie caveat:', category, state.policy);
          }
        }
      }
    }

  }
  const mGrid = make('g'), mTicks = make('g');
  const mLine = make('path', {fill: 'none', 'stroke-width': 2.5, 'stroke-linejoin': 'miter', 'data-monthly-series': ''});
  const allPoints = make('g', {'aria-hidden': 'true'});
  const cursor = make('path', {class: 'month-cursor'});
  const point = make('rect', {width: 8, height: 8, class: 'month-point'});
  mSvg.append(make('title', {}, 'Monthly forecast'), make('desc', {}, 'Use left and right arrows, Home and End, the month slider, or tap a month on the chart.'), mGrid, mTicks, mLine, allPoints, cursor, point);
  const monthLabels = make('g');
  mSvg.append(monthLabels);
  function renderSeries() {
    series = monthly.filter(r => r.category === state.category && r.policy === state.policy).sort((a, b) => a.lead - b.lead);
    // A zero-based category domain remains fixed across the two saved approaches.
    const maximum = Math.max(...monthly.filter(r => r.category === state.category).map(r => Number(r.prediction)));
    const step = maximum > 2000000 ? 1000000 : 200000;
    ceiling = Math.ceil(maximum * 1.08 / step) * step;
    mGrid.replaceChildren(); mTicks.replaceChildren();
    for (let i = 0; i <= (compact() ? 2 : 4); i++) {
      const value = ceiling * i / (compact() ? 2 : 4);
      mGrid.append(make('path', {d: `M${mLeft} ${mY(value)}H${mLeft + mWidth}`, class: 'chart-grid'}));
      mTicks.append(text(mLeft - (compact() ? 7 : 14), mY(value) + 5, (value / 1000000).toFixed(2).replace(/0$/, ''), {'text-anchor': 'end', class: 'chart-axis'}));
    }
    const color = colors[categories.indexOf(state.category)];
    mLine.setAttribute('d', series.map((r, i) => `${i ? 'L' : 'M'}${mX(Number(r.lead))} ${mY(r.prediction)}`).join(' '));
    mLine.setAttribute('stroke', color);
    mLine.setAttribute('stroke-dasharray', state.policy === policies[1] ? '7 4' : 'none');
    point.setAttribute('fill', color);
    allPoints.replaceChildren(...series.map(row => make('rect', {x:mX(row.lead)-2.5, y:mY(row.prediction)-2.5, width:5, height:5, fill:color})));
    point.setAttribute('width', 10); point.setAttribute('height', 10);
    point.setAttribute('stroke-width', 2);
    document.querySelector('[data-panel-category]').textContent = label(state.category).toUpperCase();
    document.querySelector('[data-panel-key]').textContent = `${approach()} · ${state.policy === policies[1] ? 'dashed' : 'solid'} line`;
    document.querySelector('.key-symbol').style.setProperty('--series-color', color);
    document.querySelector('.key-symbol').classList.toggle('reference-key', state.policy === policies[1]);

    mSvg.dataset.category = state.category; mSvg.dataset.policy = state.policy; mSvg.dataset.ceiling = ceiling;
    document.getElementById('monthly-legend').textContent = `${label(state.category)} · ${approach()} · ${series[0].model} · ${state.policy === policies[1] ? 'dashed' : 'solid'} line`;
    document.getElementById('monthly-scale').textContent = `For ${label(state.category)}, the scale runs from 0–${number.format(ceiling)}. It stays the same when you switch approaches; other categories have their own scale.`;
    table('monthly-values', series.map(r => [date(r.month), approach(), r.model, String(r.prediction)]));
  }
  function table(id, data) {
    const body = document.getElementById(id);
    body.replaceChildren(...data.map(row => {
      const tr = document.createElement('tr');
      row.forEach((value, index) => { const cell = document.createElement(index === 0 ? 'th' : 'td'); if (!index) cell.scope = 'row'; cell.textContent = value; tr.append(cell); });
      return tr;
    }));
  }
  function updateMonth() {
    const row = monthlyRow(state.lead), monthLabel = `${date(row.month)} · month ${state.lead} of 23`;
    slider.value = state.lead;
    slider.setAttribute('aria-valuetext', `${monthLabel}; ${label(state.category)}; ${approach()}; ${detail.format(row.prediction)} average concurrent activity`);
    document.getElementById('forecast-month-label').textContent = compact() ? `Month ${state.lead} of 23` : monthLabel;
    document.querySelector('[data-month-category]').textContent = label(state.category);
    document.querySelector('[data-month-value]').textContent = detail.format(row.prediction);
    document.querySelector('[data-month-approach]').textContent = approach();
    cursor.setAttribute('d', `M${mX(state.lead)} ${mTop}V${mTop + mHeight}`);
    point.setAttribute('x', mX(state.lead) - 5); point.setAttribute('y', mY(row.prediction) - 5);
    document.querySelector('[data-panel-month]').textContent = date(row.month);
    document.querySelector('[data-footer-month]').textContent = date(row.month);
    document.querySelectorAll('[data-month-step]').forEach(button => {button.disabled = Number(button.dataset.monthStep) < 0 ? state.lead === 1 : state.lead === 23;});
    point.setAttribute('data-value', row.prediction); point.setAttribute('data-lead', state.lead);
    mSvg.setAttribute('aria-label', `${label(state.category)} monthly forecast; ${monthLabel}; ${approach()}; ${detail.format(row.prediction)} average concurrent activity. Arrow keys change month.`);
    // Pan only the chart's own scroll channel so the selected month stays visible on mobile.
    const scroll = mSvg.parentElement, bounds = scroll.getBoundingClientRect(), marker = point.getBoundingClientRect();
    if (bounds.width && scroll.scrollWidth > scroll.clientWidth) {
      if (marker.right > bounds.right - 18) scroll.scrollLeft += marker.right - bounds.right + 18;
      else if (marker.left < bounds.left + 18) scroll.scrollLeft -= bounds.left - marker.left + 18;
    }
  }
  function selectCategory(category) {
    if (!sharedCategory.set(category)) applyForecastCategory(category);
  }
  function applyForecastCategory(category) {
    state.category = category; hideTips();
    document.querySelectorAll('[data-category-select]').forEach(control => control.setAttribute('aria-pressed', String(control.dataset.categorySelect === category)));
    document.querySelectorAll('[data-selected-name]').forEach(node => { node.textContent = category; });
    document.querySelectorAll('[data-model-category]').forEach(body => { body.hidden = body.dataset.modelCategory !== category; });
    document.querySelectorAll('[data-model-explanation]').forEach(section => { section.hidden = section.dataset.modelExplanation !== category; });
    renderAnnual(); renderSeries(); updateRecord(); updateMonth();
    revealCategory();
  }
  sharedCategory.subscribe(applyForecastCategory);
  function revealCategory() {
    if (compact()) {
      const button = panel.querySelector(`[data-category-select="${state.category}"]`), strip = button.parentElement;
      if (!strip.clientWidth) return;
      panel.querySelector('.category-scroll-hint').hidden = strip.scrollWidth <= strip.clientWidth + 1;
      const b = button.getBoundingClientRect(), r = strip.getBoundingClientRect();
      if (b.right > r.right - 5) strip.scrollLeft += b.right - r.right + 5;
      else if (b.left < r.left + 5) strip.scrollLeft -= r.left - b.left + 5;
    }
  }
  function updateRecord() {
    const record = annualRow(state.category);
    document.querySelector('[data-selected-value]').textContent = formatStudyNumber(record.projected_mean_activity);
    document.querySelector('[data-selected-model]').textContent = record.model;
    document.querySelector('[data-record-approach]').textContent = approach();
    document.querySelector('[data-mobile-summary]').textContent = `${label(state.category)} · ${record.model}`;
  }
  document.querySelectorAll('[data-category-select]').forEach(button => button.addEventListener('click', () => selectCategory(button.dataset.categorySelect)));
  panel.querySelectorAll('[name="forecast-approach"]').forEach(control => control.addEventListener('change', () => {
    state.policy = control.value; hideTips(); renderAnnual(); renderSeries(); updateRecord(); updateMonth();
  }));
  slider.addEventListener('input', () => { state.lead = Number(slider.value); updateMonth(); hideTips(); });
  // Convert through the SVG's coordinate system; pointer input never creates intermediate months.
  function pointerLead(event) {
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(mSvg.getScreenCTM().inverse());
    return Math.min(23, Math.max(1, Math.round((point.x - mLeft) / mWidth * 22) + 1));
  }
  mSvg.addEventListener('pointerdown', event => { tipsDismissed = false; state.lead = pointerLead(event); updateMonth(); monthTip(state.lead); });
  mSvg.addEventListener('pointerenter', () => { tipsDismissed = false; });
  mSvg.addEventListener('pointermove', event => { if (event.pointerType !== 'touch') monthTip(pointerLead(event)); });
  mSvg.addEventListener('focus', () => { tipsDismissed = false; monthTip(state.lead); });
  mSvg.addEventListener('blur', () => { mTip.hidden = true; });
  mSvg.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    tipsDismissed = false;
    state.lead = event.key === 'Home' ? 1 : event.key === 'End' ? 23 : Math.min(23, Math.max(1, state.lead + (event.key === 'ArrowRight' ? 1 : -1)));
    updateMonth(); monthTip(state.lead);
  });
  document.querySelector('.timeline-reset').addEventListener('click', () => {
    state.policy = policies[0]; state.lead = 1;
    panel.querySelectorAll('.live-chart-scroll').forEach(scroll => { scroll.scrollLeft = 0; });
    panel.querySelectorAll('[name="forecast-approach"]').forEach(control => { control.checked = control.value === state.policy; });
    selectCategory('Action');
  });
  function layoutCharts() {
    const narrow = compact(), twoLine = phone();
    const available = aSvg.parentElement.clientWidth;
    if (!available) return;
    chartWidth = narrow ? Math.max(220, available) : 890;
    aLeft = narrow ? (twoLine ? 14 : 104) : 136;
    aWidth = narrow ? chartWidth - aLeft - (twoLine ? 14 : 116) : 620;
    aSvg.setAttribute('viewBox', `0 0 ${chartWidth} ${twoLine ? 338 : 325}`);
    aSvg.dataset.scaleMax = aMax; aSvg.dataset.plotLeft = aLeft; aSvg.dataset.plotWidth = aWidth;
    annualGrid.replaceChildren();
    const ticks = narrow ? [0, 2000000, 4000000] : [0,500000,1000000,1500000,2000000,2500000,3000000,3500000,4000000];
    ticks.forEach(value => {
      // Phone label strips are outside the plot: aligned grid segments occupy only the bar bands.
      const gridPath = twoLine ? Array.from({length:5},(_,i) => `M${aX(value)} ${36+i*58+6}V${36+i*58+28}`).join(' ') : `M${aX(value)} 32V260`;
      annualGrid.append(make('path', {d:gridPath, class:'chart-grid', 'data-annual-grid':value}));
      annualGrid.append(text(aX(value), twoLine ? 326 : 283, (value/1000000).toFixed(1), {'text-anchor':narrow && value===0 ? 'start' : narrow && value===4000000 ? 'end' : 'middle', class:'chart-axis'}));
    });
    annualUnits.setAttribute('visibility', narrow ? 'hidden' : 'visible');
    const monthWidth = narrow ? mSvg.parentElement.clientWidth : 880;
    mLeft = narrow ? 43 : 95; mWidth = narrow ? monthWidth - mLeft - 14 : 700;
    mTop = narrow ? 20 : 45; mHeight = narrow ? 160 : 300;
    mSvg.setAttribute('viewBox', `0 0 ${monthWidth} ${narrow ? 222 : 440}`);
    mSvg.dataset.plotLeft = mLeft; mSvg.dataset.plotWidth = mWidth; mSvg.dataset.plotTop = mTop; mSvg.dataset.plotHeight = mHeight;
    monthLabels.replaceChildren();
    if (!narrow) monthLabels.append(text(95,30,'Average concurrent activity · millions',{class:'chart-axis'}));
    const dates = narrow ? [[1,'Feb 2026'],[12,'Jan 2027'],[23,'Dec 2027']] : [[1,'Feb 2026'],[6,'Jul 2026'],[12,'Jan 2027'],[18,'Jul 2027'],[23,'Dec 2027']];
    dates.forEach(([lead,name]) => monthLabels.append(text(mX(lead),narrow ? 207 : 375,name,{'text-anchor':narrow && lead===1 ? 'start' : narrow && lead===23 ? 'end' : 'middle',class:'chart-axis'})));
    if (!narrow) monthLabels.append(text(445,420,'Forecast month · projections',{'text-anchor':'middle',class:'chart-axis'}));
    aSvg.parentElement.setAttribute('aria-label', narrow ? 'Annual comparison, all five categories on one shared linear scale' : 'Annual comparison; scroll horizontally on narrow screens');
    mSvg.parentElement.setAttribute('aria-label', narrow ? 'Monthly forecast, full February 2026 to December 2027 timeline' : 'Monthly forecast; scroll horizontally on narrow screens');
    hideTips(); renderAnnual(); renderSeries(); updateRecord(); updateMonth(); revealCategory();
  }
  let resizeFrame;
  const resize = new ResizeObserver(() => { cancelAnimationFrame(resizeFrame); resizeFrame = requestAnimationFrame(layoutCharts); });
  resize.observe(aSvg.parentElement); resize.observe(mSvg.parentElement);
  window.matchMedia('(max-width:1100px)').addEventListener('change', layoutCharts);
  window.matchMedia('(max-width:640px)').addEventListener('change', layoutCharts);
  // Enable the live annual only after its renderer is ready; the clean SVG remains the fallback.
  panel.querySelector('.annual-live-shell').hidden = false;
  panel.querySelector('.annual-fallback').hidden = true;
  document.querySelectorAll('[data-month-step]').forEach(button => button.addEventListener('click', () => {state.lead = Math.max(1, Math.min(23, state.lead + Number(button.dataset.monthStep))); updateMonth();}));
  applyForecastCategory(sharedCategory.get());
  layoutCharts();
  fetch('./assets/model-selection-evidence.json').then(response => {
    if (!response.ok) throw new Error('Annual near-tie evidence unavailable');
    return response.json();
  }).then(evidence => {
    annualEvidence = evidence;
    const overviewTies = annualNearTies(annual, policies[0], evidence).filter(pair => pair.nearTie);
    const overviewCaveat = document.getElementById('overview-near-ties');
    const overviewRuns = renderNearTieCaveats(overviewCaveat, annualNearTies(annual, policies[0], evidence), label);
    document.querySelector('#overview img[src*="annual-comparison-pixels.svg"]').setAttribute('aria-describedby', overviewRuns.map(run => run.id).join(' '));
    renderTypicalErrorNote(document.getElementById('overview-typical-error'), evidence, policies[0], categories);
    renderAnnual();
  }).catch(error => console.warn(error));

  document.fonts.ready.then(layoutCharts);
})();

// History keeps its month and continuation state; category selection is shared.
(() => {
  const section = document.getElementById('history');
  const explorer = document.getElementById('history-explorer');
  const status = document.getElementById('history-load-status');
  const saved = document.getElementById('history-saved-figures');
  const svg = document.getElementById('history-live');
  const slider = document.getElementById('history-month');
  const continuation = document.getElementById('history-continuation');
  const categories = ['Action', 'Strategy', 'RPG', 'Massively Multiplayer', 'Indie'];
  const colors = ['#805499', '#397b64', '#956231', '#376f8e', '#9b4f78'];
  const state = {category:sharedCategory.get(), index:59, extended:false};
  const number = new Intl.NumberFormat('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
  const monthName = month => new Intl.DateTimeFormat('en-US', {month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(month+'T00:00:00Z'));
  const label = category => category === 'Massively Multiplayer' ? 'MMO' : category;
  const NS = 'http://www.w3.org/2000/svg';
  const make = (tag, attrs={}, content) => {
    const element = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key,value]) => element.setAttribute(key,value));
    if (content !== undefined) element.textContent = content;
    return element;
  };
  const text = (x,y,content,attrs={}) => make('text',{x,y,...attrs},content);
  let data, records=[], x, y, width, left, right, top, bottom, loading;
  let cursor, point;

  function updateMonth() {
    const record = records[state.index];
    if (!record) return;
    slider.value = String(state.index+1);
    const kind = record.month <= '2026-01-01' ? 'Observed' : 'Projected';
    const range = data.ranges.find(row => row.category === state.category && row.month === record.month);
    const description = `${label(state.category)} · ${monthName(record.month)}; ${kind}; ${number.format(record.value)} average concurrent activity`;
    slider.setAttribute('aria-valuetext', description);
    document.getElementById('history-svg-description').textContent = `${description}. Zero-based category scale. Use arrow keys to change month. The historical error ranges are a rough guide, not a promise about where future values will fall.`;
    document.getElementById('history-readout-title').textContent = `${label(state.category)} · ${monthName(record.month)}`;
    document.getElementById('history-observation-kind').textContent = kind + (kind === 'Observed' ? ' · historical value' : ` · selected models · ${record.model}`);
    document.getElementById('history-value').textContent = number.format(record.value);
    document.getElementById('history-range-readout').textContent = kind === 'Observed' ? 'Historical error ranges do not apply to observed values.' : range ? `Historical error range: ${number.format(range.lower)}–${number.format(range.upper)}. Not a calibrated prediction interval.` : 'Historical error range unavailable';
    cursor.setAttribute('d', `M${x(state.index)} ${top}V${bottom}`);
    point.setAttribute('x',x(state.index)-4.5); point.setAttribute('y',y(record.value)-4.5);
    point.dataset.month = record.month; point.dataset.value = record.value;
    section.querySelector('[data-history-step="-1"]').disabled = state.index===0;
    section.querySelector('[data-history-step="1"]').disabled = state.index===records.length-1;
  }

  function buildTable() {
    const body = document.getElementById('history-values');
    body.replaceChildren(...records.map(record => {
      const row = document.createElement('tr');
      [monthName(record.month),record.month <= '2026-01-01' ? 'Observed' : 'Projected',number.format(record.value)].forEach(value => {
        const cell = document.createElement('td'); cell.textContent=value; row.append(cell);
      });
      return row;
    }));
    document.getElementById('history-table-caption').textContent = `All ${records.length} monthly values for ${label(state.category)}.`;
  }

  function draw() {
    if (!data || section.hidden) return;
    const observed = data.observed.filter(row => row.category===state.category);
    const forecast = data.forecast.filter(row => row.category===state.category);
    const ranges = data.ranges.filter(row => row.category===state.category);
    records = state.extended ? [...observed,...forecast] : observed;
    state.index = Math.min(state.index, records.length-1);
    const available = svg.parentElement.clientWidth-20;
    width = Math.max(220,available);
    const phone = width<500;
    left=46; right=width-14; top=24; bottom=phone?210:254;
    // Keep the category domain stable when revealing or hiding the continuation.
    const maximum = Math.max(...observed.map(r=>r.value),...forecast.map(r=>r.value),...ranges.map(r=>r.upper));
    const step = maximum>2000000 ? 1000000 : 250000;
    const maxY = Math.ceil(maximum*1.06/step)*step;
    x = index => left + index/(records.length-1)*(right-left);
    y = value => bottom - value/maxY*(bottom-top);
    svg.setAttribute('viewBox',`0 0 ${width} ${bottom+(phone?48:40)}`);
    svg.dataset.maxY=maxY; svg.dataset.monthCount=records.length;
    svg.dataset.plotLeft=left; svg.dataset.plotRight=right; svg.dataset.category=state.category;
    svg.style.setProperty('--history-category',colors[categories.indexOf(state.category)]);
    explorer.style.setProperty('--history-category',colors[categories.indexOf(state.category)]);
    svg.replaceChildren(make('title',{id:'history-svg-title'},`${label(state.category)} observed activity${state.extended?' and projected continuation':''}`),make('desc',{id:'history-svg-description'}));
    for(let tick=0;tick<=4;tick++) {
      const value=maxY*tick/4, py=y(value);
      svg.append(make('path',{d:`M${left} ${py}H${right}`,class:'history-grid'}),text(left-7,py+4,Number((value/1000000).toFixed(2)).toString(),{'text-anchor':'end',class:'history-axis'}));
    }
    if(state.extended) {
      svg.append(make('rect',{x:x(59),y:top,width:right-x(59),height:bottom-top,class:'history-forecast-zone'}));
      svg.append(make('path',{d:`M${x(59)} ${top}V${bottom}`,class:'history-cutoff'}));
      svg.append(text(x(59),top-9,'Jan 2026 cutoff',{'text-anchor':'middle',class:'history-axis'}));
      // Each range is a saved monthly interval; step boundaries use the same monthly x positions.
      const upper=ranges.map(r=>({index:records.findIndex(v=>v.month===r.month),value:r.upper}));
      const lower=ranges.map(r=>({index:records.findIndex(v=>v.month===r.month),value:r.lower}));
      const forward=upper.map((r,i)=>`${i?'L':'M'}${x(r.index)} ${i?y(upper[i-1].value):y(r.value)}L${x(r.index)} ${y(r.value)}`).join(' ');
      const lowerPoints=lower.flatMap((r,i)=>i?[[x(r.index),y(lower[i-1].value)],[x(r.index),y(r.value)]]:[[x(r.index),y(r.value)]]);
      const reverse=lowerPoints.reverse().map(([px,py])=>`L${px} ${py}`).join(' ');
      svg.append(make('path',{d:forward+reverse+'Z',class:'history-range', 'data-history-band':''}));
    }
    function series(values,offset,kind) {
      const path=values.map((r,i)=>`${i?'L':'M'}${x(i+offset)} ${i?y(values[i-1].value):y(r.value)}L${x(i+offset)} ${y(r.value)}`).join(' ');
      svg.append(make('path',{d:path,class:`history-series history-${kind}`,'data-history-series':kind}));
      values.forEach((r,i)=>svg.append(make('rect',{x:x(i+offset)-1.5,y:y(r.value)-1.5,width:3,height:3,class:`history-mark history-${kind}`,'data-history-month':r.month,'data-history-value':r.value})));
    }
    series(observed,0,'observed');
    if(state.extended) series(forecast,60,'projection');
    const anchors=state.extended ? [0,59,82] : [0,35,59];
    anchors.forEach((index,i)=>{
      const r=records[index];
      const short=new Intl.DateTimeFormat('en-US',{month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(r.month+'T00:00:00Z'));
      const axisLabel=text(x(index),bottom+25,phone?short.split(' ')[0]:short,{'text-anchor':i===0?'start':i===anchors.length-1?'end':'middle',class:'history-axis'});
      if(phone) axisLabel.append(make('tspan',{x:x(index),dy:15},r.month.slice(0,4)));
      svg.append(axisLabel);
    });
    cursor=make('path',{class:'history-cursor'}); point=make('rect',{width:9,height:9,class:'history-selected'});
    svg.append(cursor,point);
    slider.max=String(records.length);
    document.getElementById('history-chart-title').textContent=`${state.extended?'HISTORY → PROJECTION':'RECORDED ACTIVITY'} / ${label(state.category).toUpperCase()}`;
    document.getElementById('history-period-note').textContent=state.extended?'Observed: February 2021–January 2026. Projected continuation: February 2026–December 2027.':'Observed: February 2021–January 2026. The continuation is hidden.';
    explorer.querySelectorAll('[data-history-projection-key]').forEach(el=>el.hidden=!state.extended);
    explorer.querySelectorAll('[data-history-category]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.historyCategory===state.category)));
    updateMonth();
  }

  function applyHistoryCategory(category) {
    state.category = category;
    explorer.querySelectorAll('[data-history-category]').forEach(button =>
      button.setAttribute('aria-pressed', String(button.dataset.historyCategory === category)));
    if (!data || section.hidden) return;
    draw();
    buildTable();
  }
  function selectHistoryCategory(category) {
    if (!sharedCategory.set(category)) applyHistoryCategory(category);
  }
  sharedCategory.subscribe(applyHistoryCategory);


  async function load() {
    if(section.hidden) return;
    if(data) {applyHistoryCategory(sharedCategory.get());return;}
    if(loading) return;
    loading=true;
    try {
      const response=await fetch('./assets/history-data.json');
      if(!response.ok) throw new Error('History data response unavailable');
      data=await response.json();
      if(!Array.isArray(data.observed)||!Array.isArray(data.forecast)||!Array.isArray(data.ranges)) throw new Error('History data shape unavailable');
      explorer.hidden=false; status.hidden=true; applyHistoryCategory(sharedCategory.get());
    } catch {
      status.textContent='The interactive values couldn’t load. The figures are available below; reload the page to try again.';
      saved.open=true;
    } finally {loading=false;}
  }
  explorer.querySelectorAll('[data-history-category]').forEach(button=>button.addEventListener('click',()=>selectHistoryCategory(button.dataset.historyCategory)));
  continuation.addEventListener('change',()=>{state.extended=continuation.checked;draw();buildTable();});
  slider.addEventListener('input',()=>{state.index=Number(slider.value)-1;updateMonth();});
  explorer.querySelectorAll('[data-history-step]').forEach(button=>button.addEventListener('click',()=>{state.index=Math.max(0,Math.min(records.length-1,state.index+Number(button.dataset.historyStep)));updateMonth();}));
  svg.addEventListener('keydown',event=>{
    const next={ArrowLeft:state.index-1,ArrowRight:state.index+1,Home:0,End:records.length-1}[event.key];
    if(next===undefined) return;
    event.preventDefault(); state.index=Math.max(0,Math.min(records.length-1,next));updateMonth();
  });
  svg.addEventListener('click',event=>{
    const rect=svg.getBoundingClientRect();
    const px=(event.clientX-rect.left)/rect.width*width;
    state.index=Math.max(0,Math.min(records.length-1,Math.round((px-left)/(right-left)*(records.length-1))));updateMonth();
  });
  document.getElementById('history-reset').addEventListener('click',()=>{state.index=59;state.extended=false;continuation.checked=false;selectHistoryCategory('Action');});
  window.addEventListener('hashchange',load);
  new ResizeObserver(()=>draw()).observe(explorer);
  document.fonts.ready.then(()=>draw());
  load();
})();

(() => {
  // Reflect held activation keys without changing native click or focus behavior.
  const controls = '.category-controls button,.month-step,.history-month-controls button,.timeline-reset,.menu-toggle,.nav-link,.pixel-button,.approach-controls input';
  document.addEventListener('keydown', event => {
    const target = event.target;
    if (![' ', 'Enter'].includes(event.key) || event.repeat || !target.matches(controls)) return;
    if (target.matches('a') && event.key !== 'Enter') return;
    if (target.matches('input[type="radio"]') && event.key !== ' ') return;
    (target.closest('.approach-controls label') || target).classList.add('key-held');
  });
  const release = () => document.querySelectorAll('.key-held').forEach(node => node.classList.remove('key-held'));
  document.addEventListener('keyup', release);
  document.addEventListener('focusout', release);
  window.addEventListener('blur', release);
})();


// Shared three-significant-figure formatter; T0007 extends this single entry point.
function formatStudyNumber(value) {
  const rounded = Number(value.toPrecision(3));
  const divisor = Math.abs(rounded) >= 1e6 ? 1e6 : Math.abs(rounded) >= 1e3 ? 1e3 : 1;
  const suffix = divisor === 1e6 ? 'M' : divisor === 1e3 ? 'K' : '';
  return (rounded / divisor).toPrecision(3) + suffix;
}

(async () => {
  const table = document.getElementById('overview-model-table');
  const status = document.getElementById('overview-model-status');
  const annual = JSON.parse(document.getElementById('study-data').textContent);
  const monthly = JSON.parse(document.getElementById('monthly-data').textContent);
  const policy = 'Provisional v2 policy';
  try {
    const responses = await Promise.all(['model-selection-evidence.json', 'history-data.json'].map(file => fetch('./assets/' + file)));
    if (responses.some(response => !response.ok)) throw new Error('Overview model evidence unavailable');
    const [selection, history] = await Promise.all(responses.map(response => response.json()));
    document.querySelector('.terminal-welcome').textContent = heroIntroCopy(history.observed);
    for (const category of ['Action', 'Strategy', 'RPG', 'Massively Multiplayer', 'Indie']) {
      const selected = selection.categories[category]?.selected_model || 'unknown';
      if (selected === 'unknown') console.warn('Selected model unknown:', category);
      const annualRow = annual.find(row => row.category === category && row.policy === policy);
      const row = table.tBodies[0].insertRow();
      for (const text of [category === 'Massively Multiplayer' ? 'MMO' : category, selected, formatStudyNumber(annualRow.projected_mean_activity)]) {
        row.insertCell().textContent = text;
      }
      if (selected === 'Last value') {
        const months = monthly.filter(record => record.category === category && record.policy === policy && record.month.startsWith('2027-'));
        const january = history.observed.find(record => record.category === category && record.month === '2026-01-01');
        if (new Set(months.map(record => record.month)).size === 12 && january && months.every(record => record.prediction === january.value)) {
          const note = document.createElement('small');
          note.textContent = 'Flat forecast: every 2027 month equals the January 2026 value.';
          row.cells[1].append(document.createElement('br'), note);
        } else {
          console.warn('Last-value flat forecast could not be confirmed:', category);
        }
      }
    }
    status.hidden = true;
  } catch (error) {
    status.textContent = 'The model details couldn’t load. Please try refreshing the page.';
    console.error(error);
  }
})();

// WAPE scores already average the two long-horizon fold metrics.
function annualNearTies(annual, policy, evidence) {
  const ordered = annual.filter(row => row.policy === policy).slice().sort((a, b) => b.projected_mean_activity - a.projected_mean_activity);
  const wape = row => {
    const category = evidence.categories[row.category];
    const model = policy === 'Last-value reference' ? 'Last value' : category?.selected_model;
    const score = category?.scores?.find(score => score.model === model && score.window === 'Leads 12 to 23');
    const value = score?.wape_pct == null || score.wape_pct === '' ? NaN : Number(score.wape_pct);
    return Number.isFinite(value) && value >= 0 ? value / 100 : null;
  };
  return ordered.slice(1).map((lower, index) => {
    const higher = ordered[index];
    const higherWape = wape(higher), lowerWape = wape(lower);
    const gap = (higher.projected_mean_activity - lower.projected_mean_activity) / lower.projected_mean_activity;
    return {higher: higher.category, lower: lower.category, gap, wapes: {[higher.category]: higherWape, [lower.category]: lowerWape}, nearTie: higherWape !== null && lowerWape !== null && gap < Math.max(higherWape, lowerWape)};
  });
}

// Preserve ranked order and break runs at every non-qualifying adjacent pair.
function nearTieRuns(pairs) {
  const runs = [];
  let current = null;
  for (const pair of pairs) {
    if (!pair.nearTie) {
      current = null;
    } else if (current && current[current.length - 1] === pair.higher) {
      current.push(pair.lower);
    } else {
      current = [pair.higher, pair.lower];
      runs.push(current);
    }
  }
  return runs;
}

function nearTieRunText(categories, label) {
  const names = categories.map(label);
  const joined = names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
  return categories.length === 2
    ? `Heads up: ${joined} are so close that their order could easily be noise.`
    : `Heads up: ${joined} are close enough that neighboring ranks could easily swap.`;
}

function renderNearTieCaveats(container, pairs, label) {
  const runs = nearTieRuns(pairs).map((categories, index) => ({categories, id: `${container.id}-run-${index + 1}`}));
  container.replaceChildren();
  for (const run of runs) {
    const paragraph = document.createElement('p');
    paragraph.id = run.id;
    paragraph.textContent = nearTieRunText(run.categories, label);
    container.append(paragraph);
  }
  container.hidden = runs.length === 0;
  return runs;
}

// Hero copy alone uses these data-derived duration and swap checks.
function heroIntroCopy(observed) {
  let duration = 'years of';
  if (Array.isArray(observed) && observed.length) {
    const months = [...new Set(observed.map(row => row.month))].sort();
    const ordinals = months.map(month => {
      const match = /^(\d{4})-(0[1-9]|1[0-2])-01$/.exec(month);
      return match ? Number(match[1]) * 12 + Number(match[2]) - 1 : NaN;
    });
    const categories = [...new Set(observed.map(row => row.category))];
    const complete = categories.every(category => new Set(observed.filter(row => row.category === category).map(row => row.month)).size === months.length);
    if (complete && ordinals.every(Number.isFinite) && ordinals[ordinals.length - 1] - ordinals[0] + 1 === months.length && months.length % 12 === 0) {
      const years = months.length / 12;
      const small = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
      const tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
      const words = n => n < 20 ? small[n] : n < 100 ? tens[Math.floor(n / 10)] + (n % 10 ? '-' + small[n % 10] : '') : n < 1000 ? words(Math.floor(n / 100)) + ' hundred' + (n % 100 ? ' ' + words(n % 100) : '') : words(Math.floor(n / 1000)) + ' thousand' + (n % 1000 ? ' ' + words(n % 1000) : '');
      duration = `${words(years)} ${years === 1 ? 'year' : 'years'} of`;
    }
  }
  return `Hello and welcome! I’ve been looking through ${duration} Steam activity to see where it might head next. Here’s my best guess for 2027.`;
}

function heroFindingCopy(annual) {
  const selected = category => annual.find(row => row.category === category && row.policy === 'Provisional v2 policy');
  const reference = category => annual.find(row => row.category === category && row.policy === 'Last-value reference');
  const indie = selected('Indie'), mmo = selected('Massively Multiplayer');
  const indieReference = reference('Indie'), mmoReference = reference('Massively Multiplayer');
  const swaps = indie && mmo && indieReference && mmoReference && (indie.projected_mean_activity - mmo.projected_mean_activity) * (indieReference.projected_mean_activity - mmoReference.projected_mean_activity) < 0;
  const label = category => category === 'Massively Multiplayer' ? 'MMO' : category;
  const swapSentence = swaps ? ` ${label(indie.category)} and ${label(mmo.category)} swap places depending on the approach, but they are very close.` : '';
  return `Action stays in front under both approaches, mostly because it starts so far ahead.${swapSentence} Shall we take a closer look?`;
}

// These aggregate WAPEs describe past individual monthly errors, not annual intervals.
function typicalErrorSummary(evidence, policy, categories) {
  const entries = categories.map(category => {
    const record = evidence.categories?.[category];
    const model = policy === 'Last-value reference' ? 'Last value' : record?.selected_model;
    const score = record?.scores?.find(row => row.window === 'Leads 12 to 23' && row.model === model);
    const wape = score?.wape_pct == null || score.wape_pct === '' ? NaN : Number(score.wape_pct);
    return {category, model, wape, window: score?.window};
  });
  const missing = entries.filter(row => !Number.isFinite(row.wape) || row.wape < 0).map(row => row.category);
  if (missing.length || !entries.length) return {missing: missing.length ? missing : categories, entries};
  const horizons = entries[0].window.match(/\d+/g);
  return {missing, entries, minimum: Math.min(...entries.map(row => row.wape)), maximum: Math.max(...entries.map(row => row.wape)), horizons};
}

function renderTypicalErrorNote(container, evidence, policy, categories) {
  const summary = typicalErrorSummary(evidence, policy, categories);
  container.replaceChildren();
  if (summary.missing.length || !summary.entries.length) {
    container.hidden = true;
    console.warn('Typical-error note omitted: long-horizon WAPE unavailable', policy, summary.missing);
    return;
  }
  const setup = policy === 'Last-value reference' ? 'the last-value reference was' : 'the selected models were';
  const note = document.createElement('p');
  note.textContent = `On past data, ${setup} typically off by about ${formatStudyNumber(summary.minimum)}% to ${formatStudyNumber(summary.maximum)}% on individual monthly forecasts ${summary.horizons[0]} to ${summary.horizons[1]} months ahead, so treat the numbers as rough, not exact.`;
  const limitation = document.createElement('p');
  limitation.textContent = "These figures come from two overlapping test periods, so they are a rough guide, not a guarantee. I haven't worked out an error range for the yearly averages.";
  container.append(note, limitation);
  container.hidden = false;
}

// Methods dates and counts come from the existing evidence and chart records.
function methodsCopyFromEvidence(evidence, history) {
  const {evaluation, policy} = evidence.saved_artifacts;
  const observedMonths = [...new Set(history.observed.map(row => row.month))].sort();
  const forecastMonths = [...new Set(history.forecast.map(row => row.month))].sort();
  const origins = [...evaluation.origins].sort();
  const leads = [...evaluation.target_leads].sort((a, b) => a - b);
  const monthName = value => new Date(value + 'T00:00:00Z').toLocaleDateString('en-US', {month: 'long', year: 'numeric', timeZone: 'UTC'});
  const addMonths = (value, offset) => {
    const date = new Date(value + 'T00:00:00Z');
    return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + offset, 1)).toISOString().slice(0, 10);
  };
  const targets = origins.flatMap(origin => Array.from({length: leads[leads.length - 1] - leads[0] + 1}, (_, index) => addMonths(origin, leads[0] + index))).sort();
  const originNames = origins.map(monthName).join(' and ');
  const earlyYear = origins.length === 2 && origins.every(origin => new Date(origin + 'T00:00:00Z').getUTCMonth() < 3);
  const seasonalLimit = earlyYear ? ' Both starts are near the beginning of the year, so this check does not cover starts in other seasons.' : '';
  return {
    sources: 'I used monthly activity histories from the lunthu Kaggle dataset and the Aanomali and Liu research repositories. I also used a snapshot from Aakash-1107\'s Game Market Intelligence project and a small SteamCharts collection. Where sources overlap, I keep one compatible value for each game and month.',
    cohort: `I kept ${policy.cohort_apps} games with usable metadata and at least one selected category label. Each has an observation for every month from ${monthName(observedMonths[0])} through ${monthName(observedMonths[observedMonths.length - 1])}.`,
    evaluation: `I checked forecasts starting in ${originNames}. Their test months overlap, so this is a development check rather than a fresh test on untouched data.`,
    projection: `I used observations through ${monthName(policy.cutoff)} to make ${policy.horizon} provisional monthly forecasts, from ${monthName(forecastMonths[0])} through ${monthName(forecastMonths[forecastMonths.length - 1])}.`,
    activity: 'For each game, average concurrent activity is the average number of players active at the same time during a month. I add those monthly averages across the games in each category. That measures activity, not different people, sales or revenue.',
    overlap: 'One game can belong to more than one category. I include its activity in each one, so the categories overlap. Their totals aren’t separate Steam market shares.',
    retrospective: 'I chose the cohort and labels using information available later. I also used these test results to choose models, so they are not an independent holdout.',
    forecastLimits: 'The historical error ranges are a rough guide, not a promise about where future values will fall. I haven’t worked out ranking probabilities or an error range for yearly averages.',
    inclusion: `Each game has all ${observedMonths.length} monthly observations in the common window. I did not fill missing observations with zero.`,
    labels: 'A game’s activity goes into every selected category attached to it. The labels come from a later metadata snapshot, so they are not a record of how labels changed over time.',
    selectionLimit: 'Choosing games with a complete history favours the ones observed consistently. The inclusion checks do not show that this cohort represents all of Steam.',
    evaluationDetail: `I checked forecasts from ${originNames}, looking ${leads[0]} to ${leads[leads.length - 1]} months ahead. All the months checked at that distance fall between ${monthName(targets[0])} and ${monthName(targets[targets.length - 1])}.`,
    evaluationLimit: `The test months overlap.${seasonalLimit} I did not keep a separate set of months aside for an independent holdout. These checks helped me choose the models, so they do not prove which model will forecast best in the future.`,
    rangeLimit: 'The test periods overlap, so these ranges are a rough guide rather than a guarantee. They do not tell us how often future values will fall inside them, and I haven’t worked out an error range for yearly averages.'
  };
}

(async () => {
  try {
    const responses = await Promise.all(['methods-evidence.json', 'history-data.json'].map(file => fetch('./assets/' + file)));
    if (responses.some(response => !response.ok)) throw new Error('Methods evidence unavailable');
    const [evidence, history] = await Promise.all(responses.map(response => response.json()));
    const copy = methodsCopyFromEvidence(evidence, history);
    document.querySelectorAll('[data-methods-copy]').forEach(element => { element.textContent = copy[element.dataset.methodsCopy]; });
  } catch (error) {
    console.warn(error);
  }
})();
