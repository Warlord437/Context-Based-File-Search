# 📦 Installation Guide

This guide provides step-by-step instructions for installing and setting up Local-Agent on different operating systems.

## System Requirements

### Minimum Requirements
- **Python**: 3.8 or higher
- **RAM**: 4GB (8GB+ recommended)
- **Storage**: 2GB free space
- **OS**: macOS 10.15+, Ubuntu 18.04+, or Windows 10+

### Recommended Requirements
- **Python**: 3.11 or higher
- **RAM**: 16GB
- **Storage**: 10GB free space
- **CPU**: Multi-core processor (8+ cores for best performance)
- **GPU**: Apple Silicon (M1/M2/M3) for MPS acceleration

## Installation Methods

### Method 1: Direct Installation (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/local-agent.git
cd local-agent

# Install Python dependencies
pip install -r requirements.txt

# Install optional dependencies for best performance
pip install pypdfium2 pdfminer.six beautifulsoup4 lxml psutil

# Verify installation
python3 local-agent/cli.py status
```

### Method 2: Virtual Environment (Recommended for Development)

```bash
# Create virtual environment
python3 -m venv local-agent-env
source local-agent-env/bin/activate  # On Windows: local-agent-env\Scripts\activate

# Clone and install
git clone https://github.com/yourusername/local-agent.git
cd local-agent
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development

# Test installation
python3 local-agent/cli.py status
```

### Method 3: Docker Installation

```bash
# Clone repository
git clone https://github.com/yourusername/local-agent.git
cd local-agent

# Start Qdrant server
docker-compose up -d

# Build and run local-agent
docker build -t local-agent .
docker run -v ~/Documents:/data local-agent index /data
```

## Platform-Specific Instructions

### macOS Installation

#### Prerequisites
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11+
brew install python@3.11

# Install Tesseract for OCR (optional)
brew install tesseract

# Install Docker (optional, for Qdrant)
brew install docker
```

#### Installation Steps
```bash
# Clone repository
git clone https://github.com/yourusername/local-agent.git
cd local-agent

# Install dependencies
pip3 install -r requirements.txt

# Install additional dependencies
pip3 install pypdfium2 pdfminer.six beautifulsoup4 lxml psutil

# Test installation
python3 local-agent/cli.py status
```

#### Apple Silicon Optimization
```bash
# Verify MPS support
python3 -c "import torch; print('MPS available:', torch.backends.mps.is_available())"

# If MPS is available, embeddings will automatically use GPU acceleration
```

### Ubuntu/Debian Installation

#### Prerequisites
```bash
# Update package list
sudo apt update

# Install Python 3.11+
sudo apt install python3.11 python3.11-pip python3.11-venv

# Install system dependencies
sudo apt install build-essential libssl-dev libffi-dev

# Install Tesseract for OCR (optional)
sudo apt install tesseract-ocr tesseract-ocr-eng

# Install Docker (optional, for Qdrant)
sudo apt install docker.io docker-compose
```

#### Installation Steps
```bash
# Clone repository
git clone https://github.com/yourusername/local-agent.git
cd local-agent

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pypdfium2 pdfminer.six beautifulsoup4 lxml psutil

# Test installation
python3 local-agent/cli.py status
```

### Windows Installation

#### Prerequisites
```bash
# Install Python 3.11+ from python.org
# Install Git from git-scm.com
# Install Visual Studio Build Tools (for compiling dependencies)
```

#### Installation Steps
```powershell
# Clone repository
git clone https://github.com/yourusername/local-agent.git
cd local-agent

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pypdfium2 pdfminer.six beautifulsoup4 lxml psutil

# Test installation
python local-agent\cli.py status
```

## Dependency Installation

### Core Dependencies
```bash
# Essential packages
pip install qdrant-client sentence-transformers ollama

# For best performance
pip install torch torchvision torchaudio  # PyTorch with CUDA/MPS support
```

### Optional Dependencies

#### PDF Processing
```bash
# Fast PDF parsing
pip install pypdfium2

# Fallback PDF parsing
pip install pdfminer.six

# Legacy PDF support
pip install PyPDF2
```

#### HTML Processing
```bash
# Fast HTML parsing
pip install beautifulsoup4 lxml

# Alternative HTML parser
pip install html5lib
```

#### Document Processing
```bash
# Microsoft Word documents
pip install python-docx

# Rich Text Format
pip install python-docx  # Also handles RTF
```

#### Image Processing (OCR)
```bash
# Image processing
pip install Pillow

# OCR engine
pip install pytesseract

# System Tesseract installation required
# macOS: brew install tesseract
# Ubuntu: sudo apt install tesseract-ocr
# Windows: Download from GitHub releases
```

#### System Monitoring
```bash
# Process and system monitoring
pip install psutil
```

#### Development Dependencies
```bash
# Code formatting
pip install black isort

# Testing
pip install pytest pytest-cov

# Type checking
pip install mypy

# Linting
pip install flake8
```

## Configuration Setup

### Basic Configuration
```bash
# Create config file
cp config.yaml.example config.yaml

# Edit configuration
nano config.yaml  # or use your preferred editor
```

