/* ══════════════════════════════════════════════════════════════════════════
   裸K战法终端 · 前端交互层
   后端: /api/*  (FastAPI, engine/analyzer.py 五模块规则引擎)
   图表: lightweight-charts v4 (TradingView) — 蜡烛 + 关键价位标注
   ══════════════════════════════════════════════════════════════════════════ */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const state = {
  report: null,
  bars: [],
  levels: [],
  hidden: new Set(),
  chart: null,
  candle: null,
  vol: null,
  priceLines: [],
  addMode: false,
  acIndex: -1,
  acItems: [],
  watchQuery: null,
};

/* ───────────────────────── 工具 ───────────────────────── */

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const fx = (v, n = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(n);

const sgn = (v, n = 2) => (v > 0 ? '+' : '') + fx(v, n);

function toneOf(v) { return v > 0 ? 'up' : v < 0 ? 'down' : 'flat'; }

const ICON = (id, cls = 'h-3.5 w-3.5') =>
  `<svg class="${cls}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><use href="#i-${id}"/></svg>`;

const TONE_BADGE = { good: 'badge-bull', bad: 'badge-bear', warn: 'badge-warn' };

function hexA(hex, a) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/* ───────────────────────── API ───────────────────────── */

async function api(path, opts) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

/* ───────────────────────── 错误横幅 ───────────────────────── */

let errTimer = null;
function showError(msg) {
  const b = $('#err-banner');
  $('#err-msg').textContent = msg;
  b.classList.remove('hidden');
  clearTimeout(errTimer);
  errTimer = setTimeout(() => b.classList.add('hidden'), 9000);
}

/* ───────────────────────── 自选股 ───────────────────────── */

async function loadWatchlist() {
  const ul = $('#watchlist');
  try {
    const { items } = await api('/api/watchlist');
    $('#wl-count').textContent = items.length;
    if (!items.length) {
      ul.innerHTML = `<li class="px-4 py-8 text-center text-xs text-dim">暂无自选股<br><span class="mt-1 block">点右上 + 添加</span></li>`;
      return;
    }
    ul.innerHTML = items.map((it) => {
      const q = it.quote || {};
      const t = toneOf(q.chg_pct);
      const active = state.report && state.report.symbol === it.symbol;
      return `<li class="wl-item" data-active="${active ? 1 : 0}" data-q="${esc(it.query)}" data-sym="${esc(it.symbol || '')}" tabindex="0">
        <div class="min-w-0 flex-1">
          <div class="truncate text-[13px] text-ink">${esc(it.name || it.query)}</div>
          <div class="num mt-0.5 text-[10.5px] text-dim">${esc(it.code || it.symbol || '')}</div>
        </div>
        <div class="text-right shrink-0">
          <div class="num text-[13px] v-${t}">${fx(q.last)}</div>
          <div class="num text-[10.5px] v-${t}">${q.chg_pct === undefined ? '' : sgn(q.chg_pct) + '%'}</div>
        </div>
        <button class="wl-del icon-btn h-6 w-6 border-0 bg-transparent" data-del="${esc(it.query)}" title="移出自选">${ICON('x', 'h-3 w-3')}</button>
      </li>`;
    }).join('');
  } catch (e) {
    ul.innerHTML = `<li class="px-4 py-6 text-center text-xs text-dim">自选股加载失败<br>${esc(e.message)}</li>`;
  }
}

/* ───────────────────────── 搜索联想 ───────────────────────── */

let acTimer = null;
let acSeq = 0;

function closeAc() {
  $('#ac').classList.add('hidden');
  state.acIndex = -1;
}

async function doSearch(q) {
  if (!q.trim()) return closeAc();
  const seq = ++acSeq;
  let results = [];
  try { ({ results } = await api('/api/search?q=' + encodeURIComponent(q))); } catch { return; }
  if (seq !== acSeq) return;
  state.acItems = results;
  state.acIndex = -1;
  const box = $('#ac');
  if (!results.length) {
    box.innerHTML = `<div class="px-3 py-3 text-xs text-dim">无匹配结果</div>`;
  } else {
    box.innerHTML = results.map((r, i) => `<div class="ac-item" data-i="${i}" role="option">
        <span class="ac-name">${esc(r.name)}</span>
        <span class="ac-code">${esc(r.code)}</span>
        <span class="ac-kind">${esc(r.kind)}</span>
      </div>`).join('');
  }
  box.classList.remove('hidden');
}

/* ───────────────────────── 主流程 ───────────────────────── */

async function analyze(query) {
  if (!query) return;
  $('#empty').classList.add('hidden');
  $('#report').classList.add('hidden');
  $('#loading').classList.remove('hidden');
  try {
    const rep = await api('/api/analyze?q=' + encodeURIComponent(query));
    state.report = rep;
    state.bars = rep.bars;
    state.levels = rep.chart_levels;
    localStorage.setItem('nakedk.last', rep.symbol);
    // 必须先让容器可见再挂载图表：display:none 下容器尺寸为 0，
    // lightweight-charts 会创建 0×0 canvas 并且不会自愈。
    $('#report').classList.remove('hidden');
    render(rep);
    $$('#watchlist .wl-item').forEach((li) =>
      li.dataset.active = (li.dataset.sym === rep.symbol) ? '1' : '0');
  } catch (e) {
    showError('分析失败：' + e.message);
    if (!state.report) $('#empty').classList.remove('hidden');
    else $('#report').classList.remove('hidden');
  } finally {
    $('#loading').classList.add('hidden');
  }
}

/* ───────────────────────── 渲染 ───────────────────────── */

function render(rep) {
  $('#report').innerHTML = [
    headCard(rep),
    chartCard(rep),
    `<div class="grid gap-4 lg:grid-cols-2">${m1(rep)}${m2(rep)}</div>`,
    `<div class="grid gap-4 lg:grid-cols-2">${m3(rep)}${m4(rep)}</div>`,
    `<div class="grid gap-4 lg:grid-cols-2">${m6(rep)}${sideCard(rep)}</div>`,
  ].join('');
  mountChart(rep);
  bindChartControls();
  bindAltChips();
}

/* ── 标头 ── */
function headCard(rep) {
  const m1 = rep.m1_kline, m2 = rep.m2_context, o = m1.ohcl;
  const last = o.close;
  const t = toneOf(m1.chg_pct);
  const id = rep.intraday && rep.intraday.available ? rep.intraday : null;
  return `<div class="panel px-4 py-4 sm:px-5">
    <div class="flex flex-wrap items-start gap-x-6 gap-y-4">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="text-lg font-600 tracking-tight text-ink">${esc(rep.name)}</h1>
          <span class="num text-xs text-muted">${esc(rep.code)}</span>
          <span class="badge badge-mute">${esc(rep.kind || '')}</span>
          ${rep.is_intraday ? '<span class="badge badge-warn">盘中·未收盘</span>' : ''}
        </div>
        <div class="mt-1.5 flex items-center gap-2 text-[11px] text-dim">
          ${ICON('clock', 'h-3 w-3')}<span class="num">${esc(rep.date)}</span>
          <span class="text-lineSoft">·</span><span>${rep.bar_count} 根日K</span>
          <span class="text-lineSoft">·</span><span>源 ${esc(rep.source)}</span>
        </div>
      </div>

      <div class="flex items-end gap-3">
        <span class="num text-3xl font-600 leading-none v-${t}">${fx(last)}</span>
        <span class="num pb-0.5 text-sm v-${t}">${sgn(m1.chg_pct)}%</span>
      </div>

      <dl class="ml-auto flex flex-wrap gap-x-5 gap-y-2">
        ${[['开', o.open], ['高', o.high], ['低', o.low], ['收', o.close]].map(([k, v]) => {
          return `<div><dt class="text-[10px] text-dim">${k}</dt>
            <dd class="num text-[13px] v-${toneOf(v - o.open)}">${fx(v)}</dd></div>`;
        }).join('')}
        <div><dt class="text-[10px] text-dim">实体</dt><dd class="num text-[13px] text-ink">${m1.entity_pct}%</dd></div>
        <div><dt class="text-[10px] text-dim">阶段</dt><dd class="text-[13px] text-ink">${esc(m2.stage)}</dd></div>
        <div><dt class="text-[10px] text-dim">趋势</dt><dd class="text-[13px] text-ink">${esc(m2.trend)}</dd></div>
      </dl>
    </div>

    ${(rep.alternatives && rep.alternatives.length) ? `<div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-dim">
      <span>${esc(rep.code)} 也可指：</span>
      ${rep.alternatives.map((a) => `<button class="alt-chip" data-q="${esc(a.code)}" data-sym="${esc(a.symbol)}" title="${esc(a.kind)}">
        ${esc(a.name)}<span class="ml-1 opacity-60">${esc(a.symbol.toUpperCase())}</span></button>`).join('')}
    </div>` : ''}

    ${id ? `<div class="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-playA/30 bg-playA/8 px-3 py-2 text-[11.5px] text-playA">
      ${ICON('zap', 'h-3.5 w-3.5')}模块五 · ${esc(id.note)}
      <span class="ml-auto num text-dim">快照 ${esc(id.intraday.time || '')}</span></div>` : ''}
  </div>`;
}

/* ── 图表 ── */
function chartCard(rep) {
  const legend = state.levels.map((l) => {
    const price = l.kind === 'band' ? `${fx(l.bottom)}~${fx(l.top)}` : fx(l.price);
    return `<button class="legend" data-key="${l.key}" data-off="0" title="${esc(l.note)}">
      <span class="swatch" style="background:${l.color}"></span>
      <span>${esc(l.label)}</span><span class="num text-dim">${price}</span></button>`;
  }).join('');

  const ranges = [[60, '60'], [90, '90'], [180, '180'], [0, '全部']];
  return `<div class="panel" id="chart-wrap">
    <div class="panel-head">
      <span class="panel-title">${ICON('candle', 'h-3.5 w-3.5 text-accent')}KLINE · 纯价格行为</span>
      <span class="badge badge-mute">${state.bars.length} 根</span>
      <div class="ml-auto flex items-center gap-1" role="group" aria-label="显示K线根数">
        ${ranges.map(([n, label]) => `<button class="rng-btn" data-n="${n}" data-on="${n === 90 ? 1 : 0}">${label}</button>`).join('')}
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-1.5 border-b border-lineSoft px-4 py-2">
      <span class="mr-1 text-[10px] tracking-[0.12em] text-dim">价位标注</span>${legend}
    </div>
    <div class="relative">
      <div id="chart"></div>
      <div id="bands"></div>
      <div id="ladder"></div>
    </div>
  </div>`;
}

const LINE_STYLE = { solid: 0, dotted: 1, dashed: 2, large_dashed: 3, sparse_dotted: 4 };

/* lightweight-charts 的默认刻度会月/日混排（6月 → 12日），统一成 MM/DD。 */
function fmtTick(t, full = false) {
  let d;
  if (typeof t === 'string') d = new Date(t + 'T00:00:00');
  else if (t && typeof t === 'object' && t.year !== undefined) d = new Date(t.year, t.month - 1, t.day);
  else d = new Date(t * 1000);
  if (Number.isNaN(d.getTime())) return String(t);
  const p2 = (n) => String(n).padStart(2, '0');
  return full ? `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}` : `${d.getMonth() + 1}/${d.getDate()}`;
}

function mountChart(rep) {
  const el = $('#chart');
  if (!el) return;
  if (!el.clientWidth || !el.clientHeight) {
    requestAnimationFrame(() => mountChart(rep));
    return;
  }
  if (state.chart) { try { state.chart.remove(); } catch (e) {} state.chart = null; }

  const C = {
    layout: {
      background: { type: 'solid', color: 'transparent' },
      textColor: '#94A3B8',
      fontFamily: '"Fira Code", ui-monospace, monospace',
      fontSize: 11,
    },
    grid: { vertLines: { color: 'rgba(30,41,59,.85)' }, horzLines: { color: 'rgba(30,41,59,.85)' } },
    rightPriceScale: { borderColor: '#334155', scaleMargins: { top: 0.08, bottom: 0.24 } },
    timeScale: {
      borderColor: '#334155', rightOffset: 6, barSpacing: 7, fixLeftEdge: true,
      tickMarkFormatter: (t) => fmtTick(t),
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: 'rgba(148,163,184,.5)', width: 1, style: 2, labelBackgroundColor: '#1E293B' },
      horzLine: { color: 'rgba(148,163,184,.5)', width: 1, style: 2, labelBackgroundColor: '#1E293B' },
    },
    handleScale: { axisPressedMouseMove: { time: true, price: false } },
    localization: {
      locale: 'zh-CN',
      priceFormatter: (p) => p.toFixed(2),
      timeFormatter: (t) => fmtTick(t, true),
    },
  };

  state.chart = LightweightCharts.createChart(el, C);

  state.candle = state.chart.addCandlestickSeries({
    upColor: '#F6465D', downColor: '#0ECB81',
    borderUpColor: '#F6465D', borderDownColor: '#0ECB81',
    wickUpColor: 'rgba(246,70,93,.75)', wickDownColor: 'rgba(14,203,129,.75)',
    priceLineVisible: false, lastValueVisible: true,
  });
  state.candle.setData(state.bars.map((b) => ({
    time: b.date, open: b.open, high: b.high, low: b.low, close: b.close,
  })));

  state.vol = state.chart.addHistogramSeries({
    priceScaleId: 'vol', priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'volume' },
  });
  state.vol.setData(state.bars.map((b) => ({
    time: b.date, value: b.vol,
    color: b.close >= b.open ? 'rgba(246,70,93,.32)' : 'rgba(14,203,129,.32)',
  })));
  state.chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

  // 标记：冰线来源K线 / 上轮分析日 / 今日
  const marks = [];
  const ice = rep.levels.ice;
  if (ice.date && state.bars.some((b) => b.date === ice.date)) {
    marks.push({ time: ice.date, position: ice.role === 'resistance' ? 'aboveBar' : 'belowBar',
      color: '#38BDF8', shape: 'circle', text: '冰', size: 0 });
  }
  const v = rep.verification;
  if (v && v.prev_date && state.bars.some((b) => b.date === v.prev_date)) {
    marks.push({ time: v.prev_date, position: 'aboveBar', color: '#A78BFA', shape: 'square', text: '验', size: 0 });
  }
  marks.push({ time: rep.date, position: 'aboveBar', color: '#38BDF8', shape: 'circle', text: '今', size: 0 });
  state.candle.setMarkers(marks.sort((a, b) => (a.time < b.time ? -1 : 1)));

  applyLevels();
  setRange(90);
  state.chart.timeScale().subscribeVisibleLogicalRangeChange(drawBands);
  state.chart.subscribeCrosshairMove((p) => { if (!p.time) return; });
  if (state.ro) { try { state.ro.disconnect(); } catch (e) {} }
  state.ro = new ResizeObserver(() => drawBands());
  state.ro.observe(el);
  setTimeout(drawBands, 60);
}

