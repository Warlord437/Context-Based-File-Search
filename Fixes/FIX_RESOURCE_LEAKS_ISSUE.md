# 🔧 Resource Leaks Issue - Analysis & Fix Plan

## The Problem Explained

### What Are Resource Leaks?

Resources are things your program uses that need to be cleaned up:
- **File handles** - Open files that need to be closed
- **Database connections** - Connections that need to be closed
- **PDF documents** - Documents that need to be closed
- **Memory** - Objects that hold memory

**Resource Leak**: When you open a resource but forget to close it, it stays open forever, consuming memory and system resources.

### Current Problems in the Code

#### Problem 1: PDF Documents Not Always Closed

**Current Code:**
```python
def _extract_pdf(self, file_path: str):
    try:
        doc = fitz.open(file_path)  # Opens PDF
        # ... process pages ...
        doc.close()  # ✅ Closes if everything works
    except Exception as e:
        logger.debug(f"Failed: {e}")
        # ❌ If error occurs, doc.close() never called!
        # PDF document stays open in memory
```

**What's Wrong:**
- If exception occurs before `doc.close()`, PDF stays open
- Memory leak - PDF document consumes memory
- File handle leak - file stays locked
- After many errors, system runs out of resources

#### Problem 2: Database Connections Not Always Closed

**Current Code:**
```python
# In indexer.py
def __init__(self, config):
    self.qdrant, self.catalog = create_storage(config)
    # Catalog has a database connection
    # ❌ Never explicitly closed!

# In retriever.py
def __init__(self, config):
    self.qdrant, self.catalog = create_storage(config)
    # ❌ Connection stays open forever
```

**What's Wrong:**
- Database connections are created but never closed
- SQLite connections can lock database files
- After many operations, too many connections open
- Database file might be locked for other processes

#### Problem 3: PDF Extraction Has Multiple Exit Points

**Current Code:**
```python
def _extract_pdf(self, file_path: str):
    # Try PyMuPDF
    try:
        doc = fitz.open(file_path)
        # ... process ...
        doc.close()  # ✅ Closes
        return text  # Returns early
    except Exception:
        pass  # ❌ If exception, doc might not be closed
    
    # Try pypdfium2
    try:
        pdf = pdfium.PdfDocument(file_path)
        # ... process ...
        pdf.close()  # ✅ Closes
        return text  # Returns early
    except Exception:
        pass  # ❌ If exception, pdf might not be closed
```

**What's Wrong:**
- Multiple return points - easy to miss cleanup
- Exceptions can skip cleanup code
- No guarantee resources are closed

---

## Real-World Impact

### Scenario 1: Indexing 1000 PDFs with Errors

**What Happens:**
```python
# Index 1000 PDFs, 50 have errors
for pdf_file in pdf_files:
    text = indexer._extract_pdf(pdf_file)
    # 50 PDFs fail with exceptions
    # 50 PDF documents stay open in memory
    # 50 file handles locked
    # Memory usage grows: 50 × 10MB = 500MB leaked!
```

**Result:**
- Memory usage keeps growing
- System slows down
- Eventually runs out of memory
- Application crashes

### Scenario 2: Long-Running Indexing Process

**What Happens:**
```python
# Index files for hours
indexer = BFSIndexer(config)
# Database connection opened
# ... hours of indexing ...
# Connection never closed
# Multiple indexers = multiple connections
# Database file locked
```

**Result:**
- Database connections accumulate
- Database file locked
- Can't access database from other processes
- System resources exhausted

### Scenario 3: Concurrent Operations

**What Happens:**
```python
# Multiple operations at once
Operation 1: Opens PDF, fails, doesn't close
Operation 2: Opens PDF, fails, doesn't close
Operation 3: Opens PDF, fails, doesn't close
# ... 100 operations ...
# 100 PDFs open, 100 file handles locked
```

**Result:**
- System runs out of file handles
- "Too many open files" error
- Application crashes

