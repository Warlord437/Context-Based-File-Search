# 🤖 ChatGPT Integration Guide for Local-Agent

This document is specifically designed to help ChatGPT and other AI assistants understand and work with the Local-Agent codebase effectively.

## 🎯 Project Overview

**Local-Agent** is a high-performance, hybrid document search engine that combines vector similarity search with lexical (BM25) search. It uses BFS streaming indexing, concurrent processing, and modern database technologies including Qdrant and SQLite FTS5.

### Key Capabilities
- **Hybrid Search**: Combines vector similarity search with BM25 lexical search for best results
- **Universal Search**: Index and search PDFs, Word docs, HTML, code files, images (OCR)
- **System-wide Scanning**: Scan entire computer from root (/) with smart exclusions
- **BFS Streaming**: Level-by-level, checkpointable indexing with time/size caps
- **High Performance**: Apple Silicon MPS acceleration with batch processing
- **Dual Storage**: Qdrant for vectors + SQLite FTS5 for lexical search

## 🏗️ Architecture Summary

### New Hybrid Search Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CLI (cli.py)  │───▶│  Search Module   │───▶│ Hybrid Storage  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  User Commands  │    │ BFS Indexer      │    │ Qdrant + SQLite │
│ (find, bfs-index)│   │ (streaming)      │    │ (dual storage)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### File Structure
```
local-agent/
├── cli.py                 # Main CLI interface (updated for new search)
└── search/                # New hybrid search module
    ├── __init__.py        # Package initialization
    ├── config.py          # Configuration management
    ├── types.py           # Data contracts (Chunk, SearchHit, etc.)
    ├── schemas.sql        # SQLite schema definitions
    ├── paths.py           # Store path constants
    ├── ids.py             # ID generation utilities
    ├── storage.py         # Qdrant + SQLite storage layer
    ├── indexer.py         # BFS streaming indexer
    ├── retriever.py       # Hybrid retrieval logic
    ├── snippets.py        # Text snippet generation
    ├── api.py             # Public API with caching
    └── bench.py           # Benchmarking suite

tests/
└── test_search.py         # Comprehensive test suite

store/                     # Data storage directory
├── catalog.db             # SQLite catalog + FTS5
├── frontier.json          # BFS frontier checkpoint
└── cache/                 # LRU cache storage

docker-compose.yml         # Qdrant server setup
requirements.txt           # Dependencies
config.yaml               # Configuration
```

## 🚀 Quick Start Commands

### ✅ Currently Working Commands
```bash
# Start Qdrant server (required first!)
docker-compose up -d

# Check system status
python3 local-agent/cli.py status

# Index documents with BFS streaming
python3 local-agent/cli.py bfs-index ~/Documents
python3 local-agent/cli.py bfs-index ~/Documents --max-items 1000

# Search with hybrid retrieval
python3 local-agent/cli.py find "machine learning algorithms"
python3 local-agent/cli.py find "Python" --show-context

# Reset database and start fresh
python3 local-agent/cli.py reset-db
```

### 🚧 Not Yet Working (Placeholder Commands)
```bash
# These commands exist but don't work yet:
python3 local-agent/cli.py ask "What documents mention AI?"  # Returns placeholder message
```

### Advanced Usage
```bash
# Index with custom parameters
python3 local-agent/cli.py bfs-index ~/Documents \
  --max-tokens 1500 \
  --overlap 100 \
  --ocr \
  --max-pdf-pages 100

# Search with pagination
python3 local-agent/cli.py find "resume" \
  --page 1 \
  --per-page 20 \
  --show-context

# Run benchmarks
python3 -m search.bench --paths ~/Documents ~/Desktop
```

## 🔍 Key Components Explained

### 1. Configuration System (`search/config.py`)
- **Purpose**: Centralized configuration with YAML support
- **Features**: Environment variable overlays, type conversion, validation
- **Key Settings**: Index parameters, search weights, Qdrant config, paths

### 2. Data Contracts (`search/types.py`)
- **Chunk**: Document chunk with metadata (path, file_id, text, tokens)
- **SearchHit**: Search result with scoring breakdown and snippet
- **FileMeta**: File metadata for change tracking
- **ScoreBreakdown**: Detailed scoring components (cosine, BM25, exact, position)

### 3. Dual Storage (`search/storage.py`)
- **QdrantStore**: Vector storage with HNSW optimization and gRPC
- **Catalog**: SQLite database with FTS5 for lexical search
- **Features**: Batch operations, connection management, error handling

### 4. BFS Indexer (`search/indexer.py`)
- **Purpose**: Level-by-level, checkpointable indexing
- **Features**: Frontier-based traversal, robust PDF pipeline, streaming processing
- **Pipeline**: Extract → Chunk → Embed → Upsert to both stores
- **Robustness**: Multiple PDF extraction methods, time/size caps, change detection

