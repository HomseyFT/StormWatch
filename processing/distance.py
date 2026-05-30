"""
Distance calculations between user coordinates and NWS alert polygons.
Computes both:
  - Distance to nearest polygon edge (operational danger proximity)
  - Distance to polygon centroid (storm center tracking)

Uses shapely for polygon math; all public functions return miles.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from shapely.geometry import Point, Polygon

from api.nws import Alert, AlertPolygon

logger = logging.getLogger(__name__)

_EARTH_RADIUS_MILES = 3958.8


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two lat/lon points."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def _polygon_to_shapely(poly: AlertPolygon) -> Optional[Polygon]:
    """Convert AlertPolygon (lon, lat) ring to a shapely Polygon."""
    if len(poly.coordinates) < 3:
        return None
    try:
        return Polygon(poly.coordinates)  # (lon, lat) — consistent with GeoJSON
    except Exception as exc:
        logger.warning("Invalid polygon geometry: %s", exc)
        return None


def _approx_degrees_per_mile(lat: float) -> tuple[float, float]:
    """
    Approximate degree offsets per mile at a given latitude.
    Used to convert the shapely degree-space distance to miles.
    """
    lat_deg_per_mile = 1.0 / 69.0          # ~69 miles per degree latitude
    lon_deg_per_mile = 1.0 / (69.0 * math.cos(math.radians(lat)))
    return lat_deg_per_mile, lon_deg_per_mile


def compute_distances(
    user_lat: float,
    user_lon: float,
    polygon: AlertPolygon,
) -> tuple[float, float]:
    """
    Returns (distance_to_edge_miles, distance_to_center_miles).

    distance_to_edge:
      - 0.0 if the user is inside the polygon
      - positive = nearest exterior boundary distance

    distance_to_center:
      - haversine distance from user to polygon centroid
    """
    shape = _polygon_to_shapely(polygon)
    if shape is None or not shape.is_valid:
        # Fall back to haversine to first polygon vertex
        first = polygon.coordinates[0]
        fallback = _haversine_miles(user_lat, user_lon, first[1], first[0])
        return fallback, fallback

    user_point = Point(user_lon, user_lat)  # (lon, lat) to match GeoJSON

    # --- Distance to edge ---
    if shape.contains(user_point):
        edge_dist_miles = 0.0
    else:
        # shapely distance is in degrees; convert via average scale factor
        deg_dist = shape.exterior.distance(user_point)
        _, lon_deg_per_mile = _approx_degrees_per_mile(user_lat)
        # Use longitude scale as a reasonable approximation
        edge_dist_miles = deg_dist / lon_deg_per_mile

    # --- Distance to centroid ---
    centroid = shape.centroid
    center_dist_miles = _haversine_miles(
        user_lat, user_lon,
        centroid.y,   # lat
        centroid.x,   # lon
    )

    return edge_dist_miles, center_dist_miles


def annotate_alerts(
    user_lat: float,
    user_lon: float,
    alerts: list[Alert],
) -> list[Alert]:
    """
    Mutate Alert objects in-place with distance_to_edge_miles
    and distance_to_center_miles. Alerts without polygons get None.
    Returns the same list for chaining convenience.
    """
    for alert in alerts:
        if alert.polygon:
            edge, center = compute_distances(user_lat, user_lon, alert.polygon)
            alert.distance_to_edge_miles = round(edge, 1)
            alert.distance_to_center_miles = round(center, 1)
        else:
            alert.distance_to_edge_miles = None
            alert.distance_to_center_miles = None

    return alerts