function applyLevels() {
  if (!state.candle) return;
  state.priceLines.forEach((pl) => { try { state.candle.removePriceLine(pl); } catch (e) {} });
  state.priceLines = [];

  state.levels.forEach((l) => {
    if (state.hidden.has(l.key)) return;
    // 原生轴标签在 A 股密集价位下必然叠字，统一交给受控价位梯（drawLadder）。
    const mk = (price, lineVisible) => {
      state.priceLines.push(state.candle.createPriceLine({
        price, color: l.color, lineWidth: 1,
        lineStyle: LINE_STYLE[l.style || 'solid'] ?? 2,
        axisLabelVisible: false, title: '', lineVisible,
      }));
    };
    if (l.kind === 'line') mk(l.price, true);
    else { mk(l.top, false); mk(l.bottom, false); }
  });
  drawBands();
}

/* 受控价位梯：默认右轴标签会互相压字（15.20 / 15.21 只差 0.7px），
   这里自己按像素位置做去重叠（最小间距 15px）后再渲染。 */
function drawLadder() {
  const ladder = $('#ladder');
  if (!ladder || !state.candle) return;
  ladder.innerHTML = '';
  const h = ladder.clientHeight;
  const items = state.levels
    .filter((l) => l.kind === 'line' && !state.hidden.has(l.key))
    .map((l) => ({ l, y: state.candle.priceToCoordinate(l.price) }))
    .filter((it) => it.y !== null && it.y > -6 && it.y < h + 6)
    .sort((a, b) => a.y - b.y);

  const MIN = 15;
  let last = -1e9;
  items.forEach((it) => {
    let y = it.y;
    if (y - last < MIN) y = last + MIN;
    last = y;
    const anchor = Math.abs(y - it.y) > 0.5;
    const d = document.createElement('div');
    d.className = 'lv-tick';
    d.style.top = Math.min(y, h - 8) + 'px';
    d.innerHTML = `<i style="background:${it.l.color}"></i>`
      + `<span class="lv-name">${esc(it.l.label)}</span>`
      + `<b style="color:${it.l.color}">${fx(it.l.price)}</b>`
      + (anchor ? `<u style="background:${it.l.color}"></u>` : '');
    ladder.appendChild(d);
  });
}

