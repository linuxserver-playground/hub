"""
Every downstream artefact, each a function of data/ alone.
`python -m lsio_hub.generate` writes them under out/: store output under out/stores/<platform>/ and the
redirects from the retired build report pages to the website under out/builds/, so out/ merges onto the site root
next to dist/.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import arcane, builds, casaos, cosmos, docs, kubernetes, mods, portainer, proxy, quadlet, runtipi, umbrel, unraid
from .common import Files, GenerateContext

Generator = Callable[[GenerateContext], Files]

GENERATORS: dict[str, Generator] = {
    "docs": docs.generate,
    "unraid": unraid.generate,
    "portainer": portainer.generate,
    "casaos": casaos.generate,
    "umbrel": umbrel.generate,
    "runtipi": runtipi.generate,
    "cosmos": cosmos.generate,
    "arcane": arcane.generate,
    "proxy": proxy.generate,
    "kubernetes": kubernetes.generate,
    "quadlet": quadlet.generate,
    "mods": mods.generate,
    "builds": builds.generate,
}

OUTPUT_DIRS = {name: ("builds" if name == "builds" else f"stores/{name}") for name in GENERATORS}
"""Where each generator's files go, relative to out/."""


def generate_all(ctx: GenerateContext, only: set[str] | None = None) -> dict[str, Files]:
    """{output dir: files} for the selected generators (all by default)."""
    return {OUTPUT_DIRS[name]: gen(ctx) for name, gen in GENERATORS.items() if only is None or name in only}


def write_output(out_dir: Path, outputs: dict[str, Files]) -> list[str]:
    """Writes each generator's files under out/<dir>/, removing files it no longer produces."""
    written: list[str] = []
    for folder, files in outputs.items():
        base = out_dir / folder
        wanted = {base / rel for rel in files}
        for rel, content in files.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8") if isinstance(content, str) else content
            if not target.is_file() or target.read_bytes() != data:
                target.write_bytes(data)
            written.append(f"{folder}/{rel}")
        if base.is_dir():
            for path in sorted(base.rglob("*"), reverse=True):
                if path.is_file() and path not in wanted:
                    path.unlink()
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
    return written