### 5. Hybrid Retriever (`search/retriever.py`)
- **Vector Search**: Qdrant similarity search with cosine similarity
- **Lexical Search**: SQLite FTS5 with BM25 scoring and Porter stemming
- **Score Fusion**: Weighted combination with exact match and position boosts
- **Deduplication**: File-level result aggregation

### 6. Public API (`search/api.py`)
- **Purpose**: Clean interface for search operations
- **Features**: Pagination, LRU caching, configurable parameters
- **Caching**: In-process LRU cache for repeated queries

## 📊 Data Flow

### Indexing Flow
```
File Discovery → Text Extraction → Chunking → Embedding → Dual Storage
     ↓              ↓              ↓          ↓           ↓
  BFS Walker    PDF/HTML/DOCX   Token Split  MPS Batch   Qdrant+SQLite
     ↓              ↓              ↓          ↓           ↓
  Frontier      Robust Pipeline   Overlap    Vectorize   Batch Upsert
```

### Search Flow
```
Query → Embedding → Vector Search → Lexical Search → Score Fusion → Results
  ↓        ↓           ↓              ↓              ↓           ↓
Text    Vector      Qdrant         FTS5           Weighted    Paginated
Query   Embed       Similarity     BM25           Ranking     Display
```

## 🛠️ Development Patterns

### Adding New File Types
```python
# In search/indexer.py
def _extract_text_from_file(path: Path, ocr_enabled: bool = False) -> str:
    """Add support for new file formats."""
    suffix = path.suffix.lower()
    
    if suffix == ".custom":
        return _extract_custom_format(path)
    # ... existing parsers
```

### Custom Scoring
```python
# In search/retriever.py
def merge_and_score(query: str, vec_cands: dict, lex_cands: dict) -> list:
    """Implement custom scoring logic."""
    # Custom scoring algorithm
    return scored_results
```

### Configuration Overrides
```python
# In search/config.py
DEFAULT = {
    "search": {
        "bm25_weight": 0.55,      # Lexical search weight
        "cosine_weight": 0.45,    # Vector search weight
        "exact_boost": 0.20,      # Exact match bonus
        "early_pos_boost": 0.10   # Early position bonus
    }
}
```

## 🔧 Common Tasks

### 1. Debugging Search Issues
```python
# Check if Qdrant is running
curl http://localhost:6333/health

# Check database status
python3 -c "
from search.storage import create_storage
qdrant, catalog = create_storage()
print(f'Qdrant points: {qdrant.client.count().count}')
print(f'SQLite chunks: {catalog.conn.execute(\"SELECT COUNT(*) FROM chunks\").fetchone()[0]}')
"
```

### 2. Performance Tuning
```yaml
# In config.yaml
index:
  embed_batch: 2048        # Increase for faster embedding
  upsert_batch: 8000       # Increase for faster upserts
  max_pdf_pages: 100       # Limit PDF processing

search:
  timeout_sec: 1.0         # Reduce for faster searches
  top_k: 100               # Increase for more results
```

### 3. Custom File Processing
```python
# Add new file type support
def _extract_custom_format(path: Path) -> str:
    """Extract text from custom file format."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            # Custom parsing logic
            return custom_parser(f.read())
    except Exception as e:
        logger.warning(f"Error parsing {path}: {e}")
        return ""
```

## 🧪 Testing

### Run Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_search.py::test_hybrid_search -v

# Run with coverage
python -m pytest tests/ --cov=search --cov-report=html
```

### Test Structure
```python
# tests/test_search.py
def test_hybrid_search():
    """Test hybrid search functionality."""
    # Setup test data
    # Run search
    # Assert results
    pass

def test_bfs_indexer():
    """Test BFS indexing."""
    # Setup test directory
    # Run indexing
    # Verify results
    pass
```

## 📈 Performance Monitoring

### Built-in Metrics
```python
# Check indexing stats
from search.storage import create_storage
qdrant, catalog = create_storage()

# Get stats from SQLite
stats = catalog.conn.execute("""
    SELECT * FROM index_stats 
    ORDER BY timestamp DESC 
    LIMIT 10
""").fetchall()

# Get search stats
search_stats = catalog.conn.execute("""
    SELECT * FROM search_stats 
    ORDER BY timestamp DESC 
    LIMIT 10
""").fetchall()
```

### Benchmarking
```bash
# Run comprehensive benchmark
python3 -m search.bench --paths ~/Documents ~/Desktop

# Test search performance only
python3 -m search.bench --search-only --query "test query"

# Custom benchmark
python3 -m search.bench \
  --paths ~/Documents \
  --max-items 1000 \
  --embed-batch 1024
```

## 🚨 Common Issues & Solutions

### 1. "Qdrant client not available"
```bash
# Start Qdrant server
docker-compose up -d

# Check if running
curl http://localhost:6333/health
```

### 2. "No module named 'search'"
```bash
# Make sure you're in project root
cd /path/to/local-agent

# Check Python path
python3 -c "import sys; print(sys.path)"
```

### 3. "Search returns no results"
```bash
# Check if content is indexed
python3 local-agent/cli.py status

