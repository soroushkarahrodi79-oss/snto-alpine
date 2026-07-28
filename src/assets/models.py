from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class AssetType(str, Enum):
    TRAIL = "trail"
    VIEWPOINT = "viewpoint"
    RECREATIONAL_AREA = "recreational_area"


class GeometryType(str, Enum):
    POINT = "Point"
    LINESTRING = "LineString"
    POLYGON = "Polygon"


# Expected geometry type per asset type
_ASSET_GEOMETRY_MAP: dict[AssetType, GeometryType] = {
    AssetType.TRAIL: GeometryType.LINESTRING,
    AssetType.VIEWPOINT: GeometryType.POINT,
    AssetType.RECREATIONAL_AREA: GeometryType.POLYGON,
}


class GeoJSONGeometry(BaseModel):
    type: GeometryType
    coordinates: list[Any]


class TourismAsset(BaseModel):
    asset_id: str
    name: str
    asset_type: AssetType
    geometry: GeoJSONGeometry
    region: str
    country: str = "Spain"
    elevation_m: Optional[float] = None
    area_ha: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_geometry_matches_asset_type(self) -> "TourismAsset":
        expected = _ASSET_GEOMETRY_MAP[self.asset_type]
        if self.geometry.type != expected:
            raise ValueError(
                f"Asset type '{self.asset_type.value}' requires geometry type "
                f"'{expected.value}', got '{self.geometry.type.value}'"
            )
        return self


class SpatialStats(BaseModel):
    """
    Pixel-level distribution statistics for one spectral index in one month.

    Present when the observation comes from a real spatial aggregation (GEE /
    STAC raster pipeline) over a polygon or buffered geometry.  Absent (None)
    for mock / point-sampled data where no pixel distribution exists.
    """

    mean: float
    median: float
    p25: float   # 25th percentile — lower canopy / dry patches
    p75: float   # 75th percentile — dense / moist patches
    std: float   # standard deviation (spatial heterogeneity indicator)
    pixel_count: int           # number of valid (cloud-free) pixels
    valid_pixel_pct: float     # fraction of total pixels that were cloud-free


class AssetObservation(BaseModel):
    """One monthly satellite-derived snapshot for a single asset."""

    asset_id: str
    year: int
    month: int  # 1–12
    ndvi: float  # mean NDVI for the month (primary scalar, always present)
    ndmi: float  # mean NDMI for the month
    nbr: Optional[float] = None
    evi: Optional[float] = None   # Enhanced Vegetation Index — None when blue band unavailable
    ndsi: Optional[float] = None  # Normalized Difference Snow Index — None when green/SWIR absent
    cloud_cover_pct: float = 0.0
    data_source: str = "mock"

    # Full pixel distribution — populated by GEE/STAC adapters, None for mock
    ndvi_stats: Optional[SpatialStats] = None
    ndmi_stats: Optional[SpatialStats] = None
