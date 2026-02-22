# 📝 Changelog

All notable changes to Local-Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - v2.0.0 (Planned)

### Planned Features
- LLM integration with Ollama for question answering
- File system watcher for real-time indexing
- Auto-indexing daemon with system monitoring
- Web UI for browser-based search
- REST API for external integrations
- Advanced search filters (date, type, size)
- Boolean query operators (AND, OR, NOT)
- Distributed processing for multi-machine indexing
- Vector quantization for storage efficiency

### Planned Improvements
- Parallel BFS level processing for faster indexing
- Better error messages and progress indicators
- Improved search ranking with ML models
- Enhanced PDF extraction for complex layouts
- Multi-language support for embeddings

## [1.0.0] - 2024-10-09 (Current Release)

### ✅ Implemented Features
- **Core Search Engine**
  - BFS streaming indexer with level-by-level processing
  - Hybrid search combining vector similarity (Qdrant) and lexical search (SQLite FTS5)
  - Multi-format file support (PDF, DOCX, HTML, Markdown, Code, Images with OCR)
  - Robust PDF extraction pipeline (pypdfium2 → pdfminer.six → OCR fallback)
  - Semantic search with 384-dimensional embeddings
  - BM25 lexical search with Porter stemming

- **Storage & Performance**
  - Dual storage system (Qdrant vectors + SQLite catalog/FTS5)
  - Apple Silicon MPS acceleration for embeddings
  - Batch processing (1024 embedding batch, 4000 upsert batch)
  - SHA256-based change detection for incremental updates
  - LRU caching for fast repeated searches
  - Checkpointed BFS traversal for resumable indexing

- **CLI Interface**
  - `bfs-index`: Index files and directories with BFS streaming
  - `find`: Search with hybrid retrieval and context snippets
  - `status`: System health check with detailed statistics
  - `reset-db`: Clear all indexed data
  - `ask`: Placeholder command for future LLM integration

- **Configuration & Deployment**
  - YAML-based configuration system
  - Environment variable overrides
  - Docker Compose setup for Qdrant server
  - Comprehensive documentation (README, INSTALL, ARCHITECTURE, CONTRIBUTING)
  - Benchmark suite for performance tracking
  - Development dependencies and tooling

- **File Type Support**
  - Text files (.txt, .md, .markdown)
  - PDF documents (pypdfium2 → pdfminer.six → OCR fallback)
  - Microsoft Word (.docx)
  - HTML documents (BeautifulSoup + lxml)
  - Code files (.py, .js, .ts, .java, .cpp, .c, .h, etc.)
  - Images with OCR (.png, .jpg, .jpeg, .gif, .bmp, .tiff) - requires Tesseract
  - RTF documents

- **Search Capabilities**
  - Hybrid scoring: 0.45×cosine + 0.55×BM25 + 0.20×exact + 0.10×position
  - Context snippets with configurable radius
  - Pagination support
  - Case-sensitive and exact matching options
  - Deduplication at file level (best chunk per file)
  - Configurable result limits

- **Performance Characteristics**
  - ~300 files/min indexing speed (BFS level-by-level)
  - ~150ms search latency
  - ~1.2GB memory usage
  - Tested with 10M files, 100M chunks
  - Smart file exclusions for system directories

### Technical Specifications

- **Embedding Model**: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
- **Vector Database**: Qdrant with HNSW optimization (m=32, ef_construct=256)
- **Lexical Search**: SQLite FTS5 with BM25 ranking and Porter stemming
- **Indexing**: Single-threaded BFS with checkpointing
- **Batch Sizes**: 1024 embedding batch, 4000 upsert batch
- **Memory Usage**: ~1.2GB total system memory
- **Device Support**: CPU, Apple Silicon MPS (GPU acceleration)

### Configuration

- Comprehensive config.yaml with all options
- Environment variable support for overrides
- Sane defaults for common use cases
- Configurable scoring weights and search parameters
- Extensible file type configuration

### CLI Commands (v1.0)

```bash
# Indexing
python3 local-agent/cli.py bfs-index ~/Documents
python3 local-agent/cli.py bfs-index ~/Documents --max-items 500 --ocr

# Searching
python3 local-agent/cli.py find "machine learning" --show-context
python3 local-agent/cli.py find "resume" --exact --max-results 10

# System Management
python3 local-agent/cli.py status
python3 local-agent/cli.py reset-db

# Benchmarking
python3 -m search.bench --paths ~/Documents
```

### Documentation

- Complete README with quick start guide and roadmap
- Detailed installation instructions for macOS, Linux, Windows
- Architecture documentation with data flow diagrams
- Contributing guidelines with development priorities
- ChatGPT/AI assistant guide for code understanding
- Comprehensive changelog

### Known Limitations (v1.0)

- **LLM Q&A**: `ask` command is placeholder only (planned for v2.0)
- **No File Watching**: Manual re-indexing required for file changes
- **Single-threaded BFS**: Sequential level processing (parallel planned for v2.0)
- **No Root Scanning**: System-wide indexing safety features incomplete
- **Large PDFs**: Memory intensive for PDFs >100 pages
- **OCR Speed**: Image OCR processing is slow

## [0.9.0] - 2024-01-XX (Pre-release)

### Added
- Initial implementation of core search functionality
- Basic file type support (text, PDF, HTML)
- Simple vector storage with JSONL fallback
- Basic CLI interface
- Sequential processing pipeline

### Changed
- Improved error handling
- Better file parsing reliability
- Enhanced search result formatting

### Fixed
- Memory leaks in file processing
- Search result accuracy issues
- File permission handling

## [0.8.0] - 2024-01-XX (Alpha)

### Added
- First working prototype
- Basic document indexing
- Simple text search
- File system scanning
- Vector embeddings with sentence-transformers

### Known Issues
- Limited file type support
- No concurrent processing
- Basic error handling
- No configuration system

---

## Legend

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes
