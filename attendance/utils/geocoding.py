import requests
import logging

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


def reverse_geocode(latitude, longitude):

    if latitude is None or longitude is None:
        return None

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "addressdetails": 1,
                "zoom": 18,
            },
            headers={
                "User-Agent": "ArsheeHRMS/1.0 (admin@yourdomain.com)"
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        address = data.get("address", {})

        return {
            "full_address": data.get("display_name"),

            "road": address.get("road"),

            "village": (
                address.get("village")
                or address.get("hamlet")
                or address.get("suburb")
            ),

            "town": (
                address.get("town")
                or address.get("city")
                or address.get("municipality")
            ),

            "block": address.get("county"),

            "district": address.get("state_district"),

            "state": address.get("state"),

            "postal_code": address.get("postcode"),

            "country": address.get("country"),
        }

    except requests.RequestException as exc:

        logger.exception(
            "Reverse geocoding failed for %s, %s",
            latitude,
            longitude,
        )

        return None

    except (ValueError, TypeError) as exc:

        logger.exception(
            "Invalid reverse geocoding response: %s",
            exc,
        )

        return None