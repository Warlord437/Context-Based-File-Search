"""
BFS streaming indexer with checkpointing and robust PDF pipeline.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
import hashlib

from .config import get_config
from .storage import create_storage
from .types import Chunk, FrontierState, IndexStats
from .ids import file_id, chunk_id, generate_file_sha256, get_file_stats

logger = logging.getLogger(__name__)

class BFSIndexer:
    """BFS streaming indexer with checkpointing."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config()
        self.qdrant, self.catalog = create_storage(self.config)
        self.frontier_path = Path(self.config["paths"]["frontier"])
        self.max_items = self.config["index"].get("max_items", 1000)
        self.exclude_patterns = self.config["index"]["exclude_patterns"]
        self.allow_exts = set(self.config["index"]["allow_exts"])
        self.max_pdf_pages = self.config["index"]["max_pdf_pages"]
        self.extraction_timeout = self.config["index"]["extraction_timeout"]
        
        # Stats tracking
        self.stats = IndexStats()
    
    def run_bfs_slice(self, roots: List[str], max_items: int = None) -> IndexStats:
        """Run one BFS slice with checkpointing."""
        max_items = max_items or self.max_items
        
        # Load or create frontier
        frontier = self._load_frontier()
        
        # Add roots to frontier if empty
        if not frontier.queue:
            for root in roots:
                if Path(root).exists():
                    frontier.queue.append(root)
                    logger.info(f"Added root to frontier: {root}")
        
        # Process one level
        processed_count = 0
        current_level = []
        
        # Get current level items
        while frontier.queue and processed_count < max_items:
            current_level.append(frontier.queue.pop(0))
            processed_count += 1
        
        logger.info(f"Processing {len(current_level)} items from frontier")
        
        # Process current level
        for item_path in current_level:
            try:
                self._process_item(item_path, frontier)
            except Exception as e:
                logger.error(f"Error processing {item_path}: {e}")
                frontier.errors.append(f"{item_path}: {str(e)}")
                self.stats.errors += 1
        
        # Save frontier state
        self._save_frontier(frontier)
        
        return self.stats
    
    def _process_item(self, item_path: str, frontier: FrontierState):
        """Process a single file or directory."""
        path = Path(item_path)
        
        if not path.exists():
            logger.warning(f"Path does not exist: {item_path}")
            return
        
        # Check if already processed
        device_inode = (path.stat().st_dev, path.stat().st_ino)
        if item_path in frontier.seen and frontier.seen[item_path] == device_inode:
            logger.debug(f"Skipping already processed: {item_path}")
            return
        
        if path.is_file():
            self._process_file(item_path)
            frontier.processed_files += 1
            self.stats.files_processed += 1
        elif path.is_dir():
            self._process_directory(item_path, frontier)
            frontier.processed_dirs += 1
        
        # Mark as seen
        frontier.seen[item_path] = device_inode
    
    def _process_file(self, file_path: str):
        """Process a single file."""
        path = Path(file_path)
        
        logger.info(f"Processing file: {file_path}")
        
        # Check file extension
        if path.suffix.lower() not in self.allow_exts:
            logger.info(f"Skipping unsupported file (extension {path.suffix.lower()}): {file_path}")
            self.stats.files_skipped += 1
            return
        
        # Check exclude patterns
        if self._should_exclude(file_path):
            logger.info(f"Excluded by pattern: {file_path}")
            self.stats.files_skipped += 1
            return
        
        # Get file stats
        stats = get_file_stats(file_path)
        if not stats:
            logger.warning(f"Could not get stats for: {file_path}")
            return
        
        # Generate file ID and check if unchanged
        fid = file_id(file_path, stats["mtime"], stats["size"])
        
        # Check if file already exists and is unchanged
        existing_sha256 = self._get_existing_sha256(fid)
        if existing_sha256:
            current_sha256 = generate_file_sha256(file_path)
            if current_sha256 == existing_sha256:
                logger.debug(f"File unchanged, skipping: {file_path}")
                self.stats.files_skipped += 1
                return
        
        # Extract text
        text = self._extract_text(file_path)
        if not text:
            logger.warning(f"No text extracted from: {file_path}")
            self.stats.files_skipped += 1
            return
        
        # Generate new SHA256
        new_sha256 = hashlib.sha256(text.encode()).hexdigest()
        
        # Update file metadata
        self.catalog.upsert_file(str(file_path), stats["size"], stats["mtime"], new_sha256)
        
        # Chunk text
        chunks = self._chunk_text(text, file_path, fid)
        
        # Insert chunks into catalog
        self.catalog.insert_chunks(fid, chunks)
        
        # Generate embeddings and upsert to Qdrant
        self._embed_and_upsert(chunks)
        
        # Insert into FTS
        for chunk in chunks:
            self.catalog.fts_insert(chunk.chunk_id, chunk.text, chunk.path)
        
        self.stats.chunks_created += len(chunks)
        logger.info(f"Processed file: {file_path} ({len(chunks)} chunks)")
    
    def _process_directory(self, dir_path: str, frontier: FrontierState):
        """Process directory and add children to frontier."""
        try:
            path = Path(dir_path)
            
            # Check exclude patterns
            if self._should_exclude(dir_path):
                logger.debug(f"Excluded directory: {dir_path}")
                return
            
            # Add children to frontier
            try:
                children_added = 0
                for child in path.iterdir():
                    child_str = str(child)
                    
                    # Skip hidden files/directories
                    if child.name.startswith('.'):
                        continue
                    
                    # Skip if should be excluded
                    if self._should_exclude(child_str):
                        continue
                    
                    frontier.queue.append(child_str)
                    children_added += 1
                
                logger.info(f"Added {children_added} children from directory: {dir_path}")
                    
            except PermissionError:
                logger.warning(f"Permission denied accessing: {dir_path}")
            except OSError as e:
                logger.warning(f"Error reading directory {dir_path}: {e}")
                
        except Exception as e:
            logger.error(f"Error processing directory {dir_path}: {e}")
    
    def _extract_text(self, file_path: str) -> Optional[str]:
        """Extract text from file with robust pipeline."""
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        try:
            if suffix == '.txt':
                return self._extract_txt(file_path)
            elif suffix == '.md':
                return self._extract_md(file_path)
            elif suffix == '.pdf':
                return self._extract_pdf(file_path)
            elif suffix in ['.html', '.htm']:
                return self._extract_html(file_path)
            elif suffix in ['.docx', '.doc']:
                return self._extract_docx(file_path)
            else:
                # Try as plain text
                return self._extract_txt(file_path)
                
        except Exception as e:
            logger.error(f"Text extraction failed for {file_path}: {e}")
            return None
    
    def _extract_txt(self, file_path: str) -> str:
        """Extract text from plain text file."""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def _extract_md(self, file_path: str) -> str:
        """Extract text from Markdown file."""
        return self._extract_txt(file_path)  # Same as txt for now
    
    def _extract_pdf(self, file_path: str) -> Optional[str]:
        """Extract text from PDF with robust pipeline."""
        text_parts = []
        
        # Try PyMuPDF first (fastest)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            
            for page_num in range(min(len(doc), self.max_pdf_pages)):
                page = doc.load_page(page_num)
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
            
            doc.close()
            
            if text_parts:
                return '\n\n'.join(text_parts)
                
        except ImportError:
            logger.debug("PyMuPDF not available")
        except Exception as e:
            logger.debug(f"PyMuPDF extraction failed: {e}")
        
        # Try pypdfium2
        try:
            import pypdfium2 as pdfium
            
            pdf = pdfium.PdfDocument(file_path)
            
            for page_num in range(min(len(pdf), self.max_pdf_pages)):
                page = pdf[page_num]
                textpage = page.get_textpage()
                
                try:
                    text = textpage.get_text_bounded()
                    if text.strip():
                        text_parts.append(text)
                finally:
                    textpage.close()
                    page.close()
            
            pdf.close()
            
            if text_parts:
                return '\n\n'.join(text_parts)
                
        except ImportError:
            logger.debug("pypdfium2 not available")
        except Exception as e:
            logger.debug(f"pypdfium2 extraction failed: {e}")
        
        # Try pdfminer as fallback
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(file_path, maxpages=self.max_pdf_pages)
            if text.strip():
                return text
                
        except ImportError:
            logger.debug("pdfminer not available")
        except Exception as e:
            logger.debug(f"pdfminer extraction failed: {e}")
        
        logger.warning(f"All PDF extraction methods failed for: {file_path}")
        return None
    
    def _extract_html(self, file_path: str) -> Optional[str]:
        """Extract text from HTML file."""
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'lxml')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            # Get text
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except ImportError:
            logger.debug("BeautifulSoup not available, using plain text extraction")
            return self._extract_txt(file_path)
        except Exception as e:
            logger.error(f"HTML extraction failed for {file_path}: {e}")
            return None
    
    def _extract_docx(self, file_path: str) -> Optional[str]:
        """Extract text from DOCX file."""
        try:
            from docx import Document
            
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            return '\n'.join(paragraphs)
            
        except ImportError:
            logger.debug("python-docx not available")
            return None
        except Exception as e:
            logger.error(f"DOCX extraction failed for {file_path}: {e}")
            return None
    
    def _chunk_text(self, text: str, file_path, file_id: str) -> List[Chunk]:
        """Chunk text into overlapping segments."""
        max_tokens = self.config["index"]["max_tokens"]
        overlap = self.config["index"]["overlap"]
        
        # Simple tokenization (approximate)
        words = text.split()
        chunks = []
        
        i = 0
        chunk_idx = 0
        
        while i < len(words):
            # Take chunk of words
            chunk_words = words[i:i + max_tokens]
            chunk_text = ' '.join(chunk_words)
            
            if not chunk_text.strip():
                break
            
            # Create chunk
            chunk = Chunk(
                path=str(file_path),
                file_id=file_id,
                chunk_id=chunk_id(file_id, chunk_idx),
                text=chunk_text,
                token_start=i,
                token_end=i + len(chunk_words),
                mtime=int(Path(file_path).stat().st_mtime),
                sha256=hashlib.sha256(chunk_text.encode()).hexdigest(),
                idx=chunk_idx
            )
            
            chunks.append(chunk)
            chunk_idx += 1
            
            # Move forward with overlap
            i += max_tokens - overlap
        
        return chunks
    
    def _embed_and_upsert(self, chunks: List[Chunk]):
        """Generate embeddings and upsert to Qdrant."""
        try:
            from sentence_transformers import SentenceTransformer
            import torch
            
            # Load model (with MPS support if available)
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
            
            # Prepare texts
            texts = [chunk.text for chunk in chunks]
            
            # Generate embeddings in batches
            batch_size = self.config["index"]["embed_batch"]
            embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_embeddings = model.encode(batch_texts, convert_to_tensor=False)
                embeddings.extend(batch_embeddings.tolist())
            
            # Prepare points for Qdrant
            points = []
            for chunk, embedding in zip(chunks, embeddings):
                points.append({
                    "id": chunk.chunk_id,
                    "vector": embedding,
                    "payload": {
                        "path": chunk.path,
                        "file_id": chunk.file_id,
                        "chunk_id": chunk.chunk_id,
                        "idx": chunk.idx
                    }
                })
            
            # Upsert to Qdrant
            self.qdrant.upsert_vectors(points)
            
        except ImportError:
            logger.error("sentence-transformers not available")
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
    
    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded."""
        from fnmatch import fnmatch
        
        for pattern in self.exclude_patterns:
            if fnmatch(path, pattern):
                return True
        return False
    
    def _get_existing_sha256(self, file_id: str) -> Optional[str]:
        """Get existing SHA256 for file if it exists."""
        try:
            cursor = self.catalog.conn.execute(
                "SELECT sha256 FROM files WHERE file_id = ?", (file_id,)
            )
            row = cursor.fetchone()
            return row["sha256"] if row else None
        except Exception:
            return None
    
    def _load_frontier(self) -> FrontierState:
        """Load frontier state from disk."""
        try:
            if self.frontier_path.exists():
                with open(self.frontier_path, 'r') as f:
                    data = json.load(f)
                
                # Convert seen dict keys back to strings (JSON keys are strings)
                seen = {k: tuple(v) for k, v in data.get("seen", {}).items()}
                
                return FrontierState(
                    queue=data.get("queue", []),
                    seen=seen,
                    processed_files=data.get("processed_files", 0),
                    processed_dirs=data.get("processed_dirs", 0),
                    errors=data.get("errors", [])
                )
        except Exception as e:
            logger.warning(f"Failed to load frontier: {e}")
        
        return FrontierState(queue=[], seen={})
    
    def _save_frontier(self, frontier: FrontierState):
        """Save frontier state to disk."""
        try:
            self.frontier_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "queue": frontier.queue,
                "seen": {str(k): list(v) for k, v in frontier.seen.items()},
                "processed_files": frontier.processed_files,
                "processed_dirs": frontier.processed_dirs,
                "errors": frontier.errors
            }
            
            with open(self.frontier_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save frontier: {e}")


def run_bfs_slice(roots: List[str], **kwargs) -> IndexStats:
    """Run one BFS slice with given parameters."""
    config = get_config()
    
    # Override config with kwargs
    for key, value in kwargs.items():
        if key in config:
            config[key] = value
        elif key in config.get("index", {}):
            config["index"][key] = value
    
    indexer = BFSIndexer(config)
    
    start_time = time.time()
    stats = indexer.run_bfs_slice(roots, kwargs.get("max_items", 1000))
    stats.duration_seconds = time.time() - start_time
    
    logger.info(f"BFS slice completed: {stats.files_processed} files, {stats.chunks_created} chunks, {stats.duration_seconds:.2f}s")
    
    return stats


def run_complete_index(roots: List[str], **kwargs) -> IndexStats:
    """Run complete indexing of all files in roots."""
    config = get_config()
    
    # Override config with kwargs
    for key, value in kwargs.items():
        if key in config:
            config[key] = value
        elif key in config.get("index", {}):
            config["index"][key] = value
    
    indexer = BFSIndexer(config)
    
    start_time = time.time()
    
    # Run BFS slices until all files are processed
    total_stats = IndexStats()
    max_items_per_slice = kwargs.get("max_items_per_slice", 1000)
    
    # Clear frontier to start fresh
    frontier_path = Path(config["paths"]["frontier"])
    if frontier_path.exists():
        frontier_path.unlink()
        logger.info("Cleared existing frontier for fresh start")
    
    while True:
        # Run one slice
        slice_stats = indexer.run_bfs_slice(roots, max_items_per_slice)
        
        # Accumulate stats
        total_stats.files_processed += slice_stats.files_processed
        total_stats.chunks_created += slice_stats.chunks_created
        total_stats.files_skipped += slice_stats.files_skipped
        total_stats.errors += slice_stats.errors
        
        # Load current frontier to check if there are more items to process
        frontier = indexer._load_frontier()
        
        if not frontier.queue:
            logger.info("No more items to process. Indexing complete.")
            break
        
        # If no files were processed AND no items were added to frontier, we're done
        if slice_stats.files_processed == 0 and len(frontier.queue) == 0:
            logger.info("No files processed and no items in queue. Indexing complete.")
            break
        
        logger.info(f"Processed {slice_stats.files_processed} files, {len(frontier.queue)} items remaining in queue")
    
    total_stats.duration_seconds = time.time() - start_time
    
    logger.info(f"Complete indexing finished: {total_stats.files_processed} files, {total_stats.chunks_created} chunks, {total_stats.duration_seconds:.2f}s")
    
    return total_stats


if __name__ == "__main__":
    # Test the indexer
    import sys
    
    roots = [sys.argv[1]] if len(sys.argv) > 1 else ["/Users/tathagatasaha/Desktop/localagentandcliwithvectordb"]
    
    print(f"Testing BFS indexer with roots: {roots}")
    
    stats = run_bfs_slice(roots, max_items=10)
    
    print(f"Results:")
    print(f"  Files processed: {stats.files_processed}")
    print(f"  Chunks created: {stats.chunks_created}")
    print(f"  Files skipped: {stats.files_skipped}")
    print(f"  Errors: {stats.errors}")
    print(f"  Duration: {stats.duration_seconds:.2f}s")
