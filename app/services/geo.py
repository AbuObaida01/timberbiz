import math
from fastapi import HTTPException, status
from app.config import settings


def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float
) -> float:
    """
    Calculate distance in kilometres between two GPS points
    using the Haversine formula.

    lat1, lon1 → first point (user)
    lat2, lon2 → second point (shop)
    """

    # Earth's radius in kilometres
    R = 6371.0

    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    lon1_rad = math.radians(lon1)
    lon2_rad = math.radians(lon2)

    # Differences
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Haversine formula
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) *
        math.cos(lat2_rad) *
        math.sin(dlon / 2) ** 2
    )

    c = 2 * math.asin(math.sqrt(a))

    # Final distance in km
    distance_km = R * c
    return round(distance_km, 2)


def check_within_range(user_lat: float, user_lng: float) -> float:
    """
    Check if user is within allowed range from shop.
    Raises 403 if outside range.
    Returns distance in km if within range.
    """

    # Get shop location from .env
    shop_lat = settings.SHOP_LATITUDE
    shop_lng = settings.SHOP_LONGITUDE
    max_distance = settings.MAX_DISTANCE_KM

    # Check if user has location at all
    if user_lat is None or user_lng is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your location is not set. Please update your location before posting."
        )

    # Calculate distance
    distance = haversine_distance(user_lat, user_lng, shop_lat, shop_lng)

    # Block if too far
    if distance > max_distance:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are {distance} km away from our shop. Only sellers within {max_distance} km can post listings."
        )

    return distance