"""Read and plot the public FLARE Outlook arrays without any private inputs."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
CATEGORY_LABELS = ['Unavailable', 'Minimal', 'Low', 'Moderate', 'High', 'Very high', 'Extreme']


def catalog():
    return pd.DataFrame(json.loads((ROOT / 'manifest.json').read_text())['files'])


def file_for(date):
    rows = catalog().loc[lambda x: x.date == str(date)]
    if len(rows) != 1:
        raise ValueError('Choose an available issue date from catalog().')
    path = ROOT / rows.iloc[0]['file']
    if not path.is_file():
        raise FileNotFoundError(f'Place the daily NetCDF file at {path}')
    return path


def open_day(date):
    # Integer zero is a real "unavailable" class, not a masked fill value.
    return xr.open_dataset(file_for(date), engine='netcdf4')


def verify_file(date):
    row = catalog().loc[lambda x: x.date == str(date)].iloc[0]
    h = hashlib.sha256()
    with file_for(date).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    assert h.hexdigest() == row.sha256, 'Checksum mismatch'
    return True


def subset_bbox(ds, west, east, south, north):
    """Smallest native-grid rectangle covering bbox, with outside pixels masked."""
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('Use ordered longitude/latitude bounds, without antimeridian crossing.')
    lat, lon = ds.lat.values, ds.lon.values
    mask = (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
    rows, cols = np.where(mask)
    if not len(rows):
        raise ValueError('The requested bounds do not intersect the grid.')
    ys, xs = slice(rows.min(), rows.max()+1), slice(cols.min(), cols.max()+1)
    small = ds.isel(y=ys, x=xs).load()
    keep = xr.DataArray(mask[ys, xs], dims=('y', 'x'))
    for name in ('outlook_index', 'category'):
        small[name] = small[name].where(keep)
    return small


def nearest_pixel(ds, latitude, longitude, max_distance_km=25):
    """Find nearest native pixel using spherical distance; reject distant requests."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Invalid latitude or longitude.')
    best = (float('inf'), None, None)
    for start in range(0, ds.sizes['y'], 512):
        lat = np.deg2rad(ds.lat.isel(y=slice(start, start+512)).values)
        lon = np.deg2rad(ds.lon.isel(y=slice(start, start+512)).values)
        a = np.sin((lat-np.deg2rad(latitude))/2)**2 + np.cos(lat)*np.cos(np.deg2rad(latitude))*np.sin((lon-np.deg2rad(longitude))/2)**2
        distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        index = np.nanargmin(distance)
        row, col = np.unravel_index(index, distance.shape)
        if distance[row, col] < best[0]:
            best = (float(distance[row, col]), start+int(row), int(col))
    distance, row, col = best
    if distance > max_distance_km:
        raise ValueError(f'Nearest grid pixel is {distance:.1f} km away; request is outside the allowed distance.')
    return row, col, distance


def point_series(latitude, longitude):
    files = catalog()
    with open_day(files.iloc[0].date) as ds:
        row, col, distance = nearest_pixel(ds, latitude, longitude)
        grid_lat, grid_lon = float(ds.lat[row, col]), float(ds.lon[row, col])
    records = []
    for date in files.date:
        with open_day(date) as ds:
            assert float(ds.lat[row, col]) == grid_lat and float(ds.lon[row, col]) == grid_lon
            records.append(dict(issue=pd.Timestamp(ds.attrs['forecast_issue_time']),
                                valid_start=pd.Timestamp(ds.attrs['time_coverage_start']),
                                valid_end=pd.Timestamp(ds.attrs['time_coverage_end']),
                                **{k: ds[k][row, col].item() for k in ('outlook_index', 'category')}))
    result = pd.DataFrame(records)
    result.attrs.update(row=row, col=col, latitude=grid_lat, longitude=grid_lon, distance_km=distance)
    return result


def plot_maps(ds, stride=8, extent=(-130, -94, 29, 53)):
    """Two geographic panels; stride affects display only, never stored data."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    import cartopy.crs as ccrs
    from cartopy.io.shapereader import Reader
    if not isinstance(stride, int) or stride < 1:
        raise ValueError('stride must be a positive integer')
    view = ds.isel(y=slice(None, None, stride), x=slice(None, None, stride)).load()
    country_path = ROOT / 'assets/natural_earth/ne_110m_admin_0_countries.shp'
    states_path = ROOT / 'assets/natural_earth/ne_110m_admin_1_states_provinces_lines.shp'
    countries = list(Reader(country_path).geometries())
    states = list(Reader(states_path).geometries())
    projection = ccrs.PlateCarree()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.7), subplot_kw={'projection': projection})
    fig.subplots_adjust(left=.035, right=.985, top=.79, bottom=.15, wspace=.13)
    for ax, key in zip(axes, ('outlook_index', 'category')):
        ax.set_facecolor('white')
        ax.set_extent(extent, crs=projection)
        kwargs = dict(cmap='YlOrRd', vmin=0, vmax=1)
        if key == 'category':
            cmap = ListedColormap(['white', '#d9ef8b', '#91cf60', '#fee08b', '#fc8d59', '#d73027', '#7f0000'])
            kwargs = dict(cmap=cmap, norm=BoundaryNorm(np.arange(-.5, 7.5), cmap.N))
        mesh = ax.pcolormesh(view.lon.values, view.lat.values, view[key].values,
                             transform=projection, shading='auto', rasterized=True, **kwargs)
        ax.add_geometries(countries, crs=projection, facecolor='none', edgecolor='#353535', linewidth=.65)
        ax.add_geometries(states, crs=projection, facecolor='none', edgecolor='#606060', linewidth=.4)
        grid = ax.gridlines(draw_labels=True, linewidth=.3, alpha=.4)
        grid.top_labels = grid.right_labels = False
        ax.text(.5, 1.025, view[key].attrs.get('long_name', key), transform=ax.transAxes,
                ha='center', va='bottom', fontsize=12)
        cb = fig.colorbar(mesh, ax=ax, orientation='horizontal', pad=.07, fraction=.05)
        if key == 'category':
            labels = CATEGORY_LABELS
            cb.set_ticks(range(len(labels)), labels=labels)
            cb.ax.tick_params(labelsize=8, rotation=35)
    fig.suptitle('FLARE Outlook v11 | Issue ' + ds.attrs['forecast_issue_time'] + '\nValid ' + ds.attrs['time_coverage_start'] + ' to ' + ds.attrs['time_coverage_end'], fontsize=13, y=.97)
    return fig
