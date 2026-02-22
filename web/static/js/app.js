/**
 * Local-Agent Web UI - Search client
 */

const API_BASE = '';

// DOM elements
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const fileTypeInput = document.getElementById('fileType');
const pathContainsInput = document.getElementById('pathContains');
const expandQueryCheckbox = document.getElementById('expandQuery');
const statusBadge = document.getElementById('statusBadge');
const statsBar = document.getElementById('statsText');
const emptyState = document.getElementById('emptyState');
const resultsList = document.getElementById('resultsList');
const pagination = document.getElementById('pagination');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const pageInfo = document.getElementById('pageInfo');
const indexBtn = document.getElementById('indexBtn');
const indexBrowserBtn = document.getElementById('indexBrowserBtn');
const indexPath = document.getElementById('indexPath');
const maxItemsInput = document.getElementById('maxItems');
const indexHint = document.getElementById('indexHint');

// State
let currentPage = 1;
let totalPages = 1;
let currentQuery = '';

// Fetch status on load
async function fetchStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();

    statusBadge.classList.remove('error');
    statusBadge.classList.add('connected');

    if (data.status === 'ok') {
      statusBadge.querySelector('.status-text').textContent =
        `${data.files_indexed?.toLocaleString() || 0} files • ${data.vectors_count?.toLocaleString() || 0} vectors`;
    } else {
      statusBadge.classList.remove('connected');
      statusBadge.classList.add('error');
      statusBadge.querySelector('.status-text').textContent = 'Connection error';
    }
  } catch (err) {
    statusBadge.classList.remove('connected');
    statusBadge.classList.add('error');
    statusBadge.querySelector('.status-text').textContent = 'Offline';
  }
}

