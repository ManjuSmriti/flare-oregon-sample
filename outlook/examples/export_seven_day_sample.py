"""Export a lossless native-grid window from one complete issuance."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import xarray as xr

from seven_day import validate


def export(source, destination):
    source = Path(source)
    destination = Path(destination)
    ds = xr.open_zarr(source, consolidated=True, mask_and_scale=False, chunks=None)
    validate(ds)
    if not np.all(ds.complete.values):
        raise ValueError('All seven leads must be complete before export')
    # Find a native-grid rectangle around the county without interpolating pixels.
    matches = []
    for start in range(0, ds.sizes['y'], 512):
        lat = ds.latitude.isel(y=slice(start, start + 512)).values
        lon = ds.longitude.isel(y=slice(start, start + 512)).values
        yy, xx = np.where((lat >= 44.5) & (lat <= 45.2) & (lon >= -120.6) & (lon <= -119.6))
        if yy.size:
            matches.append((start + yy.min(), start + yy.max(), xx.min(), xx.max()))
    if not matches:
        raise ValueError('Requested geographic region is absent')
    window = [min(v[0] for v in matches), max(v[1] for v in matches) + 1,
              min(v[2] for v in matches), max(v[3] for v in matches) + 1]
    names = ['outlook_index', 'outlook_category', 'quality_flags', 'latitude',
             'longitude', 'complete', 'valid_start', 'valid_end', 'weather_cycle', 'weather_model']
    sample = ds[names].isel(y=slice(*window[:2]), x=slice(*window[2:])).load()
    safe_keys = ['algorithm_version', 'category_edges', 'forecast_policy', 'grid_signature',
                 'index_interpretation', 'issue_time', 'product_name', 'publication_rule',
                 'quality_flag_meanings', 'source_issue_signature']
    sample.attrs = {key: ds.attrs[key] for key in safe_keys}
    sample.attrs['quality_flag_meanings'] = json.dumps(sample.attrs['quality_flag_meanings'])
    sample.attrs['sample_scope'] = 'Native-grid rectangle around Wheeler County; not the full western domain'
    sample.attrs['source_grid_window_y0_y1_x0_x1'] = window
    sample.attrs['source_grid_shape'] = [ds.sizes['y'], ds.sizes['x']]
    for name in sample.variables:
        sample[name].encoding = {}
        sample[name].attrs.pop('_FillValue', None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoding = {name: {'zlib': True, 'complevel': 6, '_FillValue': None}
                for name in names if sample[name].ndim >= 2}
    sample.to_netcdf(destination, engine='netcdf4', encoding=encoding)
    with xr.open_dataset(destination, engine='netcdf4', mask_and_scale=False) as saved:
        validate(saved)
        for name in names + ['forecast_day']:
            np.testing.assert_equal(saved[name].values, sample[name].values)
    manifest = {
        'file': destination.name,
        'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        'bytes': destination.stat().st_size,
        'issue_time': sample.attrs['issue_time'],
        'algorithm_version': sample.attrs['algorithm_version'],
        'source_issue_signature': sample.attrs['source_issue_signature'],
        'source_grid_window_y0_y1_x0_x1': [int(v) for v in window],
        'sample_shape': dict(sample.sizes),
        'verification': 'All exported values equal source window, including NaN positions; no resampling',
    }
    (destination.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
    ds.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Complete single-issuance Zarr')
    parser.add_argument('destination', help='Output NetCDF path')
    args = parser.parse_args()
    export(args.source, args.destination)
