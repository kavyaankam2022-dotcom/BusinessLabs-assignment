import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import EscalationCreate, ReviewedKnowledge
from .vectors import Embedder


class KnowledgeStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self.is_initialized = False

    def initialize(self) -> None:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    lastmod TEXT,
                    content_hash TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    section TEXT NOT NULL,
                    text TEXT NOT NULL,
                    images_json TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    source_type TEXT NOT NULL DEFAULT 'article',
                    applicability TEXT,
                    customer_id TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED, title, section, text, content=''
                );
                CREATE TABLE IF NOT EXISTS escalations (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    customer_context TEXT,
                    status TEXT NOT NULL,
                    answer TEXT,
                    reviewed_by TEXT,
                    expires_at TEXT,
                    customer_id TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS expert_knowledge (
                    knowledge_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    escalation_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    source_url TEXT,
                    supporting_evidence_json TEXT NOT NULL,
                    applicability TEXT NOT NULL,
                    customer_id TEXT,
                    expires_at TEXT,
                    reviewed_by TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (knowledge_id, version)
                );
                CREATE TABLE IF NOT EXISTS evaluation_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    escalation_id TEXT NOT NULL UNIQUE,
                    question TEXT NOT NULL,
                    expected_behavior TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    actual_result_json TEXT,
                    passed INTEGER,
                    reviewed_by TEXT,
                    reviewed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    report_json TEXT,
                    error TEXT
                );
                """
            )
            self._ensure_column(connection, "chunks", "applicability", "TEXT")
            self._ensure_column(connection, "chunks", "customer_id", "TEXT")
            self._ensure_column(connection, "chunks", "expires_at", "TEXT")
            self._ensure_column(connection, "escalations", "customer_id", "TEXT")
            self._ensure_column(connection, "evaluation_cases", "actual_result_json", "TEXT")
            self._ensure_column(connection, "evaluation_cases", "passed", "INTEGER")
            self._ensure_column(connection, "evaluation_cases", "reviewed_by", "TEXT")
            self._ensure_column(connection, "evaluation_cases", "reviewed_at", "TEXT")
        self.is_initialized = True

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def save_page_state(self, url: str, document_id: str, lastmod: str | None, status: str,
                        content_hash: str | None = None, error: str | None = None) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO pages(url, document_id, lastmod, content_hash, status, attempts, error, active, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, 1, ?)
                   ON CONFLICT(url) DO UPDATE SET document_id=excluded.document_id,
                   lastmod=COALESCE(excluded.lastmod, pages.lastmod),
                   content_hash=COALESCE(excluded.content_hash, pages.content_hash),
                   status=excluded.status, attempts=pages.attempts + 1, error=excluded.error,
                   active=1, updated_at=excluded.updated_at""",
                (url, document_id, lastmod, content_hash, status, error, now),
            )

    def page_record(self, url: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM pages WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None

    def replace_article(self, article: Any, chunks: list[dict[str, Any]]) -> None:
        now = _now()
        with self._connect() as connection:
            old_ids = [row[0] for row in connection.execute("SELECT chunk_id FROM chunks WHERE document_id = ?", (article.document_id,))]
            for chunk_id in old_ids:
                connection.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (article.document_id,))
            for chunk in chunks:
                connection.execute(
                    """INSERT INTO chunks(chunk_id, document_id, title, url, section, text, images_json,
                       embedding_json, active, source_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'article', ?)""",
                    (chunk["chunk_id"], article.document_id, article.title, article.url, chunk["section"],
                     chunk["text"], json.dumps(chunk["images"]), json.dumps(chunk["embedding"]), now),
                )
                connection.execute(
                    "INSERT INTO chunks_fts(chunk_id, title, section, text) VALUES (?, ?, ?, ?)",
                    (chunk["chunk_id"], article.title, chunk["section"], chunk["text"]),
                )
            connection.execute(
                """INSERT INTO pages(url, document_id, lastmod, content_hash, status, attempts, error, active, updated_at)
                   VALUES (?, ?, NULL, ?, 'success', 1, NULL, 1, ?)
                   ON CONFLICT(url) DO UPDATE SET content_hash=excluded.content_hash, status='success',
                   attempts=pages.attempts + 1, error=NULL, active=1, updated_at=excluded.updated_at""",
                (article.url, article.document_id, article.content_hash, now),
            )

    def deactivate_missing_pages(self, sitemap_urls: set[str]) -> int:
        with self._connect() as connection:
            rows = connection.execute("SELECT url, document_id FROM pages WHERE active=1").fetchall()
            missing = [(row["url"], row["document_id"]) for row in rows if row["url"] not in sitemap_urls]
            for url, document_id in missing:
                connection.execute("UPDATE pages SET active=0, status='removed', updated_at=? WHERE url=?", (_now(), url))
                chunk_ids = [row[0] for row in connection.execute("SELECT chunk_id FROM chunks WHERE document_id=?", (document_id,))]
                for chunk_id in chunk_ids:
                    connection.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
                connection.execute("UPDATE chunks SET active=0 WHERE document_id=?", (document_id,))
        return len(missing)

    def search(self, question: str, embedder: Embedder, top_k: int,
               customer_id: str | None = None) -> list[dict[str, Any]]:
        query_vector = embedder.encode(question)
        now = _now()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM chunks WHERE active=1 AND (
                       source_type != 'expert' OR (
                           (expires_at IS NULL OR expires_at > ?) AND (
                               applicability='general' OR
                               (applicability='customer_specific' AND customer_id=?)
                           )
                       )
                   )""",
                (now, customer_id),
            ).fetchall()
            lexical_rows = self._fts_candidates(connection, question, max(top_k * 4, 20))
        lexical_rank = {row["chunk_id"]: index + 1 for index, row in enumerate(lexical_rows)}
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            semantic = Embedder.similarity(query_vector, json.loads(row["embedding_json"]))
            rank = lexical_rank.get(row["chunk_id"])
            lexical = 1 / (60 + rank) if rank else 0.0
            score = semantic * 0.7 + min(1.0, lexical * 60) * 0.3
            if semantic >= 0.22 or rank is not None:
                ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, row in ranked[:top_k]:
            results.append({
                "document_id": row["document_id"], "chunk_id": row["chunk_id"], "title": row["title"],
                "url": row["url"], "section": row["section"], "excerpt": row["text"],
                "relevance": round(max(0.0, min(1.0, score)), 4), "images": json.loads(row["images_json"]),
            })
        return results

    def _fts_candidates(self, connection: sqlite3.Connection, question: str, limit: int) -> list[sqlite3.Row]:
        terms = [term for term in question.replace('"', " ").split() if len(term) > 1]
        if not terms:
            return []
        expression = " OR ".join(f'"{term}"' for term in terms[:20])
        try:
            return connection.execute(
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (expression, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    def ingestion_status(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS count FROM pages GROUP BY status").fetchall()
            total_chunks = connection.execute("SELECT COUNT(*) FROM chunks WHERE active=1").fetchone()[0]
            failures = [dict(row) for row in connection.execute(
                "SELECT url, attempts, error, updated_at FROM pages WHERE status='failed' ORDER BY updated_at DESC LIMIT 20"
            )]
            recent_runs = [dict(row) for row in connection.execute(
                "SELECT id, trigger, status, started_at, finished_at, report_json, error "
                "FROM ingestion_runs ORDER BY started_at DESC LIMIT 10"
            )]
        for run in recent_runs:
            run["report"] = json.loads(run.pop("report_json")) if run["report_json"] else None
        return {
            "pages": {row["status"]: row["count"] for row in rows},
            "active_chunks": total_chunks,
            "recent_failures": failures,
            "recent_runs": recent_runs,
        }

    def start_ingestion_run(self, trigger: str) -> str:
        run_id = hashlib.sha256(f"{trigger}{_now()}".encode()).hexdigest()[:20]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_runs(id, trigger, status, started_at) VALUES (?, ?, 'running', ?)",
                (run_id, trigger, _now()),
            )
        return run_id

    def finish_ingestion_run(self, run_id: str, status: str, report: dict[str, Any] | None = None,
                             error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE ingestion_runs SET status=?, finished_at=?, report_json=?, error=? WHERE id=?",
                (status, _now(), json.dumps(report) if report is not None else None, error, run_id),
            )

    def create_escalation(self, request: EscalationCreate) -> str:
        escalation_id = hashlib.sha256(f"{request.question}{_now()}".encode()).hexdigest()[:20]
        with self._connect() as connection:
            connection.execute(
                     """INSERT INTO escalations(id, question, reason, evidence_json, customer_context, status,
                         customer_id, created_at)
                   VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
                (escalation_id, request.question, request.reason, json.dumps(request.evidence),
                 request.customer_context, request.customer_id, _now()),
            )
            connection.execute(
                "INSERT INTO evaluation_cases(escalation_id, question, expected_behavior, created_at) VALUES (?, ?, ?, ?)",
                (escalation_id, request.question, request.reason, _now()),
            )
        return escalation_id

    def list_escalations(self, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM escalations WHERE status=? ORDER BY created_at LIMIT ?", (status, limit)
            ).fetchall()
        results = [dict(row) for row in rows]
        for item in results:
            item["evidence"] = json.loads(item.pop("evidence_json"))
        return results

    def evaluation_cases(self, status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, escalation_id, question, expected_behavior, status, created_at, "
                "actual_result_json, passed, reviewed_by, reviewed_at "
                "FROM evaluation_cases WHERE status=? ORDER BY created_at LIMIT ?", (status, limit)
            ).fetchall()
        results = [dict(row) for row in rows]
        for result in results:
            result["actual_result"] = json.loads(result.pop("actual_result_json")) if result["actual_result_json"] else None
        return results

    def resolve_escalation(self, escalation_id: str, request: ReviewedKnowledge,
                           embedding: list[float]) -> int | None:
        with self._connect() as connection:
            escalation = connection.execute(
                "SELECT question, customer_id FROM escalations WHERE id=? AND status='open'", (escalation_id,)
            ).fetchone()
            if not escalation:
                return None
            knowledge_id = f"expert-{escalation_id}"
            latest = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM expert_knowledge WHERE knowledge_id=?", (knowledge_id,)
            ).fetchone()[0]
            version = latest + 1
            self._write_expert_version(connection, knowledge_id, version, escalation_id,
                                        escalation["question"], request, embedding)
            connection.execute(
                """UPDATE escalations SET status='resolved', answer=?, reviewed_by=?, expires_at=?,
                   customer_id=?, resolved_at=? WHERE id=? AND status='open'""",
                (request.answer, request.reviewed_by, _iso(request.expires_at), request.customer_id, _now(), escalation_id),
            )
        return version

    def revise_expert_knowledge(self, knowledge_id: str, request: ReviewedKnowledge,
                                embedding: list[float]) -> int | None:
        with self._connect() as connection:
            latest = connection.execute(
                "SELECT * FROM expert_knowledge WHERE knowledge_id=? ORDER BY version DESC LIMIT 1", (knowledge_id,)
            ).fetchone()
            if not latest:
                return None
            version = latest["version"] + 1
            self._write_expert_version(connection, knowledge_id, version, latest["escalation_id"],
                                        latest["question"], request, embedding)
        return version

    def _write_expert_version(self, connection: sqlite3.Connection, knowledge_id: str, version: int,
                              escalation_id: str, question: str, request: ReviewedKnowledge,
                              embedding: list[float]) -> None:
        now = _now()
        old_chunks = connection.execute(
            "SELECT chunk_id FROM chunks WHERE document_id=? AND active=1", (knowledge_id,)
        ).fetchall()
        for row in old_chunks:
            connection.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (row["chunk_id"],))
        connection.execute("UPDATE chunks SET active=0 WHERE document_id=?", (knowledge_id,))
        connection.execute("UPDATE expert_knowledge SET active=0 WHERE knowledge_id=?", (knowledge_id,))
        source_url = str(request.source_url) if request.source_url else None
        expires_at = _iso(request.expires_at)
        connection.execute(
            """INSERT INTO expert_knowledge(knowledge_id, version, escalation_id, question, answer, source_url,
               supporting_evidence_json, applicability, customer_id, expires_at, reviewed_by, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (knowledge_id, version, escalation_id, question, request.answer, source_url,
             json.dumps(request.supporting_evidence), request.applicability, request.customer_id,
             expires_at, request.reviewed_by, now),
        )
        chunk_id = hashlib.sha256(f"{knowledge_id}:{version}".encode()).hexdigest()[:24]
        text = f"Question: {question}\nReviewed expert answer: {request.answer}"
        for evidence in request.supporting_evidence:
            excerpt = evidence.get("excerpt") or evidence.get("text")
            if excerpt:
                text += f"\nSupporting evidence: {excerpt}"
        url = source_url or f"expert://{knowledge_id}/v{version}"
        connection.execute(
            """INSERT INTO chunks(chunk_id, document_id, title, url, section, text, images_json,
               embedding_json, active, source_type, applicability, customer_id, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, '[]', ?, 1, 'expert', ?, ?, ?, ?)""",
            (chunk_id, knowledge_id, "Reviewed expert answer", url, f"Expert answer v{version}", text,
             json.dumps(embedding), request.applicability, request.customer_id, expires_at, now),
        )
        connection.execute(
            "INSERT INTO chunks_fts(chunk_id, title, section, text) VALUES (?, ?, ?, ?)",
            (chunk_id, "Reviewed expert answer", f"Expert answer v{version}", text),
        )

    def expert_knowledge_versions(self, knowledge_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM expert_knowledge WHERE knowledge_id=? ORDER BY version", (knowledge_id,)
            ).fetchall()
        versions = [dict(row) for row in rows]
        for version in versions:
            version["supporting_evidence"] = json.loads(version.pop("supporting_evidence_json"))
        return versions

    def mark_evaluation_case(self, escalation_id: str, actual_result: dict[str, Any],
                             passed: bool, reviewed_by: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE evaluation_cases SET status='reviewed', actual_result_json=?, passed=?,
                   reviewed_by=?, reviewed_at=? WHERE escalation_id=? AND status='pending'""",
                (json.dumps(actual_result), int(passed), reviewed_by, _now(), escalation_id),
            )
        return cursor.rowcount == 1

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()