function drawBands() {
  const layer = $('#bands');
  if (!layer || !state.candle) return;
  layer.innerHTML = '';
  // 标注层 = 区间带 + 价位梯，每次一起重画
  if (!layer.dataset.split) { layer.dataset.split = '1'; }
  const h = layer.clientHeight;
  state.levels.filter((l) => l.kind === 'band' && !state.hidden.has(l.key)).forEach((l) => {
    let yT = state.candle.priceToCoordinate(l.top);
    let yB = state.candle.priceToCoordinate(l.bottom);
    if (yT === null || yB === null) return;
    const pxT = Math.max(-2, Math.min(h + 2, yT));
    const pxB = Math.max(-2, Math.min(h + 2, yB));
    const top = Math.min(pxT, pxB);
    const height = Math.max(1, Math.abs(pxB - pxT));
    const d = document.createElement('div');
    d.className = 'zone-band';
    d.style.top = top + 'px';
    d.style.height = height + 'px';
    d.style.background = hexA(l.color, 0.09);
    d.style.borderTopColor = hexA(l.color, 0.45);
    d.style.borderBottomColor = hexA(l.color, 0.45);
    d.innerHTML = `<span style="color:${l.color}">${esc(l.label)} ${fx(l.bottom)}–${fx(l.top)}</span>`;
    layer.appendChild(d);
  });
  drawLadder();
}

