from __future__ import annotations

from app.settings import RuntimeSettings
from app.storage.memory_store import EventStore
from app.storage.postgres_store import PostgresStore
from app.storage.store import Store


def create_store(settings: RuntimeSettings) -> Store:
    if settings.storage_backend == "postgres":
        return PostgresStore(settings)
    return EventStore()
