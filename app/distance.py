# What it does: Estimates travel distance/time from the owner's base to a job location, for factoring
#   into estimates (gas/travel time) and scheduling (travel time between jobs). The origin lives
#   only in this server-side code (env var), never in agent context — see REQUIREMENTS.md
#   "Security: data isolation." The tool returns only the computed distance, never the address.
# When it runs: Called by the estimate_travel tool (app/tools.py).
# What calls it: app/tools.py.
#
# NOTE: this is a straight-line (haversine) approximation as a placeholder — not real driving
# distance/time. A real implementation needs a maps/directions API (e.g. Google Distance Matrix),
# which needs an API key decision — not made yet. Flagged, not guessed.
import math
import os
from dataclasses import dataclass


@dataclass
class TravelEstimate:
    straight_line_miles: float
    note: str = "approximate straight-line distance, not real driving distance/time"


def _origin_lat_lon() -> tuple[float, float]:
    lat = os.environ.get("BASE_LATITUDE")
    lon = os.environ.get("BASE_LONGITUDE")
    if not lat or not lon:
        raise RuntimeError("BASE_LATITUDE / BASE_LONGITUDE not set")
    return float(lat), float(lon)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_miles = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return r_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_travel(destination_lat: float, destination_lon: float) -> TravelEstimate:
    origin_lat, origin_lon = _origin_lat_lon()
    miles = _haversine_miles(origin_lat, origin_lon, destination_lat, destination_lon)
    return TravelEstimate(straight_line_miles=round(miles, 1))
