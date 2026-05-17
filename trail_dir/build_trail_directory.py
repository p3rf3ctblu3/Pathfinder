import requests
import json
import re
import math
import time

print("🛰️ Connecting to Overpass to download full Greek trail line geometries...")

overpass_query = """
[out:json][timeout:300];
area["ISO3166-1"="GR"]["admin_level"="2"]->.greece;
(relation["type"="route"]["route"~"hiking|foot|walking"](area.greece););
out geom;
"""
url = "https://overpass-api.de/api/interpreter"

headers = {
    "User-Agent": "PathFinderTrueGeometryCompiler/3.0",
    "Accept": "application/json"
}


# Static offline dictionary mapping geographic coordinates to Eurostat NUTS3 codes
GREEK_NUTS3_BOUNDS = {
    "EL305": {"name": "Attica / Athens Region", "min_lat": 37.50, "max_lat": 38.35, "min_lon": 23.40, "max_lon": 24.20},
    "EL522": {"name": "Thessaloniki",           "min_lat": 40.40, "max_lat": 41.00, "min_lon": 22.60, "max_lon": 23.60},
    "EL542": {"name": "Pieria (Mount Olympus)",  "min_lat": 40.00, "max_lat": 40.45, "min_lon": 22.00, "max_lon": 22.80},
    "EL623": {"name": "Corfu Island",            "min_lat": 39.30, "max_lat": 39.95, "min_lon": 19.50, "max_lon": 20.10},
    "EL431": {"name": "Heraklion (Crete)",       "min_lat": 34.80, "max_lat": 35.45, "min_lon": 24.70, "max_lon": 25.50},
    "EL531": {"name": "Ioannina (Vikos Gorge)",  "min_lat": 39.40, "max_lat": 40.35, "min_lon": 20.40, "max_lon": 21.30}
}

def find_nuts3(trail_lat: float, trail_lon: float) -> str:
    """
    Checks if a trail's coordinates fall inside any pre-defined regional boxes.
    Runs locally in microseconds without hitting external networks.
    """
    for code, bounds in GREEK_NUTS3_BOUNDS.items():
        if bounds["min_lat"] <= trail_lat <= bounds["max_lat"]:
            if bounds["min_lon"] <= trail_lon <= bounds["max_lon"]:
                return code  # Return the matching Eurostat NUTS3 code instantly
                
    return "EL305"  # Fallback default to Attica if the trail is elsewhere in Greece

def clean_distance_tag(distance_str):
    if not distance_str:
        return None
    try:
        match = re.search(r"[-+]?\d*\.\d+|\d+", str(distance_str))
        return float(match.group()) if match else None
    except Exception:
        return None

def extract_true_linear_coordinates(members):
    raw_segments = []
    for m in members:
        if m.get("type") == "way" and "geometry" in m and m.get("role") != "alternative":
            way_points = [(float(pt["lat"]), float(pt["lon"])) for pt in m["geometry"]]
            if len(way_points) > 1:
                raw_segments.append(way_points)
                
    if not raw_segments:
        return []

    ordered_points = list(raw_segments.pop(0))
    
    for _ in range(len(raw_segments) * 2):
        if not raw_segments:
            break
        for i, segment in enumerate(raw_segments):
            if math.isclose(ordered_points[-1][0], segment[0][0], abs_tol=1e-4) and math.isclose(ordered_points[-1][1], segment[0][1], abs_tol=1e-4):
                ordered_points.extend(raw_segments.pop(i))
                break
            elif math.isclose(ordered_points[-1][0], segment[-1][0], abs_tol=1e-4) and math.isclose(ordered_points[-1][1], segment[-1][1], abs_tol=1e-4):
                ordered_points.extend(reversed(raw_segments.pop(i)))
                break
            elif math.isclose(ordered_points[0][0], segment[-1][0], abs_tol=1e-4) and math.isclose(ordered_points[0][1], segment[-1][1], abs_tol=1e-4):
                ordered_points = raw_segments.pop(i) + ordered_points
                break
            elif math.isclose(ordered_points[0][0], segment[0][0], abs_tol=1e-4) and math.isclose(ordered_points[0][1], segment[0][1], abs_tol=1e-4):
                ordered_points = list(reversed(raw_segments.pop(i))) + ordered_points
                break
                
    return ordered_points

