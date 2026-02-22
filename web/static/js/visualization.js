/**
 * File visualization: 3D force-directed graph and category breakdown
 * Uses API_BASE from app.js (avoid duplicate declaration)
 */

const CATEGORY_COLORS = [
  '#58a6ff', '#3fb950', '#d29922', '#f85149', '#a371f7',
  '#79c0ff', '#56d364', '#e3b341', '#ff7b72', '#bc8cff',
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
    document.querySelectorAll('.viz-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.viz-tab').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        const view = tab.dataset.view;
        if (view === '3d') {
          document.getElementById('graph3d').style.display = 'block';
          document.getElementById('categoriesView').style.display = 'none';
        } else {
          document.getElementById('graph3d').style.display = 'none';
          document.getElementById('categoriesView').style.display = 'block';
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
