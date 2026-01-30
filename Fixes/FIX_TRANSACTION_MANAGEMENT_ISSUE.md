# 🔧 Transaction Management Issue - Analysis & Fix Plan

## The Problem Explained

### What is Transaction Management?

Think of a database transaction like a **"all or nothing"** operation:

- ✅ **Success**: All changes are saved together
- ❌ **Failure**: All changes are undone (rolled back)
- 🔒 **Isolation**: Other operations can't see partial changes

**Example**: Transferring money between bank accounts
- Step 1: Deduct $100 from Account A
- Step 2: Add $100 to Account B
- **If Step 2 fails, Step 1 must be undone!**

### Current Problems in the Code

#### Problem 1: No Rollback on Errors

**Current Code:**
```python
def upsert_file(self, path: str, size: int, mtime: int, sha256: str) -> str:
    try:
        self.conn.execute("INSERT INTO files ...")
        self.conn.commit()  # ✅ Commits immediately
        return file_id
    except Exception as e:
        logger.error(f"Failed: {e}")
        raise  # ❌ No rollback! Transaction might be left open
```

**What's Wrong:**
- If error occurs AFTER commit → Too late, data is saved
- If error occurs BEFORE commit → Transaction left open, database locked
- No rollback means partial changes might be saved

#### Problem 2: Multi-Step Operations Without Transaction Boundaries

**Current Code in `_process_file()`:**
```python
def _process_file(self, file_path: str):
    # Step 1: Insert file metadata
    self.catalog.upsert_file(...)  # ✅ Commits immediately
    
    # Step 2: Insert chunks
    self.catalog.insert_chunks(...)  # ✅ Commits immediately
    
    # Step 3: Generate embeddings (external operation)
    self._embed_and_upsert(chunks)  # ⚠️  If this fails...
    
    # Step 4: Insert FTS entries
    for chunk in chunks:
        self.catalog.fts_insert(...)  # ✅ Commits for each chunk
```

**What's Wrong:**
- If Step 3 (embeddings) fails → Steps 1 & 2 are already committed!
- Database has file and chunks, but no embeddings → **INCONSISTENT STATE**
- Can't rollback because commits already happened
- Database is now corrupted (missing data)

#### Problem 3: No Context Managers

**Current Code:**
```python
def insert_chunks(self, file_id: str, chunks: List[Chunk]) -> bool:
    try:
        self.conn.execute("DELETE FROM chunks ...")
        self.conn.executemany("INSERT INTO chunks ...")
        self.conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed: {e}")
        return False  # ❌ No rollback! Changes might be partial
```

**What's Wrong:**
- If error occurs, no automatic rollback
- Manual rollback is easy to forget
- Context managers would handle this automatically

#### Problem 4: Missing Rollback in Error Handlers

**Current Code:**
```python
def delete_file(self, file_id: str) -> bool:
    try:
        cursor = self.conn.execute("DELETE FROM files ...")
        self.conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed: {e}")
        return False  # ❌ No rollback! Delete might be partial
```

**What's Wrong:**
- If error occurs, transaction is left open
- Database might be locked
- No cleanup of partial changes

---

## Real-World Scenarios Where This Breaks

### Scenario 1: Indexing Fails Mid-Process

**What Happens:**
```python
# User indexes a file with 100 chunks
1. ✅ File metadata saved (committed)
2. ✅ Chunks 1-50 saved (committed)
3. ❌ Chunk 51 fails (disk full, memory error, etc.)
4. ❌ Embedding generation fails
5. ❌ FTS insertion skipped

# Result: Database has:
- ✅ File record
- ✅ Chunks 1-50
- ❌ Missing chunks 51-100
- ❌ Missing embeddings
- ❌ Missing FTS entries

# Database is CORRUPTED - inconsistent state!
```

### Scenario 2: Concurrent Operations

**What Happens:**
```python
# Two operations running at same time:
Operation 1: Delete file
Operation 2: Update file

# Without proper transactions:
1. Op1: DELETE FROM files WHERE file_id = 'X' (not committed yet)
2. Op2: UPDATE files SET ... WHERE file_id = 'X' (sees old data)
3. Op1: COMMIT (deletes file)
4. Op2: COMMIT (updates non-existent file)

# Result: Data corruption or errors
```

### Scenario 3: Power Failure

**What Happens:**
```python
# User is indexing files
1. ✅ File 1 saved (committed)
2. ✅ File 2 saved (committed)
3. ⚡ POWER FAILURE during File 3 processing

# Without rollback:
- File 3 is partially saved
- Database might be locked
- On restart, database is inconsistent
```

---

## The Fix Plan

### Solution 1: Add Context Managers for Transactions

**Create a transaction context manager:**
```python
@contextmanager
def transaction(self):
    """Context manager for database transactions."""
    try:
        yield self.conn
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise
```

**Usage:**
```python
def upsert_file(self, path: str, ...):
    with self.transaction():
        self.conn.execute("INSERT ...")
        # Auto-commits on success, auto-rollback on error
```

### Solution 2: Wrap Multi-Step Operations in Transactions

**Before:**
```python
def _process_file(self, file_path: str):
    self.catalog.upsert_file(...)  # Commits
    self.catalog.insert_chunks(...)  # Commits
    self._embed_and_upsert(chunks)  # External
    for chunk in chunks:
        self.catalog.fts_insert(...)  # Commits each
```

