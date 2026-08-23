"""
SNTO Alpine Edition — candidate field-validation plots (issue #11)
=====================================================================
"Design before measuring": a field team should not have to invent plot
placement on the mountain. This module turns an asset's already-computed SCM
zones — the local corridor (0-50 m, impact) and the altitude-matched control
(200-500 m annulus ∩ elevation band, issue #9) — into a concrete, reproducible
list of candidate plot coordinates, stratified exactly the way
:mod:`src.validation.field` / :mod:`src.validation.agreement` expect
(``is_control`` + ``stratum``).

Pure geometry, no I/O: the caller supplies zone polygons already built by
:func:`src.spatial_causality.alpine_causality.altitude_matched_control_zone`
(and the plain local-corridor buffer) in their metric CRS. Reprojection to
WGS84 for GPS coordinates is the only CRS work done here, via
:func:`src.geospatial.zonal_stats.reproject_polygon` — reused rather than
duplicated.

Sampling is deterministic (seeded rejection sampling within the polygon), so
the same zone geometry always proposes the same coordinates — a field team
re-running this after a geometry fix gets a stable, diffable plot list rather
than a new random scatter each time.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from src.geospatial.zonal_stats import reproject_polygon

__all__ = ["ProposedPlot", "propose_baci_plots"]

_MAX_ATTEMPTS_PER_PLOT = 200


@dataclass(frozen=True)
class ProposedPlot:
    """One candidate plot a field team can navigate to and survey.

    Shape matches what :class:`src.validation.field.FieldObservation` needs to
    be constructed from a visited plot: ``asset_id``, ``is_control`` and
    ``stratum`` carry straight over: ``lat``/``lon`` become the GPS fix once
    the team is on-site (this is a candidate, not a guarantee — terrain access
    may force a plot to be moved; keep ``plot_id`` if it does, so the
    impact/control pairing survives the move).
    """

    asset_id: str
    plot_id: str
    lat: float
    lon: float
    is_control: bool
    stratum: str


def _sample_points_in_polygon(
    polygon, n: int, rng: random.Random
) -> list[tuple[float, float]]:
    """Deterministic rejection-sampled interior points, as (lon, lat)."""
    if polygon is None or polygon.is_empty or n <= 0:
        return []

    minx, miny, maxx, maxy = polygon.bounds
    points: list[tuple[float, float]] = []
    attempts = 0
    max_attempts = n * _MAX_ATTEMPTS_PER_PLOT
    while len(points) < n and attempts < max_attempts:
        attempts += 1
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if polygon.contains(_point(x, y)):
            points.append((x, y))
    return points


def _point(x: float, y: float):
    from shapely.geometry import Point

    return Point(x, y)


def propose_baci_plots(
    asset_id: str,
    local_zone,
    control_zone,
    zone_crs: str,
    stratum: str,
    n_per_zone: int = 4,
    seed: int = 0,
) -> list[ProposedPlot]:
    """Propose ``n_per_zone`` candidate plots in each of the local/control zones.

    Args:
        asset_id: the trail asset these zones belong to.
        local_zone: impact-zone polygon (0-50 m corridor), in ``zone_crs``.
        control_zone: control-zone polygon (altitude-matched annulus, or the
            plain annulus when matching failed — the caller decides which to
            pass; this function does not know or care), in ``zone_crs``.
        zone_crs: metric CRS the two polygons are expressed in (e.g. the
            project default EPSG:25830).
        stratum: habitat/altitude-band label shared by both zones — the BACI
            pairing key (:mod:`src.validation.field`'s ``stratum`` field).
        n_per_zone: candidate plots requested per zone. Fewer are returned,
            never fabricated, when the polygon is too small/thin to fit that
            many non-overlapping rejection samples within the attempt budget.
        seed: RNG seed; same inputs always propose the same coordinates.

    Returns:
        Impact plots first, then control plots. Empty for a zone whose
        polygon is ``None`` or empty (e.g. issue #9's ``NO_VALID_CONTROL``
        fallback) rather than raising — a field team can still survey the
        other zone, and an empty list is the honest signal that this asset
        needs its geometry fixed before a paired plot can be proposed there.
    """
    rng = random.Random(seed)
    local_wgs84 = (
        reproject_polygon(local_zone, zone_crs, "EPSG:4326")
        if local_zone is not None
        else None
    )
    control_wgs84 = (
        reproject_polygon(control_zone, zone_crs, "EPSG:4326")
        if control_zone is not None
        else None
    )

    plots: list[ProposedPlot] = []
    for zone_poly, is_control, prefix in (
        (local_wgs84, False, "impact"),
        (control_wgs84, True, "control"),
    ):
        pts = _sample_points_in_polygon(zone_poly, n_per_zone, rng)
        for i, (lon, lat) in enumerate(pts):
            plots.append(
                ProposedPlot(
                    asset_id=asset_id,
                    plot_id=f"{asset_id}:{prefix}:{i:02d}",
                    lat=round(lat, 6),
                    lon=round(lon, 6),
                    is_control=is_control,
                    stratum=stratum,
                )
            )
    return plots
