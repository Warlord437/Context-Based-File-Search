/**
 * File visualization: 3D force-directed graph and category breakdown
 * Uses API_BASE from app.js (avoid duplicate declaration)
 */

const CATEGORY_COLORS = [
  '#22d3c7', '#0ea5e9', '#fbbf24', '#f87171', '#a78bfa',
  '#34d399', '#38bdf8', '#fbbf24', '#fb7185', '#c084fc',
];

let graphInstance = null;

async function loadVisualization() {
  const container = document.getElementById('graph3d');
  const categoriesEl = document.getElementById('categoriesView');
  const hint = document.getElementById('vizHint');

  try {
    // Phase 1: fast load without AI labels (instant display)
    const res = await fetch(`${(typeof API_BASE !== 'undefined' ? API_BASE : '')}/api/visualization?limit=250&ai_labels=false`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to load');

    if (!data.nodes || data.nodes.length === 0) {
      hint.textContent = 'No indexed files yet. Index some folders or browser links first.';
      container.innerHTML = '<div class="viz-empty">Index content to see the visualization</div>';
      return;
    }

    const local = data.local_count ?? 0;
    const browser = data.browser_count ?? 0;
    hint.textContent = `${data.total_files} files (${local} local, ${browser} links) • ${data.links.length} connections • Drag to rotate, scroll to zoom`;

    // 3D Graph
    init3DGraph(container, data);

    // Categories view (instant)
    renderCategories(categoriesEl, data.categories);

    // Phase 2: fetch AI labels in background, update Categories tab when ready
    fetch(`${(typeof API_BASE !== 'undefined' ? API_BASE : '')}/api/visualization?limit=250&ai_labels=true`)
      .then(r => r.json())
      .then(aiData => {
        if (aiData.categories && aiData.categories.length > 0) {
          renderCategories(categoriesEl, aiData.categories);
        }
      })
      .catch(() => {});

    // Tab switching
    const analyticsEl = document.getElementById('analyticsView');
    document.querySelectorAll('.viz-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.viz-tab').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        const view = tab.dataset.view;
        document.getElementById('graph3d').style.display = view === '3d' ? 'block' : 'none';
        document.getElementById('categoriesView').style.display = view === 'categories' ? 'block' : 'none';
        if (analyticsEl) {
          analyticsEl.style.display = view === 'analytics' ? 'block' : 'none';
          if (view === 'analytics') loadAnalytics(analyticsEl);
        }
      });
    });
  } catch (err) {
    hint.textContent = `Error: ${err.message}`;
    container.innerHTML = `<div class="viz-empty viz-error">${err.message}</div>`;
  }
}

function init3DGraph(container, data) {
  if (graphInstance) {
    graphInstance.graphData({ nodes: [], links: [] });
    graphInstance = null;
  }

  const categoryIndex = {};
  data.categories.forEach((c, i) => { categoryIndex[c.name] = i; });

  // Local files: green tint; browser links: blue/orange tint
  const sourceColors = { local: '#3fb950', browser: '#58a6ff' };
  const graphData = {
    nodes: data.nodes.map((n) => ({
      ...n,
      val: Math.max(2, Math.min(8, (n.chunk_count || 0) * 0.5 + 2)),
      color: n.source === 'local'
        ? sourceColors.local
        : (CATEGORY_COLORS[categoryIndex[n.category] % CATEGORY_COLORS.length] || sourceColors.browser),
    })),
    links: data.links,
  };

  const Graph = window.ForceGraph3D;
  if (!Graph) {
    container.innerHTML = '<div class="viz-empty">3D library not loaded</div>';
    return;
  }

  graphInstance = Graph()(container)
    .graphData(graphData)
    .nodeLabel((n) => {
      const catLabel = (data.categories || []).find(c => c.name === n.category)?.label || n.category;
      return `${n.name}\n${n.source} • ${catLabel} • ${n.file_type}`;
    })
    .nodeColor((n) => n.color || '#58a6ff')
    .nodeVal((n) => n.val || 3)
    .linkWidth(0.5)
    .linkDirectionalParticles(0)
    .backgroundColor('#0d1117')
    .onNodeClick((node) => {
      if (!node.path) return;
      if (node.source === 'browser' || node.path.startsWith('browser:')) {
        const url = node.path.startsWith('browser:') ? node.path.split(':').slice(2).join(':') : node.path;
        if (url.startsWith('http')) window.open(url, '_blank');
      } else if (node.source === 'local' && typeof openLocalFile === 'function') {
        openLocalFile(node.path);
      }
    });

  // Fit graph within container frame (respects .graph-3d CSS)
  const resize = () => {
    const rect = container.getBoundingClientRect();
    const w = Math.max(rect.width, 280);
    const h = Math.max(Math.min(rect.height, 420), 320);
    graphInstance.width(w).height(h);
  };
  resize();
  window.addEventListener('resize', resize);
  const ro = new ResizeObserver(resize);
  if (container.parentElement) ro.observe(container.parentElement);
}