function setRange(n) {
  if (!state.chart) return;
  const len = state.bars.length;
  if (!n || n >= len) { state.chart.timeScale().fitContent(); }
  else { state.chart.timeScale().setVisibleLogicalRange({ from: len - n, to: len + 6 }); }
  state.range = n;
  $$('.rng-btn').forEach((b) => b.dataset.on = (+b.dataset.n === n) ? '1' : '0');
  setTimeout(drawBands, 30);
}

function bindAltChips() {
  $$('.alt-chip').forEach((b) => {
    b.addEventListener('click', () => analyze(b.dataset.sym || b.dataset.q));
  });
}

function bindChartControls() {
  $$('.rng-btn').forEach((b) => {
    b.addEventListener('click', () => setRange(+b.dataset.n));
  });
  $$('.legend').forEach((b) => {
    b.addEventListener('click', () => {
      const k = b.dataset.key;
      const off = state.hidden.has(k);
      if (off) state.hidden.delete(k); else state.hidden.add(k);
      b.dataset.off = off ? '0' : '1';
      applyLevels();
    });
  });
}

/* ── 模块一：K线解剖 ── */
function m1(rep) {
  const d = rep.m1_kline;
  const H = 62;
  const hUp = Math.round(d.shadow.upper_pct / 100 * H);
  const hEn = Math.max(2, Math.round(d.entity_pct / 100 * H));
  const hLo = Math.max(0, H - hUp - hEn);
  const bull = d.ohcl.close >= d.ohcl.open;
  return card(1, 'K线解剖', `<span class="badge ${TONE_BADGE[d.close_pos.tone] || ''}">${esc(d.close_pos.class)} ${d.close_pos.pct}%</span>`,
    `<div class="p-4">
      <div class="flex items-start gap-5">
        <div class="shrink-0">
          <div class="anatomy">
            <i style="height:${hUp}px;background:${bull ? 'var(--up)' : 'var(--down)'}"></i>
            <b style="height:${hEn}px;background:${bull ? 'var(--up)' : 'var(--down)'}"></b>
            ${hLo ? `<i style="height:${hLo}px;background:${bull ? 'var(--up)' : 'var(--down)'}"></i>` : ''}
          </div>
          <div class="mt-2 text-center"><span class="badge ${bull ? 'badge-bull' : 'badge-bear'}">${esc(d.entity_class)}</span></div>
        </div>
        <div class="min-w-0 flex-1">
          <div class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
            ${mini('实体占比', d.entity_pct + '%', '')}
            ${mini('上影线', d.shadow.upper_pct + '%', d.shadow.upper_meaning)}
            ${mini('下影线', d.shadow.lower_pct + '%', d.shadow.lower_meaning)}
            ${mini('跳空', sgn(d.gap.pct) + '%', d.gap.class)}
          </div>
          <div class="mt-3 flex items-start gap-2 rounded-lg border border-lineSoft bg-surface2/40 px-3 py-2">
            <span class="mt-0.5 shrink-0 text-accent">${ICON('crosshair', 'h-3.5 w-3.5')}</span>
            <p class="text-[12.5px] leading-relaxed text-muted">${esc(d.narration)}</p>
          </div>
        </div>
      </div>
    </div>`);
}

