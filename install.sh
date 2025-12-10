#!/bin/bash

# Local-Agent Installation Script
# This script automates the installation process for Local-Agent

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python version
check_python() {
    print_status "Checking Python version..."
    
    if ! command_exists python3; then
        print_error "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ $PYTHON_MAJOR -lt 3 ] || ([ $PYTHON_MAJOR -eq 3 ] && [ $PYTHON_MINOR -lt 8 ]); then
        print_error "Python 3.8 or higher is required. Current version: $PYTHON_VERSION"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION detected"
}

# Check if we're in the right directory
check_directory() {
    if [ ! -f "local-agent/cli.py" ]; then
        print_error "Please run this script from the local-agent root directory"
        exit 1
    fi
    print_success "Found local-agent directory"
}

# Install system dependencies
install_system_deps() {
    print_status "Installing system dependencies..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command_exists brew; then
            print_status "Installing dependencies with Homebrew..."
            brew install tesseract || print_warning "Failed to install tesseract (OCR will be disabled)"
        else
            print_warning "Homebrew not found. Please install tesseract manually for OCR support."
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command_exists apt-get; then
            print_status "Installing dependencies with apt..."
            sudo apt-get update
            sudo apt-get install -y tesseract-ocr tesseract-ocr-eng || print_warning "Failed to install tesseract (OCR will be disabled)"
        elif command_exists yum; then
            print_status "Installing dependencies with yum..."
            sudo yum install -y tesseract || print_warning "Failed to install tesseract (OCR will be disabled)"
        else
            print_warning "Package manager not found. Please install tesseract manually for OCR support."
        fi
    else
        print_warning "Unsupported operating system. Please install tesseract manually for OCR support."
    fi
}

# Create virtual environment
create_venv() {
    print_status "Creating virtual environment..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_success "Virtual environment created"
    else
        print_warning "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    print_success "Virtual environment activated"
}

# Install Python dependencies
install_python_deps() {
    print_status "Installing Python dependencies..."
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install core dependencies
    pip install -r requirements.txt
    
    # Install optional dependencies for best performance
    print_status "Installing optional dependencies for enhanced performance..."
    pip install pypdfium2 pdfminer.six beautifulsoup4 lxml psutil || print_warning "Some optional dependencies failed to install"
    
    print_success "Python dependencies installed"
}

# Install development dependencies (optional)
install_dev_deps() {
    if [ "$1" = "--dev" ]; then
        print_status "Installing development dependencies..."
        pip install -r requirements-dev.txt
        print_success "Development dependencies installed"
    fi
}

# Setup configuration
setup_config() {
    print_status "Setting up configuration..."
    
    if [ ! -f "config.yaml" ]; then
        cp config.yaml.example config.yaml
        print_success "Configuration file created from template"
    else
        print_warning "Configuration file already exists"
    fi
}

# Test installation
test_installation() {
    print_status "Testing installation..."
    
    # Test CLI
    if python3 local-agent/cli.py status > /dev/null 2>&1; then
        print_success "CLI test passed"
    else
        print_error "CLI test failed"
        exit 1
    fi
    
    # Test basic indexing
    echo "This is a test document" > test.txt
    if python3 local-agent/cli.py index test.txt > /dev/null 2>&1; then
        print_success "Indexing test passed"
    else
        print_error "Indexing test failed"
        exit 1
    fi
    
    # Test search
    if python3 local-agent/cli.py find "test document" > /dev/null 2>&1; then
        print_success "Search test passed"
    else
        print_error "Search test failed"
        exit 1
    fi
    
    # Clean up test file
    rm -f test.txt
}

# Start Qdrant (optional)
start_qdrant() {
    if [ "$1" = "--with-qdrant" ]; then
        print_status "Starting Qdrant server..."
        
        if command_exists docker; then
            if command_exists docker-compose; then
                docker-compose up -d
                print_success "Qdrant server started"
            else
                print_warning "docker-compose not found. Please start Qdrant manually."
            fi
        else
            print_warning "Docker not found. Please install Docker to use Qdrant server."
        fi
    fi
}

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dev           Install development dependencies"
    echo "  --with-qdrant   Start Qdrant server with Docker"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Basic installation"
    echo "  $0 --dev              # Install with development tools"
    echo "  $0 --with-qdrant      # Install and start Qdrant server"
    echo "  $0 --dev --with-qdrant # Full development setup"
}

# Main installation process
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    Local-Agent Installer                    ║"
    echo "║              High-Performance Document Search               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # Parse arguments
    INSTALL_DEV=false
    START_QDRANT=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev)
                INSTALL_DEV=true
                shift
                ;;
            --with-qdrant)
                START_QDRANT=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # Run installation steps
    check_directory
    check_python
    install_system_deps
    create_venv
    install_python_deps
    
    if [ "$INSTALL_DEV" = true ]; then
        install_dev_deps --dev
    fi
    
    setup_config
    test_installation
    
    if [ "$START_QDRANT" = true ]; then
        start_qdrant --with-qdrant
    fi
    
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗"
    echo -e "║                    Installation Complete!                    ║"
    echo -e "╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    print_success "Local-Agent has been successfully installed!"
    echo ""
    echo "Next steps:"
    echo "1. Activate the virtual environment: source venv/bin/activate"
    echo "2. Check system status: python3 local-agent/cli.py status"
    echo "3. Index your documents: python3 local-agent/cli.py index ~/Documents --system-wide"
    echo "4. Start searching: python3 local-agent/cli.py find 'your search term'"
    echo ""
    echo "For more information, see README.md"
    echo ""
}

# Run main function
main "$@"