function renderCategories(el, categories) {
  if (!categories || categories.length === 0) {
    el.innerHTML = '<div class="viz-empty">No categories</div>';
    return;
  }

  const maxCount = Math.max(...categories.map((c) => c.count), 1);
  el.innerHTML = `
    <div class="category-list">
      ${categories
        .map(
          (c, i) => `
        <div class="category-item">
          <div class="category-bar-wrap">
            <span class="category-bar" style="width: ${(c.count / maxCount) * 100}%; background: ${CATEGORY_COLORS[i % CATEGORY_COLORS.length]}"></span>
          </div>
          <span class="category-name">${escapeHtml(c.label || c.name)}</span>
          <span class="category-count">${c.count}</span>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function loadAnalytics(container) {
  if (!container) return;
  container.innerHTML = '<div class="viz-empty">Loading analytics...</div>';
  try {
    const res = await fetch(`${typeof API_BASE !== 'undefined' ? API_BASE : ''}/graphql`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `{
          analytics(topQueriesLimit: 10, searchSinceHours: 24, indexSinceHours: 168) {
            fileTypeDistribution { fileType count }
            topQueries { query count avgDuration }
            searchPercentiles { p50 p95 p99 }
            searchSummary { totalSearches cacheHits cacheHitRate avgDuration }
            indexSummary { totalOps totalFiles avgDuration }
          }
        }`,
      }),
    });
    const { data, errors } = await res.json();
    if (errors) throw new Error(errors[0]?.message || 'GraphQL error');
    const a = data?.analytics;
    if (!a) throw new Error('No analytics data');

    const fileTypes = a.fileTypeDistribution || [];
    const topQueries = a.topQueries || [];
    const pct = a.searchPercentiles || {};
    const searchSum = a.searchSummary || {};
    const indexSum = a.indexSummary || {};
    const maxFileCount = Math.max(...fileTypes.map((f) => f.count), 1);

    container.innerHTML = `
      <div class="analytics-grid">
        <div class="analytics-card">
          <h3>File types</h3>
          <div class="analytics-list">
            ${fileTypes.map((f) => `
              <div class="analytics-row">
                <span class="analytics-label">${escapeHtml(f.fileType)}</span>
                <span class="analytics-bar-wrap"><span class="analytics-bar" style="width: ${(f.count / maxFileCount) * 100}%"></span></span>
                <span class="analytics-value">${f.count.toLocaleString()}</span>
              </div>
            `).join('')}
          </div>
        </div>
        <div class="analytics-card">
          <h3>Search latency (p50 / p95 / p99)</h3>
          <p class="analytics-metric">${(pct.p50 || 0).toFixed(2)}s / ${(pct.p95 || 0).toFixed(2)}s / ${(pct.p99 || 0).toFixed(2)}s</p>
        </div>
        <div class="analytics-card">
          <h3>Search stats</h3>
          <p class="analytics-metric">${(searchSum.totalSearches || 0).toLocaleString()} searches</p>
          <p class="analytics-metric">${searchSum.cacheHitRate != null ? searchSum.cacheHitRate + '%' : '—'} cache hit rate</p>
          <p class="analytics-metric">${(searchSum.avgDuration ?? 0).toFixed(2)}s avg</p>
        </div>
        <div class="analytics-card">
          <h3>Index stats</h3>
          <p class="analytics-metric">${(indexSum.totalOps || 0).toLocaleString()} ops</p>
          <p class="analytics-metric">${(indexSum.totalFiles || 0).toLocaleString()} files</p>
          <p class="analytics-metric">${(indexSum.avgDuration ?? 0).toFixed(2)}s avg</p>
        </div>
        <div class="analytics-card analytics-card-wide">
          <h3>Top queries</h3>
          ${topQueries.length ? `
            <div class="analytics-list">
              ${topQueries.slice(0, 8).map((q) => `
                <div class="analytics-row">
                  <span class="analytics-label" title="${escapeHtml(q.query)}">${escapeHtml(q.query.length > 40 ? q.query.slice(0, 40) + '…' : q.query)}</span>
                  <span class="analytics-value">${q.count}×</span>
                </div>
              `).join('')}
            </div>
          ` : '<p class="analytics-muted">Run some searches to see top queries</p>'}
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="viz-empty viz-error">${escapeHtml(err.message)}</div>`;
  }
}

// Lazy load when viz section scrolls into view (faster initial page load)
function initVizWhenVisible() {
  const section = document.getElementById('vizSection');
  if (!section) return;
  const io = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) {
        io.disconnect();
        loadVisualization();
      }
    },
    { rootMargin: '100px', threshold: 0 }
  );
  io.observe(section);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initVizWhenVisible);
} else {
  initVizWhenVisible();
}
