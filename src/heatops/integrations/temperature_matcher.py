from shapely.geometry import Point, shape


def match_jobs_to_temperatures(jobs, features):
    """
    Match each job location to the FortyGuard heatmap tile
    containing that location.

    Returns jobs with temperature information attached.
    """

    matched_jobs = []

    for job in jobs:
        point = Point(
            job["longitude"],
            job["latitude"]
        )

        matched_feature = None

        for feature in features:
            polygon = shape(feature["geometry"])

            if polygon.covers(point):
                matched_feature = feature
                break

        if matched_feature is None:
            matched_jobs.append({
                **job,
                "temperature": None,
                "tile_id": None
            })
            continue

        properties = matched_feature["properties"]

        matched_jobs.append({
            **job,
            "temperature": properties["average_temperature"],
            "tile_id": properties["tile_id"]
        })

    return matched_jobs