"""
Benchmarks and metrics for the hybrid search system.
"""

import time
import csv
import os
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List
import tempfile
import shutil

from .config import get_config
from .indexer import run_bfs_slice
from .api import run as search_run

logger = logging.getLogger(__name__)

class SearchBenchmark:
    """Benchmark suite for search performance."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config()
        self.benchmark_dir = Path(self.config["paths"]["benchmarks"])
        self.benchmark_dir.mkdir(parents=True, exist_ok=True)
        self.csv_file = self.benchmark_dir / "search_bench.csv"
    
    def benchmark_indexing(self, test_paths: List[str], max_items: int = 100) -> Dict[str, Any]:
        """Benchmark indexing performance."""
        print(f"🚀 Benchmarking indexing performance...")
        print(f"📁 Test paths: {test_paths}")
        print(f"📊 Max items: {max_items}")
        
        start_time = time.time()
        
        # Run BFS slice
        stats = run_bfs_slice(test_paths, max_items=max_items)
        
        end_time = time.time()
        duration = end_time - start_time
        
        result = {
            "timestamp": int(time.time()),
            "operation": "indexing",
            "files_indexed": stats.files_processed,
            "chunks_indexed": stats.chunks_created,
            "files_skipped": stats.files_skipped,
            "errors": stats.errors,
            "t_index": duration,
            "test_paths": ",".join(test_paths),
            "max_items": max_items
        }
        
        print(f"✅ Indexing benchmark completed:")
        print(f"   📄 Files indexed: {stats.files_processed}")
        print(f"   📝 Chunks created: {stats.chunks_created}")
        print(f"   ⏱️  Duration: {duration:.2f}s")
        print(f"   📊 Rate: {stats.files_processed/duration:.1f} files/sec")
        
        return result
    
    def benchmark_search(self, queries: List[str], search_type: str = "hybrid") -> Dict[str, Any]:
        """Benchmark search performance."""
        print(f"🔍 Benchmarking {search_type} search performance...")
        
        results = {
            "timestamp": int(time.time()),
            "operation": f"search_{search_type}",
            "queries": queries,
            "search_times": [],
            "total_results": [],
            "cache_hits": 0
        }
        
        total_time = 0
        
        for i, query in enumerate(queries):
            print(f"   Query {i+1}/{len(queries)}: \"{query}\"")
            
            # Warm up (first query might be slower due to model loading)
            if i == 0:
                search_run(query, k=10, page=1, per_page=10)
            
            # Actual benchmark
            start_time = time.time()
            result = search_run(query, k=10, page=1, per_page=10)
            search_time = time.time() - start_time
            
            results["search_times"].append(search_time)
            results["total_results"].append(result["total_hits"])
            
            if result["cache_hit"]:
                results["cache_hits"] += 1
            
            total_time += search_time
            
            print(f"      {search_time:.3f}s - {result['total_hits']} results")
        
        results["t_search_avg"] = total_time / len(queries)
        results["t_search_min"] = min(results["search_times"])
        results["t_search_max"] = max(results["search_times"])
        
        print(f"✅ Search benchmark completed:")
        print(f"   ⏱️  Average time: {results['t_search_avg']:.3f}s")
        print(f"   ⏱️  Min time: {results['t_search_min']:.3f}s")
        print(f"   ⏱️  Max time: {results['t_search_max']:.3f}s")
        print(f"   📊 Total queries: {len(queries)}")
        print(f"   ⚡ Cache hits: {results['cache_hits']}")
        
        return results
    
    def benchmark_end_to_end(self, test_paths: List[str], queries: List[str]) -> Dict[str, Any]:
        """Run complete end-to-end benchmark."""
        print(f"🎯 Running end-to-end benchmark...")
        
        # Step 1: Indexing benchmark
        index_result = self.benchmark_indexing(test_paths, max_items=50)
        
        # Step 2: Search benchmarks
        hybrid_result = self.benchmark_search(queries, "hybrid")
        
        # Combine results
        combined = {
            **index_result,
            "t_search_hybrid": hybrid_result["t_search_avg"],
            "search_queries": len(queries),
            "total_search_time": sum(hybrid_result["search_times"])
        }
        
        return combined
    
    def save_benchmark(self, result: Dict[str, Any]):
        """Save benchmark result to CSV."""
        # Prepare CSV row
        csv_row = {
            "timestamp": result["timestamp"],
            "operation": result["operation"],
            "files_indexed": result.get("files_indexed", 0),
            "chunks_indexed": result.get("chunks_indexed", 0),
            "t_index": result.get("t_index", 0),
            "t_search_hybrid": result.get("t_search_hybrid", 0),
            "t_search_vec": result.get("t_search_vec", 0),
            "t_search_lex": result.get("t_search_lex", 0),
            "test_paths": result.get("test_paths", ""),
            "queries": ",".join(result.get("queries", []))
        }
        
        # Write to CSV
        file_exists = self.csv_file.exists()
        
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=csv_row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(csv_row)
        
        print(f"📊 Benchmark saved to: {self.csv_file}")
    
    def compare_with_previous(self, current_result: Dict[str, Any]) -> None:
        """Compare current benchmark with previous run."""
        if not self.csv_file.exists():
            print("📊 No previous benchmarks found for comparison")
            return
        
        # Read previous results
        previous_results = []
        with open(self.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["operation"] == current_result["operation"]:
                    previous_results.append(row)
        
        if len(previous_results) < 2:
            print("📊 Not enough previous results for comparison")
            return
        
        # Get most recent previous result
        latest_previous = previous_results[-1]
        
        # Compare indexing performance
        if "t_index" in current_result and latest_previous["t_index"]:
            prev_time = float(latest_previous["t_index"])
            curr_time = current_result["t_index"]
            
            if prev_time > 0:
                improvement = ((prev_time - curr_time) / prev_time) * 100
                print(f"📈 Indexing performance:")
                print(f"   Previous: {prev_time:.2f}s")
                print(f"   Current:  {curr_time:.2f}s")
                if improvement > 0:
                    print(f"   🚀 Improvement: {improvement:.1f}% faster")
                else:
                    print(f"   📉 Regression: {abs(improvement):.1f}% slower")
        
        # Compare search performance
        if "t_search_hybrid" in current_result and latest_previous["t_search_hybrid"]:
            prev_time = float(latest_previous["t_search_hybrid"])
            curr_time = current_result["t_search_hybrid"]
            
            if prev_time > 0:
                improvement = ((prev_time - curr_time) / prev_time) * 100
                print(f"📈 Search performance:")
                print(f"   Previous: {prev_time:.3f}s")
                print(f"   Current:  {curr_time:.3f}s")
                if improvement > 0:
                    print(f"   🚀 Improvement: {improvement:.1f}% faster")
                else:
                    print(f"   📉 Regression: {abs(improvement):.1f}% slower")


def create_test_environment(test_dir: str = None) -> str:
    """Create a temporary test environment with sample files."""
    if test_dir is None:
        test_dir = tempfile.mkdtemp(prefix="search_bench_")
    
    test_path = Path(test_dir)
    test_path.mkdir(exist_ok=True)
    
    # Create sample files
    sample_files = {
        "ai_research.md": """