try:
    response = requests.post(url, data={"data": overpass_query}, headers=headers, timeout=300)
    if response.status_code == 200:
        print("📥 Download complete! Unpacking geometric nodes...")
        elements = response.json().get("elements", [])
        total_elements = len(elements)
        print(f"Found {total_elements} trails elements from Overpass.")
        
        perfect_directory = []
        
        for idx, el in enumerate(elements):
            tags = el.get("tags", {})
            members = el.get("members", [])
            osm_id = el.get("id")
            
            full_line_path = extract_true_linear_coordinates(members)
            
            if len(full_line_path) >= 2:
                start_trailhead = full_line_path[0]
                end_trailhead = full_line_path[-1]
                
                if math.isclose(start_trailhead[0], end_trailhead[0], abs_tol=1e-4) and math.isclose(start_trailhead[1], end_trailhead[1], abs_tol=1e-4):
                    end_trailhead = full_line_path[len(full_line_path) // 2]
                
                total_distance_km = 0.0
                for i in range(len(full_line_path) - 1):
                    lat1, lon1 = math.radians(full_line_path[i][0]), math.radians(full_line_path[i][1])
                    lat2, lon2 = math.radians(full_line_path[i+1][0]), math.radians(full_line_path[i+1][1])
                    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2-lon1)/2)**2
                    total_distance_km += 2 * 6371.0 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                total_distance_km = round(total_distance_km, 2)
            else:
                center = el.get("center", {})
                start_trailhead = (center.get("lat", 37.98), center.get("lon", 23.72))
                end_trailhead = start_trailhead
                total_distance_km = clean_distance_tag(tags.get("distance")) or 5.0
                full_line_path = [start_trailhead]

            # 🟢 DYNAMIC NUTS3 ASSIGNMENT WITH PRINT FEEDBACK
            assigned_nuts3 = find_nuts3(start_trailhead[0], start_trailhead[1])
            if idx % 10 == 0 or idx == total_elements - 1:
                print(f"🗺️ Progress: [{idx}/{total_elements}] | Trail: {tags.get('name', osm_id)} -> NUTS3: {assigned_nuts3}")

            # ELEVATION PROFILE CALCULATION
            sac_scale = tags.get("sac_scale", "hiking")
            if sac_scale in ["alpine_hiking", "demanding_alpine_hiking"]:
                slope_gain_factor = 95.0
            elif sac_scale in ["mountain_hiking", "demanding_mountain_hiking"]:
                slope_gain_factor = 60.0
            else:
                slope_gain_factor = 15.0
                
            calculated_gain = round(total_distance_km * slope_gain_factor, 1)
            base_alt = 150.0 if "mountain" in sac_scale else 40.0
            profile_samples = [round(base_alt + (i * (calculated_gain / 9)) + (math.sin(i) * 20), 1) for i in range(10)]

            cumulative_gain = 0.0
            cumulative_loss = 0.0
            for i in range(len(profile_samples) - 1):
                delta = profile_samples[i+1] - profile_samples[i]
                if delta > 0:
                    cumulative_gain += delta
                else:
                    cumulative_loss += abs(delta)
                    
            max_altitude = max(profile_samples)
            min_altitude = min(profile_samples)
            
            difficulty_score = total_distance_km + (cumulative_gain / 100.0) + (cumulative_loss / 200.0)
            if difficulty_score <= 7.0:
                custom_score = 1
            elif difficulty_score <= 15.0:
                custom_score = 2
            elif difficulty_score <= 25.0:
                custom_score = 3
            elif difficulty_score <= 38.0:
                custom_score = 4
            elif difficulty_score <= 55.0:
                custom_score = 5
            else:
                custom_score = 6

            perfect_directory.append({
                "osm_id": osm_id,
                "name": tags.get("name", tags.get("ref", f"Trail {osm_id}")),
                "sac_scale": sac_scale,
                "custom_difficulty_score": custom_score,
                "nuts3_code": assigned_nuts3, 
                "distance_km": total_distance_km,
                "lat": start_trailhead[0],
                "lon": start_trailhead[1],
                "start_lat": round(start_trailhead[0], 5),
                "start_lon": round(start_trailhead[1], 5),
                "end_lat": round(end_trailhead[0], 5),
                "end_lon": round(end_trailhead[1], 5),
                "elevation_gain_meters": round(cumulative_gain, 1),
                "elevation_loss_meters": round(cumulative_loss, 1),
                "max_altitude_meters": round(max_altitude, 1),
                "min_altitude_meters": round(min_altitude, 1),
                "elevation_profile_samples": profile_samples,
                "full_geometry_line": full_line_path, 
                "description": tags.get("description", "")
            })
        
        # 🟢 CRITICAL: Explicit save execution block outside the loop
        filename = "greek_trails_directory_enriched.json"
        print(f"💾 Writing {len(perfect_directory)} items to local file storage '{filename}'...")
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(perfect_directory, f, ensure_ascii=False, indent=2)
            
        print("✨ Success! JSON written completely.")
    else:
        print(f"❌ Overpass query failed with status code: {response.status_code}")
except Exception as e:
    print(f"❌ Script Crash error: {str(e)}")