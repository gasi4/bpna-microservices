import numpy as np
from scipy.interpolate import griddata


def interpolate_heatmap(
    measurements: list[dict],
    width_cells: int,
    height_cells: int,
    step_cm: int,
) -> dict:
    if len(measurements) < 3:
        return {"x": [], "y": [], "z": [], "min_rssi": -90, "max_rssi": -30}

    xs = np.array([point["x"] * step_cm for point in measurements], dtype=float)
    ys = np.array([point["y"] * step_cm for point in measurements], dtype=float)
    rssi_vals = np.array([point["rssi"] for point in measurements], dtype=float)

    grid_x = np.linspace(0, width_cells * step_cm, max(2, width_cells * 10))
    grid_y = np.linspace(0, height_cells * step_cm, max(2, height_cells * 10))
    grid_points = (grid_x[None, :], grid_y[:, None])

    try:
        grid_z = griddata((xs, ys), rssi_vals, grid_points, method="cubic", fill_value=np.nan)
    except Exception:
        grid_z = griddata((xs, ys), rssi_vals, grid_points, method="linear", fill_value=np.nan)

    nearest_z = griddata((xs, ys), rssi_vals, grid_points, method="nearest")
    if grid_z is None:
        grid_z = nearest_z
    else:
        grid_z = np.where(np.isnan(grid_z), nearest_z, grid_z)

    grid_z = np.clip(grid_z, float(np.min(rssi_vals)), float(np.max(rssi_vals)))
    grid_z = np.nan_to_num(grid_z, nan=float(np.mean(rssi_vals)))
    return {
        "x": grid_x.tolist(),
        "y": grid_y.tolist(),
        "z": grid_z.tolist(),
        "min_rssi": float(np.min(rssi_vals)),
        "max_rssi": float(np.max(rssi_vals)),
    }
