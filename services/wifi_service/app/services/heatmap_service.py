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

    xs = [point["x"] * step_cm for point in measurements]
    ys = [point["y"] * step_cm for point in measurements]
    rssi_vals = [point["rssi"] for point in measurements]

    grid_x = np.linspace(0, width_cells * step_cm, width_cells * 10)
    grid_y = np.linspace(0, height_cells * step_cm, height_cells * 10)

    try:
        grid_z = griddata(
            (xs, ys),
            rssi_vals,
            (grid_x[None, :], grid_y[:, None]),
            method="cubic",
            fill_value=-90,
        )
    except Exception:
        grid_z = griddata(
            (xs, ys),
            rssi_vals,
            (grid_x[None, :], grid_y[:, None]),
            method="nearest",
            fill_value=-90,
        )

    grid_z = np.nan_to_num(grid_z, nan=-90)
    return {
        "x": grid_x.tolist(),
        "y": grid_y.tolist(),
        "z": grid_z.tolist(),
        "min_rssi": float(np.min(rssi_vals)),
        "max_rssi": float(np.max(rssi_vals)),
    }
