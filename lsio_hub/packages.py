"""
The normalised package table: syft JSON reduced to name, version, type, purl and licenses, plus version ordering and
file slugs. The implementation is the builder's (`builder.derive.packages`), which the build also runs to write the
release's record.json, so the hub and the build compute the same table.
"""

from builder.derive.packages import compare_versions, normalise, normalise_gz, slug, table, version_key

__all__ = ["compare_versions", "normalise", "normalise_gz", "slug", "table", "version_key"]
