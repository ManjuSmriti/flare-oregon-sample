"""Export seven issuances for July 15 from the original July FireOutlook archive."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
import xarray as xr

from seven_day import validate


def export(source, county_file, reference_file, destination):
    destination = Path(destination)
    ds = xr.open_zarr(source, consolidated=True, mask_and_scale=False, chunks=None)
    spatial = dict(y=slice(1088, 1664), x=slice(1680, 2496))
    fields = ['outlook_index', 'outlook_category', 'quality_flags', 'complete',
              'valid_start', 'valid_end', 'weather_cycle', 'weather_model']
    rows, signatures = [], {}
    for utc_day in range(9, 16):
        issue = np.datetime64(f'2026-07-{utc_day:02}T03:00')
        row = ds[fields].sel(issue_time=issue, forecast_day=16-utc_day).isel(**spatial).load()
        if not bool(row.complete.item()):
            raise ValueError('Incomplete source forecast')
        row = row.expand_dims(issue_time=[issue])
        row['forecast_day'] = ('issue_time', [16-utc_day])
        rows.append(row)
        minute = str(int(issue.astype('datetime64[m]').astype(int)))
        signatures[str(issue)] = ds.attrs['issue_signatures'][minute]
    sample = xr.concat(rows, dim='issue_time')
    for name in ['latitude', 'longitude', 'pixel_area']:
        sample[name] = ds[name].isel(**spatial).load()
    county = json.loads(Path(county_file).read_text())
    geometry = shape(county['features'][0]['geometry'])
    sample['county_mask'] = (('y', 'x'), shapely.contains_xy(
        geometry, sample.longitude.values, sample.latitude.values).astype('uint8'))
    sample.attrs = {key: ds.attrs[key] for key in ['category_edges', 'forecast_policy',
        'grid_signature', 'index_interpretation', 'product']}
    sample.attrs.update({
        'quality_flag_meanings': json.dumps(ds.attrs['quality_flag_meanings']),
        'issue_signatures': json.dumps(signatures),
        'sample_scope': 'Native-grid window containing Wheeler County, Oregon',
        'source_grid_window_y0_y1_x0_x1': [1088, 1664, 1680, 2496],
        'target_valid_start': '2026-07-15T12:00:00Z',
        'target_valid_end': '2026-07-16T12:00:00Z',
        'issuance_dates_local': 'July 8-14, 2026, 20:00 PDT',
        'experiment_type': 'historical forecast replay',
        'county_method': 'Pixel-center inclusion weighted by source pixel_area; denominator includes all county centers',
    })
    validate(sample)
    for name in sample.variables:
        sample[name].encoding = {}
        sample[name].attrs.pop('_FillValue', None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix('.partial.nc')
    sample.to_netcdf(partial, engine='netcdf4', encoding={
        name: {'zlib': True, 'complevel': 6, '_FillValue': None}
        for name in sample.data_vars if sample[name].ndim >= 2})
    with xr.open_dataset(partial, engine='netcdf4', mask_and_scale=False) as saved:
        validate(saved)
        for name in sample.variables:
            np.testing.assert_equal(saved[name].values, sample[name].values)
    partial.replace(destination)
    features = [dict(county['features'][0], properties={'name': 'Wheeler County', 'role': 'county'})]
    names = ['Crosswhite', 'Red Rock', 'Twickenham', 'Camel Hump', 'Cove Creek']
    colors = ['#3a66ff', '#c05cff', '#f349b5', '#00a5c0', '#9f8500']
    raw = json.loads(Path(reference_file).read_text())
    codes = ['000445', '000442', '000444', '000446', '000450']
    for number, (name, color, code) in enumerate(zip(names, colors, codes), 1):
        original = next(f for f in raw['features'] if f['properties']['attr_UniqueFireIdentifier'].endswith(code))
        p = original['properties']
        props = {'name': name, 'number': number, 'color': color,
                 'source': p['poly_Source'], 'irwin_id': p['poly_IRWINID'],
                 'record_current_utc': pd.to_datetime(p['poly_DateCurrent'], unit='ms', utc=True).isoformat(),
                 'role': 'later observed reference perimeter'}
        features.append({'type': 'Feature', 'properties': props, 'geometry': original['geometry']})
        features.append({'type': 'Feature', 'properties': dict(props, role='reported origin'),
                         'geometry': {'type': 'Point', 'coordinates': [p['attr_InitialLongitude'], p['attr_InitialLatitude']]}})
    refs = destination.parent / 'references.geojson'
    refs.write_text(json.dumps({'type': 'FeatureCollection', 'features': features,
        'county_source': county.get('source'), 'county_vintage': county.get('vintage'),
        'perimeter_source': 'NIFC/WFIGS retained NIFS history, July 16-17, 2026',
        'purpose': 'Reference geography for interpretation, not forecast fire boundaries'}, separators=(',', ':')))
    manifest = {'file': destination.name, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        'references_sha256': hashlib.sha256(refs.read_bytes()).hexdigest(),
        'bytes': destination.stat().st_size, 'product': ds.attrs['product'],
        'issue_signatures': signatures, 'sample_shape': dict(sample.sizes),
        'source_grid_window_y0_y1_x0_x1': [1088, 1664, 1680, 2496],
        'target_valid_start': sample.attrs['target_valid_start'], 'target_valid_end': sample.attrs['target_valid_end'],
        'verification': 'Every exported forecast, coordinate and area value equals its source window, including NaNs; no resampling'}
    (destination.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
    ds.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ['source', 'county_file', 'reference_file', 'destination']:
        parser.add_argument(arg)
    export(**vars(parser.parse_args()))
