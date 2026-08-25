def build_aoi_from_jobs(jobs, padding=0.005):
    latitudes = [job["latitude"] for job in jobs]
    longitudes = [job["longitude"] for job in jobs]

    min_lat = min(latitudes) - padding
    max_lat = max(latitudes) + padding
    min_lon = min(longitudes) - padding
    max_lon = max(longitudes) + padding

    coordinates = [[
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat]
    ]]

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coordinates
                }
            }
        ]
    }