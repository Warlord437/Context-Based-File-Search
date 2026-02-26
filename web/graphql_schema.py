"""
GraphQL API for Local-Agent metrics and analytics.
Exposes indexing stats, search stats, database metrics, and analytics.
"""

import sys
from pathlib import Path
from typing import List, Optional

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import strawberry


def get_catalog():
    """Get catalog instance for resolvers."""
    from search.storage import create_storage
    from search.config import get_config
    _, catalog = create_storage(get_config())
    return catalog


def get_qdrant():
    """Get Qdrant store for vector count."""
    from search.storage import create_storage
    from search.config import get_config
    qdrant, _ = create_storage(get_config())
    return qdrant


def _build_search_summary(catalog):
    """Build SearchStatsSummary from catalog."""
    s = catalog.get_search_stats_summary()
    total = s.get("total_searches", 0) or 0
    hits = s.get("cache_hits", 0) or 0
    cache_rate = (hits / total * 100) if total > 0 else None
    return SearchStatsSummary(
        total_searches=total,
        cache_hits=hits,
        cache_hit_rate=round(cache_rate, 2) if cache_rate is not None else None,
        avg_duration=s.get("avg_duration"),
        avg_results=s.get("avg_results"),
    )


def _build_index_summary(catalog):
    """Build IndexStatsSummary from catalog."""
    s = catalog.get_index_stats_summary()
    return IndexStatsSummary(
        total_ops=s.get("total_ops", 0) or 0,
        total_files=s.get("total_files", 0) or 0,
        total_chunks=s.get("total_chunks", 0) or 0,
        total_errors=s.get("total_errors", 0) or 0,
        avg_duration=s.get("avg_duration"),
    )


def _build_system_status():
    """Build SystemStatus from storage."""
    try:
        qdrant = get_qdrant()
        catalog = get_catalog()
        stats = catalog.get_file_stats()
        point_count = 0
        if qdrant.client:
            try:
                collection_info = qdrant.client.get_collection(qdrant.collection_name)
                point_count = collection_info.points_count
            except Exception:
                pass
        return SystemStatus(
            status="ok",
            qdrant_connected=qdrant.client is not None,
            files_indexed=stats.get("total_files", 0),
            chunks_indexed=stats.get("total_chunks", 0),
            vectors_count=point_count,
        )
    except Exception as e:
        return SystemStatus(
            status="error",
            qdrant_connected=False,
            files_indexed=0,
            chunks_indexed=0,
            vectors_count=0,
            error=str(e),
        )


def _build_database_stats():
    """Build DatabaseStats from catalog."""
    catalog = get_catalog()
    stats = catalog.get_file_stats()
    last_indexed = None
    try:
        row = catalog.conn.execute("SELECT last_indexed FROM db_stats").fetchone()
        if row and row["last_indexed"]:
            from datetime import datetime
            ts = row["last_indexed"]
            last_indexed = datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        pass
    return DatabaseStats(
        total_files=stats.get("total_files", 0),
        total_chunks=stats.get("total_chunks", 0),
        total_fts_entries=stats.get("total_fts_entries", 0),
        unique_paths=stats.get("unique_paths", 0),
        total_size_bytes=stats.get("total_size_bytes"),
        last_indexed=last_indexed,
    )


def _build_recent_indexing(limit: int):
    """Build list of IndexOperation from catalog."""
    catalog = get_catalog()
    rows = catalog.get_recent_indexing(limit)
    return [
        IndexOperation(
            operation=r.get("operation", ""),
            files_processed=r.get("files_processed", 0),
            chunks_created=r.get("chunks_created", 0),
            files_skipped=r.get("files_skipped", 0),
            errors=r.get("errors", 0),
            duration_seconds=r.get("duration_seconds", 0) or 0,
            timestamp=r.get("timestamp", 0),
            timestamp_str=r.get("timestamp_str"),
        )
        for r in rows
    ]


def _build_recent_searches(limit: int):
    """Build list of SearchOperation from catalog."""
    catalog = get_catalog()
    rows = catalog.get_recent_searches(limit)
    return [
        SearchOperation(
            query=r.get("query", ""),
            total_candidates=r.get("total_candidates", 0),
            vector_candidates=r.get("vector_candidates", 0),
            lexical_candidates=r.get("lexical_candidates", 0),
            final_results=r.get("final_results", 0),
            duration_seconds=r.get("duration_seconds", 0) or 0,
            cache_hit=bool(r.get("cache_hit")),
            timestamp=r.get("timestamp", 0),
            timestamp_str=r.get("timestamp_str"),
        )
        for r in rows
    ]