**After:**
```python
def _process_file(self, file_path: str):
    with self.catalog.transaction():
        # All steps in one transaction
        self.catalog.upsert_file(...)  # No commit yet
        self.catalog.insert_chunks(...)  # No commit yet
        # ... other operations
        # Auto-commits all at once, or rolls back all
```

### Solution 3: Add Rollback to All Error Handlers

**Before:**
```python
except Exception as e:
    logger.error(f"Failed: {e}")
    return False  # No rollback
```

**After:**
```python
except Exception as e:
    logger.error(f"Failed: {e}")
    self.conn.rollback()  # Always rollback on error
    return False
```

### Solution 4: Make Methods Transaction-Aware

**Option A: Methods that auto-commit (current behavior)**
```python
def upsert_file(self, ...):
    with self.transaction():
        # Auto-commits
```

**Option B: Methods that don't commit (for multi-step operations)**
```python
def upsert_file(self, ..., commit: bool = True):
    self.conn.execute(...)
    if commit:
        self.conn.commit()
    # Caller handles transaction
```

---

## Recommended Changes

### Change 1: Add Transaction Context Manager

**File**: `search/storage.py`  
**Location**: Add to `Catalog` class

```python
from contextlib import contextmanager

class Catalog:
    @contextmanager
    def transaction(self):
        """Context manager for database transactions with auto-rollback."""
        try:
            yield self.conn
            self.conn.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise
```

### Change 2: Update Methods to Use Transactions

**Files to Update**:
- `upsert_file()` - Wrap in transaction
- `delete_file()` - Wrap in transaction, add rollback
- `insert_chunks()` - Wrap in transaction
- `fts_insert()` - Wrap in transaction

**Example:**
```python
def upsert_file(self, path: str, size: int, mtime: int, sha256: str) -> str:
    file_id = self._generate_file_id(path, mtime, size)
    
    with self.transaction():
        self.conn.execute("""
            INSERT OR REPLACE INTO files ...
        """, (file_id, path, size, mtime, sha256))
        # Auto-commits on success, auto-rollback on error
    
    return file_id
```

### Change 3: Update Multi-Step Operations

**File**: `search/indexer.py`  
**Location**: `_process_file()` method

**Before:**
```python
def _process_file(self, file_path: str):
    self.catalog.upsert_file(...)  # Commits
    chunks = self._chunk_text(...)
    self.catalog.insert_chunks(...)  # Commits
    self._embed_and_upsert(chunks)
    for chunk in chunks:
        self.catalog.fts_insert(...)  # Commits each
```

**After:**
```python
def _process_file(self, file_path: str):
    # All database operations in one transaction
    with self.catalog.transaction():
        # Step 1: File metadata
        fid = self.catalog.upsert_file(..., commit=False)
        
        # Step 2: Chunks
        chunks = self._chunk_text(...)
        self.catalog.insert_chunks(fid, chunks, commit=False)
        
        # Step 3: FTS entries
        for chunk in chunks:
            self.catalog.fts_insert(chunk.chunk_id, chunk.text, chunk.path, commit=False)
    
    # Step 4: External operations (outside transaction)
    # If this fails, database is still consistent
    self._embed_and_upsert(chunks)
```

### Change 4: Add Commit Parameter to Methods

**Update method signatures:**
```python
def upsert_file(self, path: str, size: int, mtime: int, sha256: str, 
                commit: bool = True) -> str:
    """Upsert file with optional commit control."""
    with self.transaction() if commit else nullcontext():
        # ... operation
        if commit:
            self.conn.commit()
```

---

## Files to Modify

### 1. `search/storage.py`
- ✅ Add `transaction()` context manager to `Catalog` class
- ✅ Update `upsert_file()` - Use transaction
- ✅ Update `delete_file()` - Use transaction, add rollback
- ✅ Update `insert_chunks()` - Use transaction
- ✅ Update `fts_insert()` - Use transaction
- ✅ Add `commit` parameter to methods for multi-step operations

### 2. `search/indexer.py`
- ✅ Update `_process_file()` - Wrap database operations in transaction
- ✅ Keep external operations (embeddings) outside transaction

### 3. `FIXES.md`
- ✅ Document the fix
- ✅ Update status

---

## Benefits of the Fix

✅ **Data Integrity** - All-or-nothing operations  
✅ **Consistency** - Database never in partial state  
✅ **Error Recovery** - Automatic rollback on errors  
✅ **Concurrency** - Better handling of concurrent operations  
✅ **Reliability** - Survives crashes and power failures  

---

## Testing Plan

1. **Test Single Operation**: Verify commit/rollback works
2. **Test Multi-Step**: Verify all-or-nothing behavior
3. **Test Error Cases**: Verify rollback on errors
4. **Test Concurrency**: Verify no data corruption
5. **Test Recovery**: Verify database consistency after crashes

---

## Implementation Order

1. **Step 1**: Add transaction context manager
2. **Step 2**: Update single-step methods (upsert_file, delete_file)
3. **Step 3**: Update multi-step methods (insert_chunks, fts_insert)
4. **Step 4**: Update indexer to use transactions
5. **Step 5**: Test and verify

---

**Status**: 📋 **PLAN READY**  
**Next Step**: Implement the changes