// Perform search
async function search(page = 1) {
  const query = searchInput.value.trim();
  if (!query) return;

  currentPage = page;
  currentQuery = query;

  searchBtn.disabled = true;
  document.body.classList.add('loading');

  emptyState.style.display = 'none';
  resultsList.style.display = 'block';
  resultsList.innerHTML = '<div class="empty-state">Searching...</div>';
  pagination.style.display = 'none';

  try {
    const body = {
      query,
      page,
      per_page: 10,
      file_type: fileTypeInput.value.trim() || null,
      path_contains: pathContainsInput.value.trim() || null,
      expand_query: expandQueryCheckbox.checked,
    };

    const res = await fetch(`${API_BASE}/api/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Search failed');
    }

    // Update stats
    statsBar.textContent = data.error
      ? `Error: ${data.error}`
      : `Found ${data.total_hits?.toLocaleString() || 0} results in ${(data.search_time || 0).toFixed(2)}s${data.cache_hit ? ' (cached)' : ''}`;

    // Render results
    if (!data.items || data.items.length === 0) {
      resultsList.innerHTML = `
        <div class="empty-state">
          <p>No context found for "${escapeHtml(query)}"</p>
          <p class="hint">Nothing in your indexed documents and links matches this query. Try different keywords or index more content.</p>
        </div>
      `;
    } else {
      resultsList.innerHTML = data.items.map((hit) => renderResultCard(hit)).join('');
      // Delegate Open button clicks
      resultsList.querySelectorAll('.open-file-btn').forEach((btn) => {
        btn.addEventListener('click', () => openLocalFile(btn.dataset.path));
      });
    }

    // Pagination
    totalPages = data.total_pages || 1;
    if (totalPages > 1) {
      pagination.style.display = 'flex';
      pageInfo.textContent = `Page ${data.page} of ${totalPages}`;
      prevBtn.disabled = !data.has_prev;
      nextBtn.disabled = !data.has_next;
    }
  } catch (err) {
    statsBar.textContent = `Error: ${err.message}`;
    resultsList.innerHTML = `
      <div class="empty-state">
        <p>Search failed: ${escapeHtml(err.message)}</p>
        <p class="hint">Make sure the server is running and Qdrant is started.</p>
      </div>
    `;
  } finally {
    searchBtn.disabled = false;
    document.body.classList.remove('loading');
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function shortenPath(path, maxLen = 60) {
  // Browser links: browser:bookmark:https://... or browser:history:https://...
  if (path.startsWith('browser:')) {
    const parts = path.split(':', 3);
    const url = parts[2] || path;
    return (url.length <= maxLen - 2) ? `🔗 ${url}` : `🔗 ...${url.slice(-(maxLen - 6))}`;
  }
  if (path.length <= maxLen) return path;
  return '...' + path.slice(-maxLen);
}

/**
 * Detect result type from path for proper link handling.
 * @returns {'web'|'local'|'email'}
 */
function getResultType(path) {
  if (!path || typeof path !== 'string') return 'local';
  const lower = path.toLowerCase();
  if (lower.startsWith('browser:')) {
    const parts = path.split(':', 3);
    const url = parts[2] || '';
    if (url.startsWith('mailto:')) return 'email';
    if (url.startsWith('http://') || url.startsWith('https://')) return 'web';
  }
  if (lower.startsWith('mailto:')) return 'email';
  if (lower.startsWith('http://') || lower.startsWith('https://')) return 'web';
  return 'local';
}

/**
 * Extract target URL for web/email links, or null for local files.
 */
function getTargetUrl(path) {
  const type = getResultType(path);
  if (type === 'web' || type === 'email') {
    if (path.startsWith('browser:')) {
      const parts = path.split(':', 3);
      return parts[2] || null;
    }
    return path;
  }
  return null;
}

function renderResultCard(hit) {
  const type = getResultType(hit.path);
  const targetUrl = getTargetUrl(hit.path);
  const displayPath = shortenPath(hit.path);
  const snippet = escapeHtml(hit.snippet || '(no snippet)');

  let pathEl;
  if (type === 'web' && targetUrl) {
    pathEl = `<a href="${escapeHtml(targetUrl)}" target="_blank" rel="noopener" class="result-path-link" title="${escapeHtml(hit.path)}">${escapeHtml(displayPath)} ↗</a>`;
  } else if (type === 'local') {
    pathEl = `<span class="result-path" title="${escapeHtml(hit.path)}">${escapeHtml(displayPath)}</span>
              <button type="button" class="open-file-btn" data-path="${escapeHtml(hit.path)}" title="Open file">Open</button>`;
  } else {
    // email: show context, no redirect link
    pathEl = `<span class="result-path result-path-email" title="${escapeHtml(hit.path)}">${escapeHtml(displayPath)}</span>
              <span class="result-badge">email</span>`;
  }

  return `
    <article class="result-card" data-type="${type}">
      <div class="result-header">
        <span class="result-path-wrap">${pathEl}</span>
        <span class="result-score">${(hit.score * 100).toFixed(0)}% match</span>
      </div>
      <div class="result-meta">${hit.file_type}</div>
      <div class="result-snippet">${snippet}</div>
    </article>
  `;
}

// Index folder
async function runIndex() {
  const path = indexPath.value.trim();
  if (!path) {
    indexHint.textContent = 'Enter a path (e.g. ~/Documents)';
    return;
  }

  indexBtn.disabled = true;
  indexHint.textContent = 'Indexing...';

  try {
    const res = await fetch(`${API_BASE}/api/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path,
        max_items: parseInt(maxItemsInput.value) || 100,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Indexing failed');
    }

    indexHint.textContent = `Indexed ${data.files_processed} files, ${data.chunks_created} chunks in ${data.duration_seconds}s`;
    fetchStatus();
    if (typeof loadVisualization === 'function') loadVisualization();
  } catch (err) {
    indexHint.textContent = `Error: ${err.message}`;
  } finally {
    indexBtn.disabled = false;
  }
}

// Index browser (bookmarks + history)
async function runIndexBrowser() {
  indexBrowserBtn.disabled = true;
  indexHint.textContent = 'Indexing browser bookmarks & history...';

  try {
    const res = await fetch(`${API_BASE}/api/index-browser`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Browser indexing failed');
    }

    indexHint.textContent = `Indexed ${data.links_indexed} links in ${data.duration_seconds}s${data.errors ? ` (${data.errors} errors)` : ''}`;
    fetchStatus();
    if (typeof loadVisualization === 'function') loadVisualization();
  } catch (err) {
    indexHint.textContent = `Error: ${err.message}`;
  } finally {
    indexBrowserBtn.disabled = false;
  }
}

async function openLocalFile(path) {
  if (!path) return;
  try {
    const res = await fetch(`${API_BASE}/api/open-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to open file');
    // Success - file should open in default app
  } catch (err) {
    alert(`Could not open file: ${err.message}`);
  }
}

// Event listeners
indexBtn.addEventListener('click', runIndex);
indexBrowserBtn.addEventListener('click', runIndexBrowser);
searchBtn.addEventListener('click', () => search(1));
searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') search(1);
});
prevBtn.addEventListener('click', () => search(currentPage - 1));
nextBtn.addEventListener('click', () => search(currentPage + 1));

// Init
fetchStatus();
