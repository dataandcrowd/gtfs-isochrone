"""
Shared I/O helpers for the GTFS isochrone pipeline.

On some sandboxed / FUSE-mounted filesystems, SQLite-based writes (which
pyogrio uses for the GeoPackage driver) fail because the filesystem does not
support the locking semantics SQLite expects. The symptom is a zero-byte
.gpkg file plus a 512-byte .gpkg-journal that cannot be unlinked.

`safe_to_gpkg()` writes the GeoDataFrame to a scratch path on the real local
filesystem first, then copies the finished GeoPackage into the target path
with shutil.copy2. This bypasses both the SQLite lock issue and the unlink
restriction.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import geopandas as gpd


SCRATCH_ROOT = Path(os.environ.get("GTFS_SCRATCH", "/sessions/ecstatic-wizardly-fermi"))


def safe_to_gpkg(gdf: gpd.GeoDataFrame, target: Path | str) -> Path:
    """
    Write `gdf` to `target` as GeoPackage (driver='GPKG'), working around
    FUSE + SQLite lock issues by staging the write in SCRATCH_ROOT first.

    Returns the final `target` Path on success.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # 1. Write to a scratch file on a well-behaved filesystem
    with tempfile.NamedTemporaryFile(
        suffix=".gpkg",
        dir=SCRATCH_ROOT,
        delete=False,
    ) as tmp:
        scratch = Path(tmp.name)

    # tempfile created a zero-byte placeholder; remove so pyogrio writes fresh
    scratch.unlink()

    gdf.to_file(scratch, driver="GPKG")

    # 2. Copy into the target. shutil.copy2 overwrites in place even when the
    #    target cannot be unlink()'d via the FUSE mount.
    shutil.copy2(scratch, target)

    # 3. Best-effort cleanup of scratch
    try:
        scratch.unlink()
    except OSError:
        pass

    return target
