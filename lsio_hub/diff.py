"""
What changed between a build and the previous build of the same branch. The implementation is the builder's
(`builder.derive.diff`): the build computes the same diff into its record.json, and the hub computes it only for
releases that have none.
"""

from builder.derive.diff import Packages, classify, diff_builds, dockerfile_diff, package_diff

__all__ = ["Packages", "classify", "diff_builds", "dockerfile_diff", "package_diff"]
