# Content Search Enhancements

**Date**: January 26, 2026  
**Status**: ✅ Implemented

---

## Summary

Four enhancements have been implemented to improve content search quality and flexibility.

---

## 1. Sentence-Aware Chunking ✅

**Problem**: Previous chunking split text by word count, breaking mid-sentence and hurting search quality.

**Solution**: Chunk text at sentence boundaries (`.`, `!`, `?`) when possible.

**Files Modified**:
- `search/indexer.py` - New `_chunk_by_sentences()`, `_chunk_by_words()`, `_create_chunk()` methods
- `search/config.py` - Added `sentence_chunking: True` to defaults
- `config.yaml` - Added `sentence_chunking: true`

**Configuration**:
```yaml
# config.yaml
index:
  sentence_chunking: true   # Set false to use word-based chunking
  max_tokens: 1200
  overlap: 80
```

**Behavior**:
- Prose/document text: Chunked at sentence boundaries
- Code/lists: Falls back to word-based chunking
- Overlap: Keeps last N sentences for context continuity

---

## 2. Configurable Embedding Model ✅

**Problem**: Model was hardcoded to `all-MiniLM-L6-v2`.

**Solution**: Model name is read from `config.embedding.model`.

**Files Modified**:
- `search/model_loader.py` - Reads model from config, caches by model name
- `search/config.py` - Added `embedding` section to defaults

**Configuration**:
```yaml
# config.yaml
embedding:
  model: "sentence-transformers/all-MiniLM-L6-v2"
  dim: 384
```

**Alternative Models** (384-dim, compatible with current Qdrant):
- `BAAI/bge-small-en-v1.5` - Better quality
- `sentence-transformers/all-mpnet-base-v2` - 768-dim (requires `qdrant.dim: 768`)

**Note**: Changing model requires `reset-db` and re-indexing.

---

## 3. Query Expansion with Synonyms ✅

**Problem**: Exact keyword queries missed semantically related content.

**Solution**: Expand query with WordNet synonyms for vector search (lexical still uses original query).

**Files Modified**:
- `search/retriever.py` - Added `_expand_query_with_synonyms()`, integrated into `search()`
- `requirements.txt` - Added `nltk>=3.8.0`
- `search/config.py` - Added `expand_query: True` to search config

**Example**:
```
Query: "machine learning"
Expanded: "machine learning ML neural network"  (for vector embedding)
Lexical: "machine learning"  (original, for exact keywords)
```

**Configuration**:
```yaml
search:
  expand_query: true
```

**CLI**:
```bash
# Disable expansion
python3 local-agent/cli.py find "query" --no-expand
```

---

## 4. Search Filters ✅

**Problem**: No way to filter results by file type or path.

**Solution**: Added `filters` parameter to search.

**Files Modified**:
- `search/retriever.py` - Added `_apply_filters()`, `filters` param to `search()`
- `search/api.py` - Pass filters from opts to retriever
- `local-agent/cli.py` - Added `--file-type`, `--path-contains`, `--no-expand`

**Filter Options**:
| Filter | Type | Description |
|--------|------|-------------|
| `file_ext` | List[str] | Only include files with these extensions |
| `path_contains` | str | Path must contain this string |

**CLI Usage**:
```bash
# Search only PDFs
python3 local-agent/cli.py find "machine learning" --file-type pdf

# Search only in Documents folder
python3 local-agent/cli.py find "report" --path-contains Documents

# Combine filters
python3 local-agent/cli.py find "python" --file-type py,md --path-contains Projects
```

**API Usage**:
```python
from search.api import run

result = run(
    query="machine learning",
    opts={
        "filters": {
            "file_ext": [".pdf", ".docx"],
            "path_contains": "Research"
        }
    }
)
```

---

## Testing

All 17 tests pass:
```bash
python3 -m pytest tests/test_search.py -v
```

---

## Migration Notes

- **Existing indexes**: Sentence chunking only affects newly indexed files. Re-index for full benefit.
- **Model change**: Run `reset-db` and re-index when changing embedding model.
- **nltk**: First query expansion may trigger `nltk.download("wordnet")` (~10MB).