/* ── 模块二：背景定位 ── */
function m2(rep) {
  const d = rep.m2_context;
  const bgTone = { tolerant: 'badge-bull', alert: 'badge-bear', neutral: 'badge-mute' }[d.background_kind];
  return card(2, '背景定位',
    `<span class="badge badge-info">${esc(d.kline_quality)}</span>`,
    `<div class="p-4 space-y-4">
      <div>
        <div class="mb-2 flex items-baseline justify-between">
          <span class="text-[11px] text-dim">60日位置</span>
          <span class="num text-[12.5px] text-ink">${d.p60_pct}% <span class="text-dim">· ${esc(d.stage)}</span></span>
        </div>
        <div class="gauge"><i style="width:${d.p60_pct}%"></i><u style="left:${d.p60_pct}%"></u></div>
        <div class="mt-1.5 flex justify-between text-[10px] text-dim num">
          <span>低 ${fx(d.range60.low)}</span><span>高 ${fx(d.range60.high)}</span>
        </div>
      </div>
      <dl class="kv">
        <dt>趋势判定</dt><dd><span class="badge ${d.trend === '上升趋势' ? 'badge-bull' : d.trend === '下跌趋势' ? 'badge-bear' : 'badge-mute'}">${esc(d.trend)}</span>
          <span class="num ml-2 text-[11px] text-dim">近5/远5 均价比 ${d.trend_ratio}</span></dd>
        <dt>K线定性</dt><dd>${esc(d.kline_quality)}${d.is_engulfing ? ' <span class="badge badge-bear">多头陷阱</span>' : ''}</dd>
        <dt>20日区间</dt><dd class="num">${fx(d.prev20.low)} ~ ${fx(d.prev20.high)}</dd>
        <dt>背景修正</dt><dd><span class="badge ${bgTone}">${esc(d.background_note)}</span></dd>
      </dl>
    </div>`);
}

/* ── 模块三：关键价位 ── */
function m3(rep) {
  const L = rep.levels, ice = L.ice, s = L.supply, dm = L.demand;
  const priceRow = (color, name, price, dist, extra, note) => `
    <div class="rowline">
      <span class="h-2 w-2 shrink-0 rounded-sm" style="background:${color}"></span>
      <span class="w-14 shrink-0 text-[12px] text-muted">${name}</span>
      <span class="num text-[15px] text-ink">${fx(price)}</span>
      <span class="num text-[11px] ${dist > 0 ? 'v-up' : dist < 0 ? 'v-down' : 'v-flat'}">${dist === undefined ? '' : sgn(dist) + '%'}</span>
      <span class="ml-auto shrink-0">${extra}</span>
    </div>
    ${note ? `<p class="pb-2 pl-[3.1rem] text-[11px] leading-relaxed ${note.warn ? 'text-playA' : 'text-dim'}">${note.text}</p>` : ''}`;

  return card(3, '关键价位',
    `<span class="badge badge-mute">冰线优先级 P${ice.priority}</span>`,
    `<div class="p-4 pt-3">
      ${priceRow('var(--ice)', '冰线', ice.price, ice.deviation_pct,
        `<span class="badge ${ice.role === 'resistance' ? 'badge-bear' : 'badge-info'}">${ice.role === 'resistance' ? '阻力' : ice.role === 'far_support' ? '偏离过大' : '支撑'}</span>`,
        { text: `${esc(ice.source)} · ${esc(ice.detail)}${ice.note ? ' · ' + esc(ice.note) : ''}`, warn: !!ice.note })}

      ${priceRow('var(--supply)', '供应区', s.bottom, s.distance_pct,
        `<span class="badge ${s.strength.startsWith('强') ? 'badge-bear' : 'badge-mute'}">${esc(s.strength)}</span>`,
        { text: `上沿 ${fx(s.top)} · 跨度 ${s.width_pct}% · 12根内局部高点 ${s.local_peaks} 个${s.in_zone ? ' · <span class="text-playA">现价位于区内</span>' : ''}`, warn: s.in_zone })}

      ${priceRow('var(--demand)', '需求区', dm.top, dm.distance_pct,
        `<span class="badge ${dm.strength.startsWith('强') ? 'badge-bull' : 'badge-mute'}">${esc(dm.strength)}</span>`,
        { text: `下沿 ${fx(dm.bottom)} · 跨度 ${dm.width_pct}% · 12根内局部低点 ${dm.local_peaks} 个${dm.in_zone ? ' · <span class="text-playA">现价位于区内</span>' : ''}`, warn: dm.in_zone })}
    </div>`);
}

