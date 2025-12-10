#!/usr/bin/env python3
"""
Setup script for Local-Agent
"""

from setuptools import setup, find_packages
import os

# Read README for long description
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Read requirements
def read_requirements():
    with open("requirements.txt", "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="local-agent",
    version="1.0.0",
    author="Local-Agent Team",
    author_email="your-email@example.com",
    description="High-performance document search engine for your entire computer",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/local-agent",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/local-agent/issues",
        "Source": "https://github.com/yourusername/local-agent",
        "Documentation": "https://github.com/yourusername/local-agent/wiki",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Office/Business",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Text Processing :: Indexing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Natural Language :: English",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pre-commit>=3.0.0",
        ],
        "ocr": [
            "pytesseract>=0.3.10",
            "Pillow>=9.0.0",
        ],
        "fast": [
            "pypdfium2>=4.0.0",
            "beautifulsoup4>=4.11.0",
            "lxml>=4.9.0",
        ],
        "monitoring": [
            "psutil>=5.9.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "local-agent=local_agent.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "local_agent": [
            "*.yaml",
            "*.yml",
            "*.json",
        ],
    },
    keywords=[
        "search",
        "documents",
        "vector-database",
        "ai",
        "embeddings",
        "pdf",
        "text-processing",
        "local-search",
        "qdrant",
        "semantic-search",
    ],
    zip_safe=False,
)
