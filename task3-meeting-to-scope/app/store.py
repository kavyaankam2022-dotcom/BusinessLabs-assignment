import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import MeetingCreate, ProjectCreate, ProjectRevision


class ScopeStore:
    def __init__(self, database_path: str | None = None) -> None:
        default_path = Path(__file__).resolve().parents[1] / "data" / "scope.db"
        self.database_path = database_path or os.getenv("SCOPE_DATABASE_PATH", str(default_path))
        self.initialized = False

    def initialize(self) -> None:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    meeting_date TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    transcript_hash TEXT NOT NULL,
                    consent_confirmed INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    meeting_id TEXT NOT NULL REFERENCES meetings(meeting_id),
                    revision_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, revision_number)
                );
                CREATE TABLE IF NOT EXISTS review_history (
                    review_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES revisions(revision_id),
                    reviewed_by TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS meetings_project_idx ON meetings(project_id, meeting_date);
                CREATE INDEX IF NOT EXISTS revisions_project_idx ON revisions(project_id, revision_number DESC);
                """
            )
        self.initialized = True

    def create_project(self, request: ProjectCreate, meeting_id: str) -> str:
        project_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects(project_id, title, created_at) VALUES (?, ?, ?)",
                (project_id, request.title, _now()),
            )
            self._insert_meeting(connection, project_id, meeting_id, request.meeting_date.isoformat(),
                                 request.transcript, request.consent_confirmed)
        return project_id

    def add_meeting(self, project_id: str, meeting_id: str, request: MeetingCreate) -> bool:
        with self._connect() as connection:
            if not connection.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone():
                return False
            self._insert_meeting(connection, project_id, meeting_id, request.meeting_date.isoformat(),
                                 request.transcript, request.consent_confirmed)
        return True

    @staticmethod
    def _insert_meeting(connection: sqlite3.Connection, project_id: str, meeting_id: str,
                        meeting_date: str, transcript: str, consent_confirmed: bool) -> None:
        import hashlib

        digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        connection.execute(
            """INSERT INTO meetings(meeting_id, project_id, meeting_date, transcript, transcript_hash,
               consent_confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (meeting_id, project_id, meeting_date, transcript, digest, int(consent_confirmed), _now()),
        )

    def meeting_transcript(self, meeting_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM meetings WHERE meeting_id=?", (meeting_id,)).fetchone()
        return dict(row) if row else None

    def project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def next_revision_number(self, project_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM revisions WHERE project_id=?",
                (project_id,),
            ).fetchone()
        return int(row[0])

    def list_meetings(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT meeting_id, project_id, meeting_date, transcript_hash, consent_confirmed, created_at
                   FROM meetings WHERE project_id=? ORDER BY meeting_date, created_at""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_revision(self, revision: ProjectRevision) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO revisions(revision_id, project_id, meeting_id, revision_number, status,
                   payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (revision.revision_id, revision.project_id, revision.meeting_id, revision.revision_number,
                 revision.status, revision.model_dump_json(), revision.created_at.isoformat()),
            )

    def get_revision(self, revision_id: str) -> ProjectRevision | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json, status FROM revisions WHERE revision_id=?", (revision_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["status"] = row["status"]
        return ProjectRevision.model_validate(payload)

    def latest_approved_revision(self, project_id: str) -> ProjectRevision | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT payload_json, status FROM revisions WHERE project_id=? AND status='approved'
                   ORDER BY revision_number DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["status"] = row["status"]
        return ProjectRevision.model_validate(payload)

    def list_revisions(self, project_id: str) -> list[ProjectRevision]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json, status FROM revisions WHERE project_id=? ORDER BY revision_number DESC",
                (project_id,),
            ).fetchall()
        revisions: list[ProjectRevision] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["status"] = row["status"]
            revisions.append(ProjectRevision.model_validate(payload))
        return revisions

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            projects = connection.execute(
                "SELECT project_id, title, created_at FROM projects ORDER BY created_at DESC"
            ).fetchall()
            result: list[dict[str, Any]] = []
            for project in projects:
                latest = connection.execute(
                    """SELECT revision_number, status FROM revisions WHERE project_id=?
                       ORDER BY revision_number DESC LIMIT 1""",
                    (project["project_id"],),
                ).fetchone()
                result.append({**dict(project), "latest_revision": dict(latest) if latest else None})
        return result

    def review_revision(self, revision_id: str, reviewed_by: str, decision: str, note: str) -> bool:
        target_status = "approved" if decision == "approve" else "changes_requested"
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, status FROM revisions WHERE revision_id=?", (revision_id,)
            ).fetchone()
            if not row or row["status"] != "pending_review":
                return False
            connection.execute("UPDATE revisions SET status=? WHERE revision_id=?", (target_status, revision_id))
            connection.execute(
                "INSERT INTO review_history(review_id, revision_id, reviewed_by, decision, note, reviewed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), revision_id, reviewed_by, decision, note, _now()),
            )
        return True

    def review_history(self, revision_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT reviewed_by, decision, note, reviewed_at FROM review_history WHERE revision_id=? ORDER BY reviewed_at",
                (revision_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