/* ── 模块四：次日验证剧本 ── */
function m4(rep) {
  const p = rep.playbook, sc = p.scenarios;
  const toneCls = { A: 'badge-bull', B: 'badge-mute', C: 'badge-bear' };
  const bar = `<div class="prob-track">
      <div class="prob-a" style="flex-basis:${sc.A.prob}%">A ${sc.A.prob}%</div>
      <div class="prob-b" style="flex-basis:${sc.B.prob}%">B ${sc.B.prob}%</div>
      <div class="prob-c" style="flex-basis:${sc.C.prob}%">C ${sc.C.prob}%</div>
    </div>`;

  const srow = (k) => {
    const s = sc[k];
    const trig = k === 'B' ? `${fx(s.low)} ~ ${fx(s.high)}` : fx(s.trigger);
    return `<div class="rowline">
      <span class="badge ${toneCls[k]} w-6 justify-center">${k}</span>
      <span class="num text-[14px] text-ink">${trig}</span>
      <span class="text-[12px] text-muted">${esc(s.label)}</span>
      <span class="num ml-auto text-[11px] text-dim">${s.prob}%</span>
    </div>`;
  };

  return card(4, '次日验证剧本',
    `<span class="badge ${toneCls[p.dominant]}">${p.tie ? '并列最高 ' + p.tied.join('/') : '主剧本 ' + p.dominant} · ${esc(sc[p.dominant].label)}</span>${p.tie ? '<span class="badge badge-warn">无单一主剧本</span>' : ''}${p.polarized ? '<span class="badge badge-warn">边界极性化</span>' : ''}`,
    `<div class="p-4 pt-3 space-y-3">
      ${bar}
      <div>
        ${srow('A')}${srow('B')}${srow('C')}
      </div>
      <div class="flex items-start gap-2 rounded-lg border border-stop/30 bg-stop/8 px-3 py-2.5">
        <span class="mt-0.5 shrink-0 text-stop">${ICON('play', 'h-3.5 w-3.5')}</span>
        <div>
          <div class="text-[11px] tracking-wide text-stop">止损反推 · ${fx(p.stop_loss)}</div>
          <p class="mt-1 text-[11.5px] leading-relaxed text-muted">${esc(p.stop_note)}</p>
        </div>
      </div>
      ${p.corrections.length ? `<ul class="space-y-1 pl-1 text-[11px] text-dim">
        ${p.corrections.map((c) => `<li class="flex gap-1.5"><span class="text-lineSoft">·</span>${esc(c)}</li>`).join('')}
      </ul>` : ''}
    </div>`);
}

/* ── 模块六：事后验证 ── */
function m6(rep) {
  const v = rep.verification;
  if (!v) {
    return card(6, '事后验证',
      `<span class="badge badge-mute">无历史</span>`,
      `<div class="px-4 py-8 text-center">
        <p class="text-[12.5px] text-muted">该标的尚无更早的分析记录</p>
        <p class="mt-1.5 text-[11px] leading-relaxed text-dim">每次分析会自动落盘到 ~/.nakedk/history/。下次分析同一标的时，<br>这里会用真实后续K线回测本轮剧本是否兑现。</p>
      </div>`);
  }
  const hit = v.verdict === '命中';
  const drift = v.drift || {};
  return card(6, '事后验证',
    `<span class="badge ${hit ? 'badge-bull' : 'badge-warn'}">${esc(v.verdict)}</span>`,
    `<div class="p-4 pt-3 space-y-3">
      <div class="flex items-center gap-3 rounded-lg border border-lineSoft bg-surface2/40 px-3 py-2.5">
        <span class="num text-[12px] text-dim">${esc(v.prev_date)}</span>
        <span class="badge ${v.prev_dominant === 'A' ? 'badge-bull' : v.prev_dominant === 'C' ? 'badge-bear' : 'badge-mute'}">预测 ${v.prev_dominant}</span>
        <span class="text-dim">${ICON('x', 'h-3 w-3')}</span>
        <span class="badge ${v.actual_scenario === 'A' ? 'badge-bull' : v.actual_scenario === 'C' ? 'badge-bear' : 'badge-mute'}">实际 ${v.actual_scenario}</span>
        <span class="num ml-auto text-[11px] text-dim">${v.days_elapsed} 个交易日后</span>
      </div>
      <dl class="kv">
        <dt>A 触发日</dt><dd class="num">${esc(v.first_hit_dates.A || '期内未触发')}</dd>
        <dt>C 触发日</dt><dd class="num">${esc(v.first_hit_dates.C || '期内未触发')}</dd>
        ${drift.ice_old !== undefined ? `<dt>上轮冰线</dt>
          <dd class="num">${fx(drift.ice_old)} <span class="badge ${drift.ice_broken ? 'badge-bear' : 'badge-bull'}">${esc(drift.ice_label || (drift.ice_broken ? '已破' : '未破'))}</span>
            <span class="ml-1 text-[10px] text-dim">${drift.ice_broken && drift.ice_break_date ? esc(drift.ice_break_date) : (drift.ice_role === 'resistance' ? '原为阻力' : '原为支撑')}</span></dd>` : ''}
        ${drift.supply_touched !== undefined ? `<dt>供应区</dt>
          <dd>${drift.supply_touched ? '<span class="badge badge-warn">已触及</span>' : '<span class="badge badge-mute">未触及</span>'}${drift.supply_upgraded ? ' <span class="badge badge-bull">已被收盘突破</span>' : ''}</dd>` : ''}
      </dl>
    </div>`);
}

