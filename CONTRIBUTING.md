# 🤝 Contributing to Local-Agent

Thank you for your interest in contributing to Local-Agent! This document provides guidelines and instructions for contributing to the project.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contributing Guidelines](#contributing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Feature Requests](#feature-requests)
- [Documentation](#documentation)
- [Testing](#testing)
- [Code Style](#code-style)

## 📜 Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to [your-email@example.com].

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- Basic understanding of Python, vector databases, and document processing

### Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR-USERNAME/local-agent.git
cd local-agent

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL-OWNER/local-agent.git
```

## 🛠️ Development Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip
```

### 2. Install Dependencies

```bash
# Install core dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### 3. Verify Setup

```bash
# Run tests
python -m pytest tests/

# Check code style
black --check local-agent/
isort --check-only local-agent/
flake8 local-agent/

# Run type checking
mypy local-agent/
```

## 📝 Contributing Guidelines

### Types of Contributions

We welcome several types of contributions:

#### 🐛 Bug Fixes
- Fix bugs in existing functionality
- Improve error handling and edge cases
- Add missing error messages

#### ✨ New Features
- Add support for new file types
- Implement new search capabilities
- Add performance optimizations
- Create new CLI commands

#### 📚 Documentation
- Improve README and documentation
- Add code comments and docstrings
- Create tutorials and examples
- Fix typos and improve clarity

#### 🧪 Testing
- Add unit tests for new features
- Improve test coverage
- Add integration tests
- Performance benchmarking

#### 🔧 Infrastructure
- CI/CD improvements
- Docker and deployment scripts
- Performance monitoring
- Security enhancements

### Development Workflow

#### 1. Create Feature Branch

```bash
# Update main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name
# or
git checkout -b bugfix/issue-number
```

#### 2. Make Changes

```bash
# Make your changes
# Write tests for new functionality
# Update documentation as needed
```

#### 3. Test Your Changes

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_chunker.py -v

# Run with coverage
python -m pytest tests/ --cov=local-agent --cov-report=html

# Test CLI commands
python3 local-agent/cli.py status
python3 local-agent/cli.py index test.txt
```

#### 4. Code Quality Checks

```bash
# Format code
black local-agent/
isort local-agent/

# Lint code
flake8 local-agent/

# Type checking
mypy local-agent/

# Run pre-commit hooks
pre-commit run --all-files
```

## 🔄 Pull Request Process

### Before Submitting

1. **Test thoroughly**: Ensure all tests pass
2. **Update documentation**: Add/update docstrings and documentation
3. **Follow code style**: Use Black for formatting, follow PEP 8
4. **Write clear commit messages**: Use conventional commit format
5. **Update CHANGELOG**: Document your changes

### Submitting PR

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request**:
   - Use descriptive title and description
   - Reference related issues
   - Include screenshots for UI changes
   - Add testing instructions

3. **PR Template**:
   ```markdown
   ## Description
   Brief description of changes

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Documentation update
   - [ ] Performance improvement
   - [ ] Breaking change

   ## Testing
   - [ ] Tests pass locally
   - [ ] Added tests for new functionality
   - [ ] Manual testing completed

   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Documentation updated
   - [ ] No breaking changes (or documented)
   ```

### Review Process

1. **Automated Checks**: CI/CD pipeline runs tests and checks
2. **Code Review**: Maintainers review code quality and functionality
3. **Testing**: Reviewers test the changes
4. **Approval**: At least one maintainer approval required
5. **Merge**: Squash and merge to main branch

## 🐛 Issue Reporting

### Before Creating Issue

1. **Search existing issues**: Check if issue already exists
2. **Check documentation**: Ensure it's not a configuration issue
3. **Try latest version**: Ensure you're using the latest release

### Creating Bug Report

Use the bug report template:

```markdown
**Bug Description**
Clear description of the bug

**To Reproduce**
Steps to reproduce the behavior:
1. Run command '...'
2. See error

**Expected Behavior**
What you expected to happen

**Environment**
- OS: [e.g., macOS 13.0, Ubuntu 22.04]
- Python version: [e.g., 3.11.0]
- Local-Agent version: [e.g., 1.0.0]
- Dependencies: [list relevant packages]

**Additional Context**
Screenshots, logs, or other relevant information
```

### Creating Feature Request

```markdown
**Feature Description**
Clear description of the feature

**Use Case**
Why is this feature needed?

**Proposed Solution**
How should this feature work?

**Alternatives Considered**
Other solutions you've considered

**Additional Context**
Any other relevant information
```

## 🧪 Testing

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=local-agent --cov-report=html

# Run specific test file
python -m pytest tests/test_embedder.py

# Run with verbose output
python -m pytest -v

# Run only fast tests
python -m pytest -m "not slow"
```

### Writing Tests

#### Test Structure

```python
import pytest
from local_agent.core.chunker import chunk_file

class TestChunker:
    def test_chunk_file_basic(self):
        """Test basic file chunking functionality."""
        # Arrange
        test_file = "test.txt"
        
        # Act
        chunks = chunk_file(test_file)
        
        # Assert
        assert len(chunks) > 0
        assert all("text" in chunk for chunk in chunks)
```

#### Test Categories

- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete workflows
- **Performance Tests**: Benchmark critical operations

#### Test Files

- `tests/test_search.py` - Comprehensive search module tests

#### What Needs Testing

High priority areas that need more test coverage:
1. BFS indexer edge cases (symlinks, permissions, large directories)
2. PDF extraction fallback pipeline
3. Hybrid search scoring algorithm
4. Error handling in file parsers
5. Qdrant connection failures
6. SQLite FTS5 edge cases

### Test Data

```bash
# Create test data directory
mkdir -p tests/data

# Add sample files
echo "Test document content" > tests/data/test.txt
```

## 🎨 Code Style

### Python Style Guide

We follow PEP 8 with some modifications:

#### Formatting

```python
# Use Black for automatic formatting
black local-agent/

# Use isort for import sorting
isort local-agent/
```

#### Naming Conventions

```python
# Functions and variables: snake_case
def extract_text_from_file(file_path):
    pass

# Classes: PascalCase
class DocumentProcessor:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_CHUNK_SIZE = 1000
```

#### Docstrings

```python
def process_document(file_path: str, max_tokens: int = 500) -> List[Dict]:
    """Process a document and return chunks.
    
    Args:
        file_path: Path to the document file
        max_tokens: Maximum tokens per chunk
        
    Returns:
        List of chunk dictionaries with text and metadata
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If max_tokens is invalid
    """
    pass
```

### Type Hints

```python
from typing import List, Dict, Optional, Union

def search_documents(
    query: str,
    max_results: int = 50,
    include_context: bool = True
) -> List[Dict[str, Union[str, float]]]:
    """Search documents with type hints."""
    pass
```

## 📚 Documentation

### Documentation Standards

1. **README**: Keep updated with new features
2. **Docstrings**: Document all public functions and classes
3. **Comments**: Explain complex logic
4. **Examples**: Provide usage examples

### Documentation Files

- `README.md` - Main project documentation
- `INSTALL.md` - Installation instructions
- `ARCHITECTURE.md` - Technical architecture
- `CONTRIBUTING.md` - This file
- `CHANGELOG.md` - Release notes

### Updating Documentation

```bash
# Check documentation
python -m pydocstyle local-agent/

# Generate API documentation
sphinx-build -b html docs/ docs/_build/
```

## 🚀 Release Process

### Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

1. **Update version** in `__init__.py`
2. **Update CHANGELOG.md**
3. **Run full test suite**
4. **Update documentation**
5. **Create release tag**
6. **Publish to PyPI** (if applicable)

## 🏷️ Labels and Milestones

### Issue Labels

- `bug` - Something isn't working
- `enhancement` - New feature or request
- `documentation` - Documentation improvements
- `good first issue` - Good for newcomers
- `help wanted` - Extra attention needed
- `performance` - Performance improvements
- `security` - Security-related issues

### Pull Request Labels

- `breaking-change` - Breaking changes
- `needs-review` - Requires code review
- `ready-to-merge` - Approved and ready
- `work-in-progress` - Still being developed

## 💡 Getting Help

### Community Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **Discord**: Real-time chat (if available)

### Resources

- **Documentation**: Read the docs first
- **Examples**: Check the examples directory
- **Tests**: Look at test files for usage examples

## 🎯 Current Project Status

### ✅ What's Complete (v1.0)
- BFS streaming indexer with checkpointing
- Hybrid search (vector + lexical)
- Multi-format support (PDF, DOCX, HTML, Markdown, Code, Images)
- Dual storage (Qdrant + SQLite FTS5)
- Apple Silicon MPS acceleration
- CLI interface (`bfs-index`, `find`, `status`, `reset-db`)
- Comprehensive test suite
- Documentation

### 🚧 High-Priority Tasks (v2.0)

#### 1. LLM Integration (Most Wanted!)
- [ ] Implement Ollama integration for local LLMs
- [ ] Context retrieval from indexed documents
- [ ] Question answering with source citations
- [ ] Conversation history
- [ ] Multi-turn dialogue support

#### 2. File System Watcher
- [ ] Watchdog integration for real-time monitoring
- [ ] Incremental indexing on file changes
- [ ] Event queue for batch processing
- [ ] Configurable watch paths

#### 3. Web UI
- [ ] React/Vue frontend
- [ ] Search interface with live results
- [ ] Document preview
- [ ] Admin dashboard
- [ ] Configuration management UI

#### 4. Advanced Search
- [ ] Boolean operators (AND, OR, NOT)
- [ ] Date range filters
- [ ] File type filters
- [ ] Size filters
- [ ] Custom metadata filters

#### 5. Performance Optimizations
- [ ] Parallel BFS level processing
- [ ] Multi-GPU embedding support
- [ ] Vector quantization
- [ ] Better caching strategies
- [ ] Query optimization

### 💡 Good First Issues

These are great starting points for new contributors:

1. **Add new file type parser** (e.g., `.epub`, `.pptx`, `.odt`)
2. **Improve error messages** in CLI
3. **Add progress bars** for indexing
4. **Create example scripts** for common workflows
5. **Improve documentation** with more examples
6. **Add unit tests** for existing parsers
7. **Optimize snippet generation** algorithm
8. **Add color output** to CLI
9. **Create Docker Compose examples**
10. **Add benchmarking scripts**

### 🔥 Areas Needing Help

1. **LLM Integration** - Implement Q&A with Ollama
2. **Web UI Development** - React/Vue frontend
3. **File System Watcher** - Real-time indexing
4. **Additional Parsers** - More file type support
5. **Performance** - Profiling and optimization
6. **Testing** - Increase test coverage
7. **Documentation** - More tutorials and examples

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to Local-Agent! 🎉
