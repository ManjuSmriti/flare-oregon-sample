"""Seven successive issuances for one fixed July 15 forecast window."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'seven_day' / 'wheeler_target_20260715.nc'
LABELS = ['Unavailable', 'Minimal', 'Low', 'Moderate', 'High', 'Very high', 'Extreme']
COLORS = ['#d5dad8', '#006837', '#66bd63', '#d9ef8b', '#fee08b', '#f46d43', '#a50026']
TZ = 'America/Los_Angeles'


def references():
    return json.loads((SAMPLE.parent / 'references.geojson').read_text())


def open_sample(path=SAMPLE, verify=True):
    path = Path(path)
    if verify:
        manifest = json.loads((path.parent / 'manifest.json').read_text())
        if path.name != manifest['file']:
            raise ValueError('The manifest describes a different file')
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Sample checksum mismatch')
        ref = path.parent / 'references.geojson'
        if hashlib.sha256(ref.read_bytes()).hexdigest() != manifest['references_sha256']:
            raise ValueError('Reference checksum mismatch')
    ds = xr.open_dataset(path, engine='netcdf4', mask_and_scale=False)
    try:
        validate(ds)
    except Exception:
        ds.close()
        raise
    return ds


def validate(ds):
    for name in ('outlook_index', 'outlook_category', 'quality_flags', 'latitude',
                 'longitude', 'complete', 'valid_start', 'valid_end', 'weather_model',
                 'weather_cycle', 'forecast_day', 'county_mask', 'pixel_area'):
        if name not in ds:
            raise ValueError(f'Missing required array: {name}')
    if not np.array_equal(ds.forecast_day.values, np.arange(7, 0, -1)):
        raise ValueError('Expected successive issuances with leads 7 through 1')
    for name in ('outlook_index', 'outlook_category', 'quality_flags'):
        if ds[name].dims != ('issue_time', 'y', 'x'):
            raise ValueError(f'Unexpected dimensions for {name}')
    issues = ds.issue_time.values
    if not np.all(np.diff(issues) == np.timedelta64(24, 'h')):
        raise ValueError('Issuances must be consecutive daily updates')
    if not np.all(ds.valid_start.values == np.datetime64('2026-07-15T12:00')):
        raise ValueError('Every update must target July 15 at 12 UTC')
    if not np.all(ds.valid_end.values == np.datetime64('2026-07-16T12:00')):
        raise ValueError('Every update must end July 16 at 12 UTC')
    if not np.all(ds.weather_cycle.values <= issues):
        raise ValueError('Weather initialization is later than issuance')
    expected = (ds.valid_start.values.astype('datetime64[D]')
                - issues.astype('datetime64[D]')).astype(int) + 1
    if not np.array_equal(expected, ds.forecast_day.values):
        raise ValueError('Lead and issuance do not match the fixed target')
    edges = np.asarray(ds.attrs['category_edges'], dtype=float)
    if edges.shape != (5,) or not np.all(np.diff(edges) > 0):
        raise ValueError('Expected five ordered category edges')


def select_update(ds, index):
    if index not in range(7):
        raise ValueError('Choose update index 0 through 6')
    layer = ds.isel(issue_time=index)
    if not bool(layer.complete.item()):
        raise ValueError('This update is incomplete and cannot be displayed')
    return layer


def schedule(ds):
    return pd.DataFrame({
        'issued_PDT': pd.to_datetime(ds.issue_time.values, utc=True).tz_convert(TZ),
        'issued_UTC': pd.to_datetime(ds.issue_time.values, utc=True),
        'forecast_day': ds.forecast_day.values,
        'valid_start_PDT': pd.to_datetime(ds.valid_start.values, utc=True).tz_convert(TZ),
        'valid_end_PDT': pd.to_datetime(ds.valid_end.values, utc=True).tz_convert(TZ),
        'weather_cycle_UTC': pd.to_datetime(ds.weather_cycle.values, utc=True),
        'weather_model': ds.weather_model.values.astype(str),
        'complete': ds.complete.values.astype(bool),
    })


def point_forecast(ds, latitude, longitude, max_distance_km=5):
    lat, lon = np.deg2rad(ds.latitude.values), np.deg2rad(ds.longitude.values)
    a = (np.sin((lat - np.deg2rad(latitude)) / 2) ** 2
         + np.cos(lat) * np.cos(np.deg2rad(latitude))
         * np.sin((lon - np.deg2rad(longitude)) / 2) ** 2)
    distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    y, x = np.unravel_index(np.nanargmin(distance), distance.shape)
    if distance[y, x] > max_distance_km:
        raise ValueError('Requested location is outside the sample coverage')
    rows = []
    for i in range(7):
        selected = select_update(ds, i).isel(y=y, x=x)
        category = int(selected.outlook_category.item())
        rows.append({'index': float(selected.outlook_index.item()) if category else np.nan,
                     'category': LABELS[category], 'category_code': category,
                     'quality_flags': int(selected.quality_flags.item()),
                     'latitude': float(selected.latitude.item()),
                     'longitude': float(selected.longitude.item()),
                     'distance_km': float(distance[y, x])})
    return pd.concat([schedule(ds), pd.DataFrame(rows)], axis=1)


def county_statistics(ds):
    area = ds.pixel_area.values.astype('float64')
    mask = ds.county_mask.values.astype(bool)
    total = area[mask].sum()
    rows = []
    for i in range(7):
        cat = select_update(ds, i).outlook_category.values
        rows.append({'county_high_or_above_pct': 100 * area[mask & (cat >= 4)].sum() / total,
                     'county_scored_pct': 100 * area[mask & (cat > 0)].sum() / total})
    return pd.concat([schedule(ds), pd.DataFrame(rows)], axis=1)


def flag_names(ds, value):
    meanings = ds.attrs['quality_flag_meanings']
    if isinstance(meanings, str):
        meanings = json.loads(meanings)
    return [meaning for bit, meaning in meanings.items() if value & int(bit)]


def draw_update(ds, index, ax, context):
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.ticker import MaxNLocator
    layer = select_update(ds, index)
    mesh = ax.pcolormesh(ds.longitude, ds.latitude, layer.outlook_category,
                         cmap=ListedColormap(COLORS), norm=BoundaryNorm(np.arange(-.5, 7.5), 7),
                         shading='auto', rasterized=True)
    for feature in context['features']:
        geom, props = feature['geometry'], feature['properties']
        if geom['type'] == 'Point':
            x, y = geom['coordinates']
            ax.scatter(x, y, s=18, facecolor='white', edgecolor='#172f29', zorder=5)
            ax.annotate(str(props['number']), (x, y), xytext=(3, 3), textcoords='offset points', fontsize=8)
        else:
            polygons = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
            for polygon in polygons:
                for ring in polygon:
                    xy = np.asarray(ring)
                    ax.plot(xy[:, 0], xy[:, 1], color=props.get('color', '#20352d'), lw=.85)
    ax.set(xlim=(-120.65, -119.6), ylim=(44.25, 45.15))
    ax.set_aspect(1 / np.cos(np.deg2rad(44.75)))
    label = pd.Timestamp(layer.issue_time.item()).tz_localize('UTC').tz_convert(TZ).strftime('%b %d')
    ax.set_title(f'Issued {label}, 8 p.m. PDT | Day {int(layer.forecast_day)}', fontsize=10)
    ax.tick_params(labelsize=8)
    ax.xaxis.set_major_locator(MaxNLocator(3))
    ax.yaxis.set_major_locator(MaxNLocator(4))
    return mesh


def plot_progression(ds):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 4, figsize=(15, 9), constrained_layout=True)
    context = references()
    for i, ax in enumerate(list(axes.flat)[:7]):
        mesh = draw_update(ds, i, ax, context)
    axes.flat[-1].axis('off')
    labels = [f"{f['properties']['number']}  {f['properties']['name']}"
              for f in context['features'] if f['geometry']['type'] == 'Point']
    axes.flat[-1].text(0, .9, 'Reported fire locations\n\n' + '\n'.join(labels)
                       + '\n\nJuly 16-17 outlines:\nreference observations', va='top', fontsize=11)
    fig.colorbar(mesh, ax=list(axes.flat), orientation='horizontal', fraction=.04,
                 ticks=range(7)).ax.set_xticklabels(LABELS)
    fig.suptitle('FLARE FireOutlook for July 15, 2026\nSeven evening updates, July 8-14 PDT', fontsize=16)
    return fig