/* ── 侧卡：警告 + 引擎 ── */
function sideCard(rep) {
  const w = rep.warnings || [];
  const tick = (rep.verification?.tick) || null;
  return card('i', '引擎自检与警告',
    `<span class="badge ${w.length ? 'badge-warn' : 'badge-bull'}">${w.length ? w.length + ' 条' : '全部通过'}</span>`,
    `<div class="p-4 pt-3">
      ${w.length ? `<ul class="space-y-2">${w.map((x) => `<li class="flex items-start gap-2 text-[11.5px] leading-relaxed text-playA">
          <span class="mt-0.5 shrink-0">${ICON('alert', 'h-3.5 w-3.5')}</span><span>${esc(x)}</span></li>`).join('')}</ul>`
        : `<p class="text-[12px] text-muted">无异常。冰线优先级 P${rep.levels.ice.priority}，偏离 ${rep.levels.ice.deviation_pct}%，供应/需求区跨度均在阈值内。</p>`}
      <dl class="kv mt-4 border-t border-lineSoft pt-3">
        <dt>引擎版本</dt><dd class="num">v${esc(rep.engine_version)}</dd>
        <dt>分析ID</dt><dd class="num text-[11px] text-dim">${esc(rep.id)}</dd>
        <dt>K线数据源</dt><dd>${esc(rep.source === 'tencent' ? '腾讯财经（前复权）' : 'TickFlow（备源）')}</dd>
        <dt>数据基数</dt><dd class="num">${rep.bar_count} 根日K</dd>
      </dl>
    </div>`);
}

/* ── 通用面板外壳 ── */
function card(idx, title, right, body) {
  return `<section class="panel">
    <div class="panel-head">
      <span class="panel-title"><span class="mod-idx">${idx}</span>${esc(title)}</span>
      <span class="ml-auto flex flex-wrap items-center gap-1.5">${right || ''}</span>
    </div>
    ${body}
  </section>`;
}

function mini(label, value, sub) {
  return `<div>
    <div class="text-[10px] text-dim">${esc(label)}</div>
    <div class="num mt-0.5 text-[13px] text-ink">${esc(value)}</div>
    ${sub ? `<div class="mt-0.5 text-[10px] leading-tight text-dim">${esc(sub)}</div>` : ''}
  </div>`;
}

/* ───────────────────────── 文本报告（复制） ───────────────────────── */

function textReport() {
  const r = state.report;
  if (!r) return '';
  const m1 = r.m1_kline, m2 = r.m2_context, L = r.levels, p = r.playbook;
  const line = (s) => s;
  const out = [
    `【裸K战法 · 五模块分析】${r.name} (${r.code})`,
    `数据日期 ${r.date}${r.is_intraday ? '（盘中，未收盘）' : ''}  收盘 ${m1.ohcl.close}  涨跌 ${sgn(m1.chg_pct)}%`,
    `数据源 ${r.source} · 引擎 v${r.engine_version}`,
    ``,
    `── 模块一 K线解剖 ──`,
    `${m1.entity_class}（实体 ${m1.entity_pct}%） 上影 ${m1.shadow.upper_pct}%(${m1.shadow.upper_meaning}) 下影 ${m1.shadow.lower_pct}%(${m1.shadow.lower_meaning})`,
    `跳空 ${sgn(m1.gap.pct)}% ${m1.gap.class} · ${m1.close_pos.class} ${m1.close_pos.pct}%`,
    m1.narration,
    ``,
    `── 模块二 背景定位 ──`,
    `阶段 ${m2.stage}（60日 ${m2.p60_pct}% 位，区间 ${m2.range60.low}~${m2.range60.high}）`,
    `趋势 ${m2.trend}（近5/远5 比值 ${m2.trend_ratio}） · 定性 ${m2.kline_quality}`,
    `背景修正：${m2.background_note}`,
    ``,
    `── 模块三 关键价位 ──`,
    `冰线 ${L.ice.price}（P${L.ice.priority} ${L.ice.source}｜偏离 ${L.ice.deviation_pct}%｜${L.ice.detail}）`,
    L.ice.note ? `      ${L.ice.note}` : null,
    `供应区 ${L.supply.bottom}~${L.supply.top}（${L.supply.strength}，跨度 ${L.supply.width_pct}%）`,
    `需求区 ${L.demand.bottom}~${L.demand.top}（${L.demand.strength}，跨度 ${L.demand.width_pct}%）`,
    ``,
    `── 模块四 次日验证剧本 ──`,
    `A ${p.scenarios.A.prob}%  触发 >${p.scenarios.A.trigger}  ${p.scenarios.A.label}`,
    `B ${p.scenarios.B.prob}%  区间 ${p.scenarios.B.low}~${p.scenarios.B.high}  ${p.scenarios.B.label}`,
    `C ${p.scenarios.C.prob}%  触发 <${p.scenarios.C.trigger}  ${p.scenarios.C.label}`,
    `止损反推 ${p.stop_loss} — ${p.stop_note}`,
    p.corrections.length ? `修正：${p.corrections.join('；')}` : null,
    r.verification ? `\n── 模块六 事后验证 ──\n上轮 ${r.verification.prev_date} 预测 ${r.verification.prev_dominant} → 实际 ${r.verification.actual_scenario}　${r.verification.verdict}（${r.verification.days_elapsed} 个交易日后）` : null,
    r.warnings.length ? `\n── 警告 ──\n${r.warnings.map((w) => '· ' + w).join('\n')}` : null,
  ].filter((x) => x !== null).join('\n');
  return out;
}