# --- Types ---

@strawberry.type
class SystemStatus:
    """Overall system health and connection status."""
    status: str
    qdrant_connected: bool
    files_indexed: int
    chunks_indexed: int
    vectors_count: int
    error: Optional[str] = None


@strawberry.type
class DatabaseStats:
    """SQLite catalog statistics."""
    total_files: int
    total_chunks: int
    total_fts_entries: int
    unique_paths: int
    total_size_bytes: Optional[int]
    last_indexed: Optional[str] = None


@strawberry.type
class IndexOperation:
    """Single indexing operation record."""
    operation: str
    files_processed: int
    chunks_created: int
    files_skipped: int
    errors: int
    duration_seconds: float
    timestamp: int
    timestamp_str: Optional[str] = None


@strawberry.type
class IndexStatsSummary:
    """Aggregated indexing metrics."""
    total_ops: int
    total_files: int
    total_chunks: int
    total_errors: int
    avg_duration: Optional[float] = None


@strawberry.type
class SearchOperation:
    """Single search operation record."""
    query: str
    total_candidates: int
    vector_candidates: int
    lexical_candidates: int
    final_results: int
    duration_seconds: float
    cache_hit: bool
    timestamp: int
    timestamp_str: Optional[str] = None


@strawberry.type
class SearchStatsSummary:
    """Aggregated search metrics."""
    total_searches: int
    cache_hits: int
    cache_hit_rate: Optional[float] = None
    avg_duration: Optional[float] = None
    avg_results: Optional[float] = None


@strawberry.type
class FileTypeCount:
    """File count by type for analytics."""
    file_type: str
    count: int


@strawberry.type
class TopQuery:
    """Most frequent search query."""
    query: str
    count: int
    avg_duration: Optional[float] = None


@strawberry.type
class SearchTimeBucket:
    """Search volume in a time bucket."""
    bucket_start: int
    bucket_str: Optional[str] = None
    count: int
    avg_duration: Optional[float] = None
    cache_hits: int


@strawberry.type
class IndexTimeBucket:
    """Indexing volume in a time bucket."""
    bucket_start: int
    bucket_str: Optional[str] = None
    files_processed: int
    chunks_created: int
    ops_count: int


@strawberry.type
class PerformancePercentiles:
    """Search latency percentiles (seconds)."""
    p50: float
    p95: float
    p99: float


@strawberry.type
class Analytics:
    """Full analytics dashboard data."""
    file_type_distribution: List[FileTypeCount]
    top_queries: List[TopQuery]
    search_time_series: List[SearchTimeBucket]
    index_time_series: List[IndexTimeBucket]
    search_percentiles: PerformancePercentiles
    search_summary: SearchStatsSummary
    index_summary: IndexStatsSummary


@strawberry.type
class Metrics:
    """Aggregate metrics view."""
    system: SystemStatus
    database: DatabaseStats
    index_summary: IndexStatsSummary
    search_summary: SearchStatsSummary
    recent_indexing: List[IndexOperation]
    recent_searches: List[SearchOperation]


# --- Query ---

