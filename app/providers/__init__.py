"""External providers: standards + fixture catalog (REST, swappable with mocks)."""

from app.providers.fixtures import (
    FixtureProvider,
    FixtureSpec,
    InMemoryFixtureProvider,
    RestFixtureProvider,
)
from app.providers.standards import (
    InMemoryStandardProvider,
    RestStandardProvider,
    StandardProvider,
    StandardTarget,
)

__all__ = [
    "FixtureProvider",
    "FixtureSpec",
    "InMemoryFixtureProvider",
    "InMemoryStandardProvider",
    "RestFixtureProvider",
    "RestStandardProvider",
    "StandardProvider",
    "StandardTarget",
]
