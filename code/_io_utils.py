"""
Shared I/O helpers for the GTFS isochrone pipeline.

On some sandboxed / FUSE-mounted filesystems, SQLite-based writes (which
pyogrio uses for the GeoPackage driver) fail because the filesystem does not
support the locking semantics SQLite expects. The symptom is a zero-byte
.gpkg file plus a 512-byte .gpkg-journal that cannot be unlinked. Reads can
fail with a similar 'attempt to write a readonly database' message because
SQLite tries to take a shared lock on open even in read mode.

`safe_to_gpkg()` writes the GeoDataFrame to a scratch path on the real local
filesystem first, then copies the finished GeoPackage into the target path
with shutil.copy2. `safe_read_gpkg()` does the inverse: copies the source
GeoPackage out of the FUSE mount into scratch, opens it from there, and then
removes the scratch copy. Both bypass the SQLite lock issue completely.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import geopandas as gpd


SCRATCH_ROOT = Path(os.environ.get("GTFS_SCRATCH", "/sessions/ecstatic-wizardly-fermi"))

# Default projected CRS for all final outputs of the Auckland pipeline.
# EPSG:2193 is NZTM2000 (New Zealand Transverse Mercator), the official
# projected CRS for Aotearoa New Zealand. All length and area measurements
# are in metres, which is what QGIS and downstream GIS workflows expect.
DEFAULT_OUTPUT_CRS = "EPSG:2193"


def safe_to_gpkg(
    gdf: gpd.GeoDataFrame,
    target: Path | str,
    *,
    layer: str | None = None,
    target_crs: str | int | None = DEFAULT_OUTPUT_CRS,
) -> Path:
    """
    Write `gdf` to `target` as GeoPackage (driver='GPKG'), working around
    FUSE + SQLite lock issues by staging the write in SCRATCH_ROOT first.

    Parameters
    ----------
    gdf : GeoDataFrame
    target : path-like
        Final destination on the (possibly FUSE-mounted) outputs folder.
    layer : str, optional
        GeoPackage layer name. Defaults to the target file stem so the layer
        name visible in QGIS matches the filename (e.g. 'sa2_equity'), not
        the throwaway scratch tempfile name.
    target_crs : str or int, optional
        CRS of the saved geometry. Defaults to EPSG:2193 (NZTM2000) for the
        Auckland pipeline. Pass `None` to keep the GeoDataFrame's current CRS.

    Returns the final `target` Path on success.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if layer is None:
        layer = target.stem

    if target_crs is not None and gdf.crs is not None:
        gdf = gdf.to_crs(target_crs)

    # 1. Write to a scratch file on a well-behaved filesystem
    with tempfile.NamedTemporaryFile(
        suffix=".gpkg",
        dir=SCRATCH_ROOT,
        delete=False,
    ) as tmp:
        scratch = Path(tmp.name)

    # tempfile created a zero-byte placeholder; remove so pyogrio writes fresh
    scratch.unlink()

    gdf.to_file(scratch, driver="GPKG", layer=layer)

    # 2. Copy into the target. shutil.copy2 overwrites in place even when the
    #    target cannot be unlink()'d via the FUSE mount.
    shutil.copy2(scratch, target)

    # 3. Best-effort cleanup of scratch
    try:
        scratch.unlink()
    except OSError:
        pass

    return target


def safe_read_gpkg(source: Path | str, **read_kwargs) -> gpd.GeoDataFrame:
    """
    Read a GeoPackage that lives on a FUSE/read-only filesystem where SQLite
    cannot acquire even the shared lock it would normally take during open.

    The file is copied to SCRATCH_ROOT first, read with geopandas, then the
    scratch copy is removed. Returns a regular GeoDataFrame.

    Any keyword arguments are forwarded to `gpd.read_file()`.
    """
    source = Path(source)
    if not (source.exists() and source.stat().st_size > 0):
        raise FileNotFoundError(f"GeoPackage missing or empty: {source}")

    with tempfile.NamedTemporaryFile(
        suffix=".gpkg",
        dir=SCRATCH_ROOT,
        delete=False,
    ) as tmp:
        scratch = Path(tmp.name)

    # Overwrite the placeholder with a real copy on the well-behaved fs.
    shutil.copy2(source, scratch)

    try:
        gdf = gpd.read_file(scratch, **read_kwargs)
    finally:
        try:
            scratch.unlink()
        except OSError:
            pass

    return gdf