/* ───────────────────────── 事件绑定 ───────────────────────── */

function setAddMode(on) {
  state.addMode = on;
  const q = $('#q');
  $('#btn-add').classList.toggle('text-accent', on);
  q.placeholder = on ? '输入要加入自选股的代码/名称，回车确认，Esc 取消' : '代码或名称，如 300768 / 迪普科技';
  q.focus();
}

function bind() {
  const q = $('#q');

  q.addEventListener('input', () => {
    clearTimeout(acTimer);
    const v = q.value;
    acTimer = setTimeout(() => doSearch(v), 180);
  });

  q.addEventListener('keydown', (e) => {
    const list = $$('.ac-item');
    if (e.key === 'ArrowDown' && list.length) {
      e.preventDefault();
      state.acIndex = (state.acIndex + 1) % list.length;
    } else if (e.key === 'ArrowUp' && list.length) {
      e.preventDefault();
      state.acIndex = (state.acIndex - 1 + list.length) % list.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const pick = state.acIndex >= 0 ? state.acItems[state.acIndex] : null;
      if (state.addMode) {
        const val = pick ? pick.code : q.value.trim();
        if (val) addToWatchlist(val);
        setAddMode(false);
      } else {
        closeAc();
        analyze(pick ? pick.code : q.value.trim());
        q.blur();
      }
      return;
    } else if (e.key === 'Escape') {
      closeAc();
      if (state.addMode) setAddMode(false);
      return;
    } else return;

    $$('.ac-item').forEach((el, i) => el.setAttribute('aria-selected', i === state.acIndex ? 'true' : 'false'));
    const cur = $$('.ac-item')[state.acIndex];
    if (cur) cur.scrollIntoView({ block: 'nearest' });
  });

  $('#ac').addEventListener('mousedown', (e) => {
    const it = e.target.closest('.ac-item');
    if (!it) return;
    e.preventDefault();
    const r = state.acItems[+it.dataset.i];
    closeAc();
    q.value = r.name;
    if (state.addMode) { addToWatchlist(r.code); setAddMode(false); }
    else analyze(r.code);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#ac') && e.target !== q) closeAc();
  });

  $('#btn-add').addEventListener('click', () => setAddMode(!state.addMode));
  $('#btn-refresh').addEventListener('click', () => {
    if (state.report) analyze(state.report.symbol);
  });
  $('#btn-copy').addEventListener('click', async () => {
    const txt = textReport();
    if (!txt) return showError('还没有可复制的报告');
    try {
      await navigator.clipboard.writeText(txt);
      const b = $('#btn-copy');
      b.innerHTML = ICON('check', 'h-4 w-4');
      b.classList.add('text-down');
      setTimeout(() => { b.innerHTML = ICON('refresh', 'h-4 w-4'); b.classList.remove('text-down'); }, 1600);
    } catch (e) { showError('复制失败：' + e.message); }
  });

  $('#watchlist').addEventListener('click', (e) => {
    const del = e.target.closest('[data-del]');
    if (del) { e.stopPropagation(); removeFromWatchlist(del.dataset.del); return; }
    const li = e.target.closest('.wl-item');
    if (li) analyze(li.dataset.q);
  });
  $('#watchlist').addEventListener('keydown', (e) => {
    const li = e.target.closest('.wl-item');
    if (li && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); analyze(li.dataset.q); }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); q.select(); }
    if (e.key === 'r' && document.activeElement !== q && !e.metaKey && !e.ctrlKey && state.report) analyze(state.report.symbol);
  });

  window.addEventListener('resize', () => drawBands());
}

async function addToWatchlist(query) {
  try {
    await api('/api/watchlist', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'add', query }),
    });
    await loadWatchlist();
    showError('已加入自选股：' + query);
    $('#err-banner').className = $('#err-banner').className.replace('border-playC/40 bg-playC/10 text-playC', 'border-down/40 bg-down/10 text-down');
  } catch (e) { showError('加入失败：' + e.message); }
}

async function removeFromWatchlist(query) {
  try {
    await api('/api/watchlist', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'remove', query }),
    });
    await loadWatchlist();
  } catch (e) { showError('移除失败：' + e.message); }
}

/* ───────────────────────── 启动 ───────────────────────── */

async function boot() {
  bind();
  try {
    const h = await api('/api/health');
    $('#eng-ver').textContent = h.engine;
    $('#eng-ver2').textContent = h.engine;
    const dot = $('#trade-dot'), txt = $('#trade-txt');
    dot.className = 'h-1.5 w-1.5 rounded-full ' + (h.trading_now ? 'bg-down animate-pulse' : 'bg-dim');
    txt.textContent = h.trading_now ? '盘中 · 实时' : '非交易时段';
    $('#trade-chip').classList.remove('hidden');
  } catch (e) { /* 静默 */ }

  await loadWatchlist();
  setInterval(loadWatchlist, 60000);

  const url = new URLSearchParams(location.search).get('q');
  const remembered = localStorage.getItem('nakedk.last');
  const first = url || remembered || ($($('#watchlist .wl-item'))?.dataset.q);
  if (first) analyze(first);
}

boot();