---

## The Fix Plan

### Solution 1: Use Context Managers for PDF Documents

**Create PDF context managers:**
```python
@contextmanager
def open_pdf_pymupdf(file_path: str):
    """Context manager for PyMuPDF documents."""
    doc = None
    try:
        doc = fitz.open(file_path)
        yield doc
    finally:
        if doc:
            doc.close()  # Always closes, even on error
```

**Usage:**
```python
def _extract_pdf(self, file_path: str):
    with open_pdf_pymupdf(file_path) as doc:
        # Use doc - auto-closes on exit
        text = doc.get_text()
```

### Solution 2: Use Try-Finally for Guaranteed Cleanup

**Before:**
```python
doc = fitz.open(file_path)
# ... process ...
doc.close()  # Might not execute if error
```

**After:**
```python
doc = None
try:
    doc = fitz.open(file_path)
    # ... process ...
finally:
    if doc:
        doc.close()  # Always executes
```

### Solution 3: Add Context Manager Support to Catalog

**Add to Catalog class:**
```python
def __enter__(self):
    """Context manager entry."""
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    """Context manager exit - closes connection."""
    self.close()
```

**Usage:**
```python
with create_storage(config) as (qdrant, catalog):
    # Use catalog
    # Auto-closes on exit
```

### Solution 4: Implement Proper Cleanup in Indexer/Retriever

**Add cleanup methods:**
```python
class BFSIndexer:
    def __del__(self):
        """Cleanup on deletion."""
        self.close()
    
    def close(self):
        """Close all resources."""
        if hasattr(self, 'catalog'):
            self.catalog.close()
```

---

## Recommended Changes

### Change 1: Fix PDF Extraction with Context Managers

**File**: `search/indexer.py`  
**Location**: `_extract_pdf()` method

**Before:**
```python
doc = fitz.open(file_path)
# ... process ...
doc.close()  # Might not execute
```

**After:**
```python
doc = None
try:
    doc = fitz.open(file_path)
    # ... process ...
finally:
    if doc:
        doc.close()  # Always executes
```

### Change 2: Add Context Manager to Catalog

**File**: `search/storage.py`  
**Location**: `Catalog` class

**Add:**
```python
def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
```

### Change 3: Add Cleanup to Indexer/Retriever

**Files**: `search/indexer.py`, `search/retriever.py`

**Add:**
```python
def close(self):
    """Close all resources."""
    if hasattr(self, 'catalog') and self.catalog:
        self.catalog.close()
```

### Change 4: Use Context Managers Where Possible

**Update all PDF operations to use try-finally or context managers**

---

## Files to Modify

### 1. `search/indexer.py`
- ✅ Fix `_extract_pdf()` - Use try-finally for all PDF libraries
- ✅ Add `close()` method to `BFSIndexer` class
- ✅ Add `__enter__` and `__exit__` for context manager support

### 2. `search/storage.py`
- ✅ Add `__enter__` and `__exit__` to `Catalog` class
- ✅ Ensure `close()` is always called

### 3. `search/retriever.py`
- ✅ Add `close()` method to `HybridRetriever` class

### 4. `FIXES.md`
- ✅ Document the fix

---

## Benefits of the Fix

✅ **No Memory Leaks** - All resources properly closed  
✅ **No File Handle Leaks** - Files always closed  
✅ **No Database Locks** - Connections properly closed  
✅ **Better Resource Management** - System resources freed  
✅ **Production Ready** - Handles long-running processes  

---

## Implementation Order

1. **Step 1**: Fix PDF extraction with try-finally blocks
2. **Step 2**: Add context manager support to Catalog
3. **Step 3**: Add cleanup methods to Indexer/Retriever
4. **Step 4**: Test resource cleanup
5. **Step 5**: Update documentation

---

**Status**: 📋 **PLAN READY**  
**Next Step**: Implement the changes
