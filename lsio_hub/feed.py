"""The recent changelog as an Atom feed, so people can follow notable image changes in a feed reader."""

import hashlib

from .config import SiteConfig
from .fleet import Fleet
from .models import ChangelogEntry
from .responses import recent_changelog
from .templating import env


def _entry_id(e: ChangelogEntry) -> str:
    """Stable across builds, so readers don't show an entry twice."""
    return "urn:sha1:" + hashlib.sha1(f"{e.image}\n{e.date}\n{e.desc}".encode()).hexdigest()


def changelog_feed(fleet: Fleet, config: SiteConfig) -> str:
    github_urls = {i.name: i.github_url for i in fleet.images}
    entries = [
        {
            "id": _entry_id(e),
            "entry": e,
            "link": github_urls.get(e.image, f"https://github.com/{fleet.settings.org}") + "#versions",
        }
        for e in recent_changelog(fleet)
    ]
    return env.get_template("feed.xml").render(
        self_url=f"{config.api_root}/api/v1/changelog.xml",
        site_url=config.site_root,
        updated=fleet.updated_at or "1970-01-01T00:00:00Z",
        entries=entries,
    )