### Environment Variables
```bash
# Optional: Set custom paths
export LOCAL_AGENT_STORAGE_PATH="/path/to/storage"
export LOCAL_AGENT_QDRANT_URL="http://localhost:6333"

# Add to your shell profile
echo 'export LOCAL_AGENT_STORAGE_PATH="/path/to/storage"' >> ~/.bashrc
echo 'export LOCAL_AGENT_QDRANT_URL="http://localhost:6333"' >> ~/.bashrc
source ~/.bashrc
```

### Qdrant Server Setup (Optional)
```bash
# Start Qdrant with Docker
docker-compose up -d

# Verify Qdrant is running
curl http://localhost:6333/collections

# Check logs
docker-compose logs qdrant
```

## Verification and Testing

### Basic Functionality Test
```bash
# Check system status
python3 local-agent/cli.py status

# Test indexing a directory
mkdir -p test_docs
echo "This is a test document about machine learning" > test_docs/test1.txt
echo "Another document about Python programming" > test_docs/test2.txt
python3 local-agent/cli.py bfs-index test_docs

# Test search
python3 local-agent/cli.py find "machine learning" --show-context
python3 local-agent/cli.py find "Python" --show-context

# Clean up
rm -rf test_docs
```

### Performance Test
```bash
# Run benchmark suite
python3 -m search.bench --paths ~/Documents

# Test indexing with custom parameters
python3 local-agent/cli.py bfs-index ~/Documents \
  --max-tokens 1500 \
  --overlap 100 \
  --max-items 500
```

### OCR Test (if Tesseract is installed)
```bash
# Test OCR functionality
python3 local-agent/cli.py bfs-index ~/Pictures --ocr
```

## Troubleshooting Installation

### Common Issues

#### Python Version Issues
```bash
# Check Python version
python3 --version

# If version is too old, install newer version
# macOS: brew install python@3.11
# Ubuntu: sudo apt install python3.11
# Windows: Download from python.org
```

#### Permission Issues
```bash
# Install with user flag
pip install --user -r requirements.txt

# Or use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Compilation Errors
```bash
# Install build tools
# macOS: xcode-select --install
# Ubuntu: sudo apt install build-essential
# Windows: Install Visual Studio Build Tools

# Try installing pre-compiled wheels
pip install --only-binary=all -r requirements.txt
```

#### Memory Issues
```bash
# Reduce batch sizes in config
echo "batch_size: 512" >> config.yaml
echo "upsert_batch_size: 2000" >> config.yaml
echo "num_parsers: 2" >> config.yaml
```

#### Network Issues
```bash
# Use alternative package index
pip install -i https://pypi.org/simple/ -r requirements.txt

# Or use conda
conda install -c conda-forge sentence-transformers
```

### Getting Help

#### Check Logs
```bash
# Enable debug logging
python3 local-agent/cli.py --verbose status

# Check system logs
tail -f ~/.local-agent/logs/system.log
```

#### System Information
```bash
# Collect system info for debugging
python3 -c "
import sys, platform
print(f'Python: {sys.version}')
print(f'Platform: {platform.platform()}')
print(f'Architecture: {platform.architecture()}')
print(f'Processor: {platform.processor()}')
"
```

#### Dependency Check
```bash
# Check installed packages
pip list | grep -E "(qdrant|sentence|torch|ollama)"

# Check optional dependencies
python3 -c "
try:
    import pypdfium2; print('✓ pypdfium2')
except: print('✗ pypdfium2')

try:
    import bs4; print('✓ beautifulsoup4')
except: print('✗ beautifulsoup4')

try:
    import psutil; print('✓ psutil')
except: print('✗ psutil')
"
```

## Next Steps

After successful installation:

1. **Read the [Quick Start Guide](README.md#quick-start)**
2. **Configure your system** (optional): Edit `config.yaml`
3. **Start Qdrant server**: `docker-compose up -d`
4. **Check system status**: `python3 local-agent/cli.py status`
5. **Index your documents**: `python3 local-agent/cli.py bfs-index ~/Documents`
6. **Start searching**: `python3 local-agent/cli.py find "your search term"`

For advanced usage, see the [Architecture Guide](ARCHITECTURE.md) and [README](README.md).

## 🎯 What Works Now

**Currently Implemented:**
- ✅ BFS streaming indexer (`bfs-index` command)
- ✅ Hybrid search (`find` command)
- ✅ System status check (`status` command)
- ✅ Database reset (`reset-db` command)
- ✅ PDF, DOCX, HTML, Markdown, Code file support
- ✅ OCR for images (requires Tesseract)
- ✅ Apple Silicon MPS acceleration
- ✅ Qdrant vector database integration
- ✅ SQLite FTS5 lexical search

**Coming Soon:**
- 🚧 LLM integration for Q&A (`ask` command placeholder exists)
- 🚧 Auto-indexing daemon with file watching
- 🚧 System-wide root scanning with safety features
- 🚧 Web UI and REST API
- 🚧 Real-time file updates

See [README.md](README.md#current-status--roadmap) for the complete roadmap.