@strawberry.type
class Query:
    """GraphQL root query for Local-Agent metrics and analytics."""

    @strawberry.field
    def system_status(self) -> SystemStatus:
        """Get system status (files indexed, Qdrant connection)."""
        try:
            qdrant = get_qdrant()
            catalog = get_catalog()
            stats = catalog.get_file_stats()
            point_count = 0
            if qdrant.client:
                try:
                    collection_info = qdrant.client.get_collection(qdrant.collection_name)
                    point_count = collection_info.points_count
                except Exception:
                    pass
            return SystemStatus(
                status="ok",
                qdrant_connected=qdrant.client is not None,
                files_indexed=stats.get("total_files", 0),
                chunks_indexed=stats.get("total_chunks", 0),
                vectors_count=point_count,
            )
        except Exception as e:
            return SystemStatus(
                status="error",
                qdrant_connected=False,
                files_indexed=0,
                chunks_indexed=0,
                vectors_count=0,
                error=str(e),
            )

    @strawberry.field
    def database_stats(self) -> DatabaseStats:
        """Get SQLite catalog statistics."""
        catalog = get_catalog()
        stats = catalog.get_file_stats()
        last_indexed = None
        try:
            row = catalog.conn.execute("SELECT last_indexed FROM db_stats").fetchone()
            if row and row["last_indexed"]:
                from datetime import datetime
                ts = row["last_indexed"]
                last_indexed = datetime.utcfromtimestamp(ts).isoformat() + "Z"
        except Exception:
            pass
        return DatabaseStats(
            total_files=stats.get("total_files", 0),
            total_chunks=stats.get("total_chunks", 0),
            total_fts_entries=stats.get("total_fts_entries", 0),
            unique_paths=stats.get("unique_paths", 0),
            total_size_bytes=stats.get("total_size_bytes"),
            last_indexed=last_indexed,
        )

    @strawberry.field
    def recent_indexing(self, limit: int = 10) -> List[IndexOperation]:
        """Get recent indexing operations."""
        catalog = get_catalog()
        rows = catalog.get_recent_indexing(limit)
        return [
            IndexOperation(
                operation=r.get("operation", ""),
                files_processed=r.get("files_processed", 0),
                chunks_created=r.get("chunks_created", 0),
                files_skipped=r.get("files_skipped", 0),
                errors=r.get("errors", 0),
                duration_seconds=r.get("duration_seconds", 0) or 0,
                timestamp=r.get("timestamp", 0),
                timestamp_str=r.get("timestamp_str"),
            )
            for r in rows
        ]

    @strawberry.field
    def recent_searches(self, limit: int = 10) -> List[SearchOperation]:
        """Get recent search operations."""
        catalog = get_catalog()
        rows = catalog.get_recent_searches(limit)
        return [
            SearchOperation(
                query=r.get("query", ""),
                total_candidates=r.get("total_candidates", 0),
                vector_candidates=r.get("vector_candidates", 0),
                lexical_candidates=r.get("lexical_candidates", 0),
                final_results=r.get("final_results", 0),
                duration_seconds=r.get("duration_seconds", 0) or 0,
                cache_hit=bool(r.get("cache_hit")),
                timestamp=r.get("timestamp", 0),
                timestamp_str=r.get("timestamp_str"),
            )
            for r in rows
        ]

    @strawberry.field
    def index_stats_summary(self) -> IndexStatsSummary:
        """Get aggregated indexing metrics."""
        catalog = get_catalog()
        s = catalog.get_index_stats_summary()
        return IndexStatsSummary(
            total_ops=s.get("total_ops", 0) or 0,
            total_files=s.get("total_files", 0) or 0,
            total_chunks=s.get("total_chunks", 0) or 0,
            total_errors=s.get("total_errors", 0) or 0,
            avg_duration=s.get("avg_duration"),
        )

    @strawberry.field
    def search_stats_summary(self) -> SearchStatsSummary:
        """Get aggregated search metrics with cache hit rate."""
        catalog = get_catalog()
        s = catalog.get_search_stats_summary()
        total = s.get("total_searches", 0) or 0
        hits = s.get("cache_hits", 0) or 0
        cache_rate = (hits / total * 100) if total > 0 else None
        return SearchStatsSummary(
            total_searches=total,
            cache_hits=hits,
            cache_hit_rate=round(cache_rate, 2) if cache_rate is not None else None,
            avg_duration=s.get("avg_duration"),
            avg_results=s.get("avg_results"),
        )

    @strawberry.field
    def metrics(self, recent_limit: int = 10) -> Metrics:
        """Get all metrics in one query (efficient for dashboards)."""
        catalog = get_catalog()
        return Metrics(
            system=_build_system_status(),
            database=_build_database_stats(),
            index_summary=_build_index_summary(catalog),
            search_summary=_build_search_summary(catalog),
            recent_indexing=_build_recent_indexing(recent_limit),
            recent_searches=_build_recent_searches(recent_limit),
        )

    # --- Analytics ---

    @strawberry.field
    def file_type_distribution(self) -> List[FileTypeCount]:
        """Get file count by type (pdf, markdown, link, etc.)."""
        catalog = get_catalog()
        rows = catalog.get_file_type_distribution()
        return [FileTypeCount(file_type=r.get("file_type", "other"), count=r.get("count", 0)) for r in rows]

    @strawberry.field
    def top_queries(
        self,
        limit: int = 20,
        since_hours: Optional[int] = None,
    ) -> List[TopQuery]:
        """Get most frequent search queries."""
        catalog = get_catalog()
        rows = catalog.get_top_queries(limit=limit, since_hours=since_hours)
        return [
            TopQuery(
                query=r.get("query", ""),
                count=r.get("count", 0),
                avg_duration=r.get("avg_duration"),
            )
            for r in rows
        ]

    @strawberry.field
    def search_time_series(
        self,
        since_hours: int = 24,
        bucket_hours: int = 1,
    ) -> List[SearchTimeBucket]:
        """Get search volume over time (for charts)."""
        catalog = get_catalog()
        rows = catalog.get_search_time_series(since_hours=since_hours, bucket_hours=bucket_hours)
        return [
            SearchTimeBucket(
                bucket_start=r.get("bucket_start", 0),
                bucket_str=r.get("bucket_str"),
                count=r.get("count", 0),
                avg_duration=r.get("avg_duration"),
                cache_hits=r.get("cache_hits", 0),
            )
            for r in rows
        ]

    @strawberry.field
    def index_time_series(
        self,
        since_hours: int = 168,
        bucket_hours: int = 24,
    ) -> List[IndexTimeBucket]:
        """Get indexing volume over time (for charts)."""
        catalog = get_catalog()
        rows = catalog.get_index_time_series(since_hours=since_hours, bucket_hours=bucket_hours)
        return [
            IndexTimeBucket(
                bucket_start=r.get("bucket_start", 0),
                bucket_str=r.get("bucket_str"),
                files_processed=r.get("files_processed", 0),
                chunks_created=r.get("chunks_created", 0),
                ops_count=r.get("ops_count", 0),
            )
            for r in rows
        ]

    @strawberry.field
    def search_percentiles(
        self,
        since_hours: Optional[int] = None,
    ) -> PerformancePercentiles:
        """Get p50, p95, p99 search latency (seconds)."""
        catalog = get_catalog()
        p = catalog.get_search_percentiles(since_hours=since_hours)
        return PerformancePercentiles(
            p50=p.get("p50", 0),
            p95=p.get("p95", 0),
            p99=p.get("p99", 0),
        )

    @strawberry.field
    def analytics(
        self,
        top_queries_limit: int = 20,
        top_queries_since_hours: Optional[int] = None,
        search_since_hours: int = 24,
        search_bucket_hours: int = 1,
        index_since_hours: int = 168,
        index_bucket_hours: int = 24,
        percentiles_since_hours: Optional[int] = None,
    ) -> Analytics:
        """Get full analytics dashboard in one query."""
        catalog = get_catalog()
        return Analytics(
            file_type_distribution=[
                FileTypeCount(file_type=r.get("file_type", "other"), count=r.get("count", 0))
                for r in catalog.get_file_type_distribution()
            ],
            top_queries=[
                TopQuery(query=r.get("query", ""), count=r.get("count", 0), avg_duration=r.get("avg_duration"))
                for r in catalog.get_top_queries(limit=top_queries_limit, since_hours=top_queries_since_hours)
            ],
            search_time_series=[
                SearchTimeBucket(
                    bucket_start=r.get("bucket_start", 0),
                    bucket_str=r.get("bucket_str"),
                    count=r.get("count", 0),
                    avg_duration=r.get("avg_duration"),
                    cache_hits=r.get("cache_hits", 0),
                )
                for r in catalog.get_search_time_series(since_hours=search_since_hours, bucket_hours=search_bucket_hours)
            ],
            index_time_series=[
                IndexTimeBucket(
                    bucket_start=r.get("bucket_start", 0),
                    bucket_str=r.get("bucket_str"),
                    files_processed=r.get("files_processed", 0),
                    chunks_created=r.get("chunks_created", 0),
                    ops_count=r.get("ops_count", 0),
                )
                for r in catalog.get_index_time_series(since_hours=index_since_hours, bucket_hours=index_bucket_hours)
            ],
            search_percentiles=PerformancePercentiles(
                **catalog.get_search_percentiles(since_hours=percentiles_since_hours)
            ),
            search_summary=_build_search_summary(catalog),
            index_summary=_build_index_summary(catalog),
        )


schema = strawberry.Schema(query=Query)
