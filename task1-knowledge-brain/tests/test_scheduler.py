import asyncio

from fastapi.testclient import TestClient

from app import main


class StubStore:
    is_initialized = False

    def initialize(self):
        self.is_initialized = True


class SchedulerRecorder:
    def __init__(self, timezone):
        self.timezone = timezone
        self.job = None
        self.started = False
        self.stopped = False

    def add_job(self, function, trigger, **kwargs):
        self.job = (function, trigger, kwargs)

    def start(self):
        self.started = True

    def shutdown(self, wait):
        self.stopped = True


def test_lifespan_registers_daily_refresh_job(monkeypatch):
    store = StubStore()
    scheduler = SchedulerRecorder("UTC")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "AsyncIOScheduler", lambda timezone: scheduler)

    with TestClient(main.app):
        assert scheduler.started is True
        assert store.is_initialized is True
        assert scheduler.job[0] is main.scheduled_ingestion_run
        assert scheduler.job[1] == "cron"
        assert scheduler.job[2]["hour"] == main.settings.daily_ingestion_hour
        assert scheduler.job[2]["minute"] == main.settings.daily_ingestion_minute
        assert scheduler.job[2]["id"] == "daily-knowledge-refresh"

    assert scheduler.stopped is True


def test_scheduled_ingestion_persists_run_summary(monkeypatch):
    class RunStore(StubStore):
        def start_ingestion_run(self, trigger):
            self.trigger = trigger
            return "run-123"

        def finish_ingestion_run(self, run_id, status, report=None, error=None):
            self.finished = (run_id, status, report, error)

    store = RunStore()
    monkeypatch.setattr(main, "store", store)

    async def fake_ingestion(**kwargs):
        return {"added": 1, "updated": 2, "unchanged": 3, "removed": 4, "failed": 0}

    monkeypatch.setattr(main, "run_ingestion", fake_ingestion)

    response = asyncio.run(main.run_ingestion_tracked("daily"))

    assert response["run_id"] == "run-123"
    assert store.trigger == "daily"
    assert store.finished[1] == "completed"
    assert store.finished[2]["removed"] == 4