# Reset and re-index
python3 local-agent/cli.py reset-db
python3 local-agent/cli.py bfs-index ~/Documents
```

### 4. "Slow indexing"
```bash
# Use smaller batches
python3 local-agent/cli.py bfs-index ~/Documents --max-items 100

# Adjust config.yaml
index:
  embed_batch: 512
  upsert_batch: 2000
```

## 🎯 What's Actually Implemented vs What's Planned

### ✅ Currently Working (v1.0)
- **bfs-index command**: Fully functional BFS streaming indexer
- **find command**: Hybrid search with vector + lexical retrieval
- **status command**: System health check with detailed info
- **reset-db command**: Clear all data and start fresh
- **PDF/DOCX/HTML/Markdown parsing**: All working with robust fallbacks
- **OCR support**: Works if Tesseract is installed (use `--ocr` flag)
- **Qdrant integration**: Vector storage fully operational
- **SQLite FTS5**: Lexical search fully operational
- **MPS acceleration**: Apple Silicon GPU support works

### 🚧 Not Implemented Yet (Coming in v2.0+)

#### High Priority (Next Release)
- **LLM Integration**: `ask` command exists but returns placeholder
- **File System Watcher**: No real-time monitoring yet
- **Daemon Mode**: No background auto-indexing
- **Root Scanning**: No system-wide safety features yet
- **Advanced Filters**: No date/type/size filters yet
- **Boolean Queries**: No AND/OR/NOT operators yet

#### Future Releases
- **Web UI**: No browser interface yet
- **REST API**: No HTTP endpoints yet
- **Multi-user**: Single user only
- **Authentication**: No auth system
- **Distributed**: Single machine only

### 🐛 Known Issues
1. **ask command**: Only shows placeholder message
2. **Large PDFs**: Can be memory intensive (>100 pages)
3. **OCR speed**: Image processing is slow
4. **Single-threaded**: BFS processes one level at a time
5. **Manual updates**: No automatic re-indexing on file changes

## 🎯 Best Practices

### 1. Configuration Management
- Use `config.yaml` for default settings
- Override with environment variables for deployment
- Keep sensitive data in environment variables

### 2. Error Handling
- Always check Qdrant connection before indexing
- Use try-catch blocks for file processing
- Log errors with context for debugging

### 3. Performance Optimization
- Use appropriate batch sizes for your hardware
- Monitor memory usage during indexing
- Use BFS indexer for large datasets

### 4. Testing
- Write tests for new file type parsers
- Test both vector and lexical search paths
- Benchmark performance changes

## 📚 Additional Resources

### Documentation Files
- `README.md` - User guide and quick start
- `ARCHITECTURE.md` - Technical architecture details
- `CONTRIBUTING.md` - Development guidelines
- `INSTALL.md` - Installation instructions

### Configuration Examples
- `config.yaml` - Main configuration file
- `config.yaml.example` - Configuration template
- `docker-compose.yml` - Qdrant server setup

### Development Tools
- `requirements.txt` - Python dependencies
- `requirements-dev.txt` - Development dependencies
- `setup.py` - Package installation
- `install.sh` - Automated setup script

## 🚀 Development Priorities

### If You're Helping Implement Features

#### Priority 1: LLM Integration
The `ask` command exists but needs implementation. Key tasks:
1. Integrate with Ollama for local LLM inference
2. Retrieve relevant context from indexed documents
3. Format prompts with context for Q&A
4. Handle conversation history
5. Return answers with source citations

**Files to modify:**
- `local-agent/cli.py` - Update `_ask()` function
- Create new `search/llm.py` - LLM integration module
- Update `search/retriever.py` - Add context retrieval function

#### Priority 2: File System Watcher
Add real-time monitoring for file changes:
1. Use `watchdog` library for file monitoring
2. Detect file creation, modification, deletion
3. Queue changes for batch processing
4. Implement incremental re-indexing
5. Add configuration for watch paths

**Files to create:**
- `search/watcher.py` - File system monitoring
- `search/incremental.py` - Incremental indexing logic

#### Priority 3: Web UI
Create browser-based interface:
1. React/Vue frontend with search interface
2. WebSocket for real-time results
3. Document preview
4. Admin dashboard
5. Configuration UI

**Files to create:**
- `web/` directory with frontend code
- `search/server.py` - Web server with API endpoints

### Common Development Tasks

#### Adding a New File Type
```python
# In search/indexer.py, update _extract_text_from_file()
if suffix == ".your_format":
    return extract_your_format(path)
```

#### Modifying Search Scoring
```python
# In search/retriever.py, update merge_and_score()
# Adjust weights in config.yaml under search section
```

#### Adding CLI Commands
```python
# In local-agent/cli.py
# 1. Create handler function: def _your_command(args):
# 2. Add subparser in main()
# 3. Set function with: p.set_defaults(func=_your_command)
```

This guide should help you understand and work with the Local-Agent codebase effectively. The architecture is solid for v1.0, and the modular design makes it easy to add new features incrementally.