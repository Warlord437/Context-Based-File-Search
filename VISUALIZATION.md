# Viewing File Clusters & Vector Visualization

**Date**: January 2026  
**Status**: ✅ Implemented

---

## Overview

Local-Agent stores document chunks as vectors in Qdrant. Each chunk is a 384-dimensional embedding. Similar documents cluster together in this space—so you can explore how your files relate to each other and visualize them in the Qdrant dashboard.

---

## Quick Start: View Your Indexed Files

1. **Start Qdrant** (if not running):
   ```bash
   docker-compose up -d
   ```

2. **Open the Qdrant dashboard**:
   ```
   http://localhost:6333/dashboard
   ```

3. **Select your collection**: `local_agent_vectors`

4. **Browse points**:
   - Each point = one chunk from a file
   - Use the Console to explore or scroll through points

---

## What Changed (Qdrant API & Payload)

### Qdrant API Fix
- **Before**: Used deprecated `client.search()` → caused `'QdrantClient' object has no attribute 'search'`.  
- **After**: Uses `client.query_points()` (current API in qdrant-client 1.7+).  
- **Files**: `search/storage.py`

### Payload for Visualization
Each indexed chunk now stores a **text snippet** in its payload so you can preview content in the dashboard:

| Payload Field | Description |
|---------------|-------------|
| `path` | Full file path |
| `file_id` | Stable file identifier |
| `chunk_id` | Unique chunk ID |
| `idx` | Chunk index within file |
| `text` | First 500 chars of chunk text (for preview) |

**Files**: `search/indexer.py` – payload extended with `text`.

---

## How to View File Clusters

### 1. Qdrant Dashboard

**URL**: http://localhost:6333/dashboard

1. **Collections** → select `local_agent_vectors`
2. **Points** → browse points and payloads
3. **Console** → run REST API calls

**Example**: Scroll points to see `path`, `text`, and other metadata. Similar content will have similar vectors (close in cosine space).

### 2. Console (REST API)

In the dashboard, use the **Console** tab to run queries:

**Search similar to a query**:
```http
POST /collections/local_agent_vectors/points/query
Content-Type: application/json

{
  "query": {
    "query": {
      "vector": [0.1, -0.2, ...],  // 384-dim embedding
      "using": "default"
    },
    "limit": 10,
    "with_payload": true
  }
}
```

**Scroll all points** (to inspect clusters):
```http
POST /collections/local_agent_vectors/points/scroll
Content-Type: application/json

{
  "limit": 100,
  "with_payload": true,
  "with_vector": false
}
```

### 3. Web UI Graph Tool (Optional)

Qdrant’s Web UI includes a graph tool for visualizing vector embeddings. Use it to see how clusters form in 2D/3D.

- Tutorial: http://localhost:6333/dashboard#/tutorial.

---

## Understanding Clusters

- **Semantic clustering**: Chunks are embedded by meaning. Similar topics cluster together.
- **Similar embeddings**: Nearby points in vector space are semantically similar.
- **Payload fields**: Use `path` and `text` to interpret what each cluster represents.

---

## Re-indexing for New Payload

After the payload update, existing points will not have the `text` field until you re-index:

```bash
# Reset and re-index
python3 local-agent/cli.py reset-db
python3 local-agent/cli.py bfs-index ~/Documents --max-items 1000
```

---

## Related Files

| File | Purpose |
|------|---------|
| `search/storage.py` | Vector search via `query_points` |
| `search/indexer.py` | Payload with `text` snippet |
| `requirements.txt` | `qdrant-client>=1.7.0` for compatibility |