# AI Research Papers

This document contains information about artificial intelligence research.

## Machine Learning
Machine learning is a subset of artificial intelligence that focuses on algorithms.

## Deep Learning
Deep learning uses neural networks with multiple layers to process data.

## Natural Language Processing
NLP is the field of AI that deals with human language understanding.
""",
        
        "python_guide.txt": """
Python Programming Guide

Python is a high-level programming language known for its simplicity.

## Variables
Variables in Python are dynamically typed.

## Functions
Functions are reusable blocks of code that perform specific tasks.

## Classes
Classes are blueprints for creating objects in Python.
""",
        
        "database_systems.md": """
# Database Systems Overview

Databases are essential for storing and managing data efficiently.

## SQL Databases
SQL databases use structured query language for data manipulation.

## NoSQL Databases
NoSQL databases provide flexible schema design for unstructured data.

## Query Optimization
Optimizing queries improves database performance significantly.
"""
    }
    
    for filename, content in sample_files.items():
        file_path = test_path / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    print(f"✅ Created test environment: {test_dir}")
    return test_dir


def main():
    """Main benchmark CLI."""
    parser = argparse.ArgumentParser(description="Search system benchmark")
    parser.add_argument("--paths", nargs="+", help="Paths to index for benchmarking")
    parser.add_argument("--queries", nargs="+", default=[
        "artificial intelligence",
        "machine learning", 
        "python programming",
        "database systems",
        "query optimization"
    ], help="Queries to benchmark")
    parser.add_argument("--max-items", type=int, default=100, help="Max items to index")
    parser.add_argument("--create-test-env", action="store_true", help="Create temporary test environment")
    parser.add_argument("--cleanup", action="store_true", help="Clean up test environment after benchmark")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create benchmark instance
    benchmark = SearchBenchmark()
    
    test_dir = None
    
    try:
        # Create test environment if requested
        if args.create_test_env:
            test_dir = create_test_environment()
            test_paths = [test_dir]
        else:
            test_paths = args.paths or ["/Users/tathagatasaha/Desktop/localagentandcliwithvectordb/README.md"]
        
        # Run end-to-end benchmark
        result = benchmark.benchmark_end_to_end(test_paths, args.queries)
        
        # Save results
        benchmark.save_benchmark(result)
        
        # Compare with previous
        benchmark.compare_with_previous(result)
        
        print(f"\n🎉 Benchmark completed successfully!")
        
    finally:
        # Cleanup test environment
        if args.cleanup and test_dir and Path(test_dir).exists():
            shutil.rmtree(test_dir)
            print(f"🧹 Cleaned up test environment: {test_dir}")


if __name__ == "__main__":
    main()
