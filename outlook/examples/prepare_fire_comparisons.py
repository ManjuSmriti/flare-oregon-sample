"""Fetch small native-grid county subsets; run explicitly, not on notebook import."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import io
import json
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds
import xarray as xr
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'assets/fire_comparisons/numerical'
DATES = [f'2026-07-{d}' for d in range(13, 17)]
county = shape(json.loads((ROOT / 'assets/boundaries/wheeler_county_41069.geojson').read_text())['features'][0]['geometry'])

def save(product, day, values, lon_edges, lat_edges, metadata):
    DEST.mkdir(parents=True, exist_ok=True)
    stem = DEST / f'{product}_{day}'
    np.savez_compressed(stem.with_suffix('.npz'), values=values, lon_edges=lon_edges, lat_edges=lat_edges)
    metadata.update(date=day, retrieved_utc=datetime.now(timezone.utc).isoformat(),
                    subset='Native cells in county bounding window plus padding; no resampling.',
                    file_sha256=hashlib.sha256(stem.with_suffix('.npz').read_bytes()).hexdigest())
    stem.with_suffix('.json').write_text(json.dumps(metadata, indent=2))
    print(product, day, values.shape, 'finite:', np.isfinite(values).sum(), flush=True)

def fetch_usgs(product, day):
    if (DEST / f'{product}_{day}.json').exists():
        return
    date = day.replace('-', '')
    url = ('https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/firedanger/download-tool/source_rasters/'
           f'{product}-forecast-1/{product}-forecast-1_data_{date}_{date}.zip')
    blob = urllib.request.urlopen(url, timeout=120).read()
    archive = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in archive.namelist() if n.endswith('.tiff'))
    xml = archive.read(name + '.xml')
    doc = ET.fromstring(xml)
    for field in ['begdate', 'enddate']:
        assert doc.findtext(f'./idinfo/timeperd/timeinfo/rngdates/{field}') == date
    with MemoryFile(archive.read(name)) as mem, mem.open() as src:
        bounds = transform_bounds('EPSG:4326', src.crs, *county.bounds, densify_pts=41)
        w = from_bounds(*bounds, src.transform)
        c0, r0 = int(np.floor(w.col_off))-2, int(np.floor(w.row_off))-2
        c1, r1 = int(np.ceil(w.col_off+w.width))+2, int(np.ceil(w.row_off+w.height))+2
        window = Window(c0, r0, c1-c0, r1-r0)
        values = src.read(1, window=window, masked=True).astype('float64').filled(np.nan)
        values = values * src.scales[0] + src.offsets[0]
        aff = src.window_transform(window)
        xx, yy = np.meshgrid(np.arange(values.shape[1]+1), np.arange(values.shape[0]+1))
        xx, yy = aff * (xx, yy)
        lon, lat = Transformer.from_crs(src.crs, 'EPSG:4326', always_xy=True).transform(xx, yy)
        metadata = dict(source='USGS Fire Danger Forecast', source_url=url,
            source_sha256=hashlib.sha256(blob).hexdigest(), product=product.upper(),
            units={'wfpi':'unitless index', 'wlfp':'per million pixel-days', 'wfsp':'percent'}[product],
            archive_product='Day 1 forecast', valid_date=day,
            issue_time=None, lead_hours=None,
            timing_note='Day 1 archive and ground-condition date verified. Exact issue timestamp and hourly lead are not supplied in this download metadata; no matched-issuance claim.',
            source_crs=src.crs.to_wkt(), source_resolution=list(src.res), source_nodata=src.nodata,
            source_dtype=src.dtypes[0], source_scale=src.scales[0], source_offset=src.offsets[0])
    save(product, day, values, lon, lat, metadata)
    (DEST / f'{product}_{day}.xml').write_bytes(xml)

def fetch_gridmet(product):
    if all((DEST / f'gridmet_{product}_{d}.json').exists() for d in DATES):
        return
    url = f'https://thredds.northwestknowledge.net/thredds/dodsC/MET/{product}/{product}_2026.nc'
    with xr.open_dataset(url) as ds:
        variable = next(k for k in ds.data_vars if ds[k].ndim == 3)
        west, south, east, north = county.bounds
        lat, lon = ds.lat.values, ds.lon.values
        ri = np.where((lat >= south-.09) & (lat <= north+.09))[0]
        ci = np.where((lon >= west-.09) & (lon <= east+.09))[0]
        part = ds[variable].isel(lat=slice(ri.min(),ri.max()+1), lon=slice(ci.min(),ci.max()+1)).sel(day=slice(DATES[0],DATES[-1])).load()
        assert part.sizes['day'] == 4
        def edges(a):
            return np.r_[a[0]-(a[1]-a[0])/2, (a[:-1]+a[1:])/2, a[-1]+(a[-1]-a[-2])/2]
        lon_e, lat_e = np.meshgrid(edges(part.lon.values), edges(part.lat.values))
        for day in DATES:
            values = part.sel(day=day).transpose('lat','lon').values
            metadata = dict(source='gridMET / Climatology Lab', source_url=url,
                product=product.upper(), variable=variable, units=str(part.attrs.get('units','')),
                valid_date=day, issue_time=None, lead_hours=None,
                timing_note='Retrospective daily product, not an issued forecast. Nominal day ends at 07:00 UTC the following calendar day.',
                fuel_model='G', source_resolution_degrees=1/24,
                source_attributes={k:str(v) for k,v in ds.attrs.items()},
                variable_attributes={k:str(v) for k,v in part.attrs.items()})
            save(f'gridmet_{product}', day, values, lon_e, lat_e, metadata)

if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda args: fetch_usgs(*args), [(p,d) for p in ['wfpi','wfsp','wlfp'] for d in DATES]))
    for product in ['erc','bi']:
        fetch_gridmet(product)
