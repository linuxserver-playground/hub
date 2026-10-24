"""The fleet: every image built from the store, with when it was refreshed and how that went."""

from __future__ import annotations

from dataclasses import dataclass

from builder.manifest import Settings

from .config import ORG, REGISTRY, SiteConfig
from .dates import python_timestamp
from .models import Health, ImageDetail, Mod, RejectedRelease, SourceStatus
from .store import ImageRecord, Store
from .transform import build_images


def hub_settings(site: SiteConfig) -> Settings:
    """builder's Settings pointed at the playground and at this deployment."""
    return Settings.from_env({"BUILDER_ORG": ORG, "BUILDER_REGISTRY": REGISTRY, "BUILDER_HUB_URL": site.api_root})


@dataclass(frozen=True)
class Fleet:
    images: list[ImageDetail]
    store: Store
    updated_at: str | None
    """ISO 8601 time of the last successful manifest refresh."""
    health: Health
    sources: dict[str, SourceStatus]
    rejected: dict[str, RejectedRelease]
    mods: list[Mod]
    settings: Settings
    site: SiteConfig

    @property
    def last_updated(self) -> str:
        """`updated_at` in the original API's format, for every response's envelope."""
        return python_timestamp(self.updated_at)

    @property
    def current(self) -> list[ImageDetail]:
        """The images that aren't deprecated."""
        return [i for i in self.images if not i.deprecated]

    def record(self, name: str) -> ImageRecord | None:
        return self.store.images.get(name)

    def image(self, name: str) -> ImageDetail | None:
        return next((i for i in self.images if i.name == name), None)


def _with_source(mod: dict[str, object], index_source: str) -> dict[str, object]:
    """Mods written before the per-entry `source` existed take the index's: legacy when it was the legacy list."""
    if "source" in mod:
        return mod
    return {**mod, "source": "legacy" if index_source.startswith("legacy") else "playground"}


def _updated_at(store: Store) -> str | None:
    sources = store.status.get("sources", {})
    manifests = sources.get("manifests", {}).get("fetched_at")
    if manifests:
        return str(manifests)
    times = [s["fetched_at"] for s in sources.values() if s.get("fetched_at")]
    return max(times) if times else None


def load_fleet(store: Store, site: SiteConfig | None = None) -> Fleet:
    site = site or SiteConfig.from_env()
    settings = hub_settings(site)
    raw_sources = {name: dict(s) for name, s in store.status.get("sources", {}).items()}
    if store.observed.get("fetched_at"):
        # observed.json is the authority on when stars and tags were last read; status.json may lag a run behind.
        raw_sources.setdefault("observed", {"ok": True, "checked_at": store.observed["fetched_at"]})
        raw_sources["observed"]["fetched_at"] = store.observed["fetched_at"]
    sources = {name: SourceStatus.model_validate(s) for name, s in raw_sources.items()}
    manifests = sources.get("manifests")
    updated_at = _updated_at(store)
    return Fleet(
        images=build_images(store.images, store.observed, settings, site, updated_at),
        store=store,
        updated_at=updated_at,
        health="Success" if manifests and manifests.ok else "Failed",
        sources=sources,
        rejected={k: RejectedRelease.model_validate(v) for k, v in sorted(store.status.get("rejected", {}).items())},
        mods=[
            Mod.model_validate(_with_source(m, str(store.mods.get("source", "")))) for m in store.mods.get("mods", [])
        ],
        settings=settings,
        site=site,
    )
