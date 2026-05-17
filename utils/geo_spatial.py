import streamlit as st
from shapely.geometry import shape, Point
import openrouteservice
from geopy.geocoders import Nominatim
import os 

# ==================================
# SPATIAL ROUTING ENGINE FUNCTIONS
# ==================================
def invoke_isochrone_api(lat, lon, max_time, mode):
    """Calls OpenRouteService to generate a dynamic travel-time polygon boundary."""
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        st.error("⚠️ Missing 'ORS_API_KEY' in your .env file!")
        return None
    try:
        client = openrouteservice.Client(key=api_key)
        ors_profile = "driving-car"
        if mode in ["foot", "walking", "hiking"]:
            ors_profile = "foot-hiking"
            
        time_seconds = int(max_time) * 60
        response = client.isochrones(
            locations=[[float(lon), float(lat)]],
            profile=ors_profile,
            range=[time_seconds],
            range_type='time'
        )
        return response['features'][0]['geometry']
    except Exception as e:
        st.error(f"❌ Isochrone API Failure: {str(e)}")
        return None


def invoke_geocoding_api(location_name):
    """Resolves a named regional string into a standard bounding box payload."""
    try:
        geolocator = Nominatim(user_agent="pathfinder_greece_trail_explorer")
        query_string = f"{location_name}, Greece"
        location = geolocator.geocode(query_string, geometry='geojson')
        
        if location and "boundingbox" in location.raw:
            bbox_raw = location.raw["boundingbox"]
            return {
                "min_lat": float(bbox_raw[0]),
                "max_lat": float(bbox_raw[1]),
                "min_lon": float(bbox_raw[2]),
                "max_lon": float(bbox_raw[3])
            }
        return None
    except Exception as e:
        st.error(f"❌ Geocoding API Failure: {str(e)}")
        return None


def filter_trails_spatial(trails, strategy, profile, gps):
    """Applies your requested hard spatial filtering logic using Shapely point containment."""
    viable_trails = []
    if not trails:
        return []

    if strategy == "ISOCHRONE":
        if gps and "lat" in gps and "lon" in gps:
            max_time = profile.get("max_travel_time") or 60  
            mode = profile.get("travel_mode") or "vehicle"
            polygon_geo = invoke_isochrone_api(gps['lat'], gps['lon'], max_time, mode)
            
            if polygon_geo:
                isochrone_shape = shape(polygon_geo)
                st.info("🛰️ Filtering trails based on travel-time isochrone...")
                for trail in trails:
                    if trail.get("lat") and trail.get("lon"):
                        trail_point = Point(float(trail["lon"]), float(trail["lat"]))
                        if isochrone_shape.contains(trail_point):
                            viable_trails.append(trail)
            else:
                viable_trails = trails
        else:
            st.error("❌ Isochrone filtering selected, but GPS coordinates are unavailable!")
            viable_trails = trails

    elif strategy == "GEOLOCATOR":
        location_value = profile.get("location_value")
        if location_value:
            bbox = invoke_geocoding_api(location_value)
            if bbox:
                st.info(f"🌍 Filtering trails inside region boundary: {location_value}...")
                for trail in trails:
                    t_lat = trail.get("lat")
                    t_lon = trail.get("lon")
                    if t_lat and t_lon:
                        lat_match = bbox["min_lat"] <= float(t_lat) <= bbox["max_lat"]
                        lon_match = bbox["min_lon"] <= float(t_lon) <= bbox["max_lon"]
                        if lat_match and lon_match:
                            viable_trails.append(trail)
            else:
                viable_trails = trails
        else:
            viable_trails = trails
    else:
        viable_trails = trails

    return viable_trails
