"""Read one FireOutlook2.0 issuance without confusing leads with issue dates."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'seven_day' / 'wheeler_20261102.nc'
LABELS = ['Unavailable', 'Minimal', 'Low', 'Moderate', 'High', 'Very high', 'Extreme']
COLORS = ['#d5dad8', '#287844', '#8dca69', '#f4db64', '#f99743', '#dc4738', '#9f143a']


def open_sample(path=SAMPLE, verify=True):
    path = Path(path)
    if verify:
        manifest = json.loads((path.parent / 'manifest.json').read_text())
        if path.name != manifest['file']:
            raise ValueError('The manifest describes a different file')
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Sample checksum mismatch')
    ds = xr.open_dataset(path, engine='netcdf4', mask_and_scale=False)
    try:
        validate(ds)
    except Exception:
        ds.close()
        raise
    return ds


def validate(ds):
    if 'issue_time' in ds.dims:
        raise ValueError('Select exactly one issuance before using this reader')
    for name in ('outlook_index', 'outlook_category', 'quality_flags', 'latitude',
                 'longitude', 'complete', 'valid_start', 'valid_end', 'weather_model',
                 'weather_cycle'):
        if name not in ds:
            raise ValueError(f'Missing required array: {name}')
    if not np.array_equal(ds.forecast_day.values, np.arange(1, 8)):
        raise ValueError('Expected forecast_day 1 through 7')
    for name in ('outlook_index', 'outlook_category', 'quality_flags'):
        if ds[name].dims != ('forecast_day', 'y', 'x'):
            raise ValueError(f'Unexpected dimensions for {name}')
    starts, ends = ds.valid_start.values, ds.valid_end.values
    if not np.all(ends - starts == np.timedelta64(24, 'h')):
        raise ValueError('Each forecast must cover 24 hours')
    if not np.all(starts[1:] == ends[:-1]):
        raise ValueError('Forecast windows must be consecutive')
    issue = np.datetime64(pd.Timestamp(ds.attrs['issue_time']).tz_convert(None))
    if not np.all(ds.weather_cycle.values <= issue):
        raise ValueError('Weather initialization is later than issuance')
    if not np.all(starts >= issue):
        raise ValueError('Valid period begins before issuance')
    edges = np.asarray(ds.attrs['category_edges'], dtype=float)
    if edges.shape != (5,) or not np.all(np.diff(edges) > 0):
        raise ValueError('Expected five ordered category edges')


def select_day(ds, day):
    if day not in range(1, 8):
        raise ValueError('Choose a forecast day from 1 to 7')
    result = ds.sel(forecast_day=day)
    if not bool(result.complete.item()):
        raise ValueError(f'Day {day} is incomplete and cannot be displayed')
    return result


def schedule(ds):
    return pd.DataFrame({
        'forecast_day': ds.forecast_day.values,
        'valid_start_UTC': pd.to_datetime(ds.valid_start.values, utc=True),
        'valid_end_UTC': pd.to_datetime(ds.valid_end.values, utc=True),
        'weather_cycle_UTC': pd.to_datetime(ds.weather_cycle.values, utc=True),
        'weather_model': ds.weather_model.values.astype(str),
        'complete': ds.complete.values.astype(bool),
    })


def point_forecast(ds, latitude, longitude, max_distance_km=5):
    lat = np.deg2rad(ds.latitude.values)
    lon = np.deg2rad(ds.longitude.values)
    a = (np.sin((lat - np.deg2rad(latitude)) / 2) ** 2
         + np.cos(lat) * np.cos(np.deg2rad(latitude))
         * np.sin((lon - np.deg2rad(longitude)) / 2) ** 2)
    distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    y, x = np.unravel_index(np.nanargmin(distance), distance.shape)
    if distance[y, x] > max_distance_km:
        raise ValueError('Requested location is outside the sample coverage')
    rows = []
    for day in range(1, 8):
        selected = select_day(ds, day).isel(y=y, x=x)
        category = int(selected.outlook_category.item())
        rows.append({
            'forecast_day': day,
            'index': float(selected.outlook_index.item()) if category else np.nan,
            'category': LABELS[category],
            'quality_flags': int(selected.quality_flags.item()),
            'latitude': float(selected.latitude.item()),
            'longitude': float(selected.longitude.item()),
            'distance_km': float(distance[y, x]),
        })
    return schedule(ds).merge(pd.DataFrame(rows), on='forecast_day')


def flag_names(ds, value):
    meanings = ds.attrs['quality_flag_meanings']
    if isinstance(meanings, str):
        meanings = json.loads(meanings)
    return [meaning for bit, meaning in meanings.items() if value & int(bit)]


def plot_week(ds):
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.ticker import MaxNLocator
    fig, axes = plt.subplots(2, 4, figsize=(14, 8), constrained_layout=True)
    cmap = ListedColormap(COLORS)
    norm = BoundaryNorm(np.arange(-0.5, 7.5), 7)
    for day, ax in zip(range(1, 8), axes.flat):
        layer = select_day(ds, day)
        mesh = ax.pcolormesh(ds.longitude, ds.latitude, layer.outlook_category,
                             cmap=cmap, norm=norm, shading='auto', rasterized=True)
        ax.set_aspect(1 / np.cos(np.deg2rad(float(ds.latitude.mean()))))
        start = pd.Timestamp(layer.valid_start.item()).strftime('%b %d')
        ax.set_title(f'Day {day} | {start} 12 UTC', fontsize=11)
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.tick_params(labelsize=8)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_locator(MaxNLocator(4))
    axes.flat[-1].axis('off')
    fig.colorbar(mesh, ax=list(axes.flat), orientation='horizontal', fraction=.045,
                 ticks=range(7)).ax.set_xticklabels(LABELS)
    fig.suptitle(f"FLARE FireOutlook | issued {ds.attrs['issue_time']}\n"
                 'Native-grid sample around Wheeler County, Oregon', fontsize=14)
    return fig
