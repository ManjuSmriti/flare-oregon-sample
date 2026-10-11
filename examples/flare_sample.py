"""Read and explore the FLARE Oregon sample without modifying source data."""
from pathlib import Path
import os
import numpy as np
import xarray as xr


def data_root(path=None):
    root = Path(path or os.environ.get('FLARE_DATA_DIR', 'data')).expanduser().resolve()
    if not (root / 'Zarr').exists() and not (root / 'NETCDF').exists():
        raise FileNotFoundError(f'Extract the Zarr or NetCDF archive into {root}, or set FLARE_DATA_DIR.')
    return root


def scenes(root, fmt='zarr'):
    folder, suffix = ('Zarr', '.zarr') if fmt == 'zarr' else ('NETCDF', '.nc')
    return sorted(p.stem.removeprefix('flare_v7_14_') for p in (Path(root)/folder).glob('*'+suffix))


def open_scene(root, tag, fmt='zarr'):
    stem = 'flare_v7_14_' + tag
    # Preserve real categorical zero and real score zero; source uses NaN for
    # unavailable float values. Never mask zero by assuming it is nodata.
    if fmt == 'zarr':
        ds = xr.open_zarr(Path(root)/'Zarr'/(stem+'.zarr'), consolidated=True,
                          mask_and_scale=False, chunks=None)
    elif fmt == 'netcdf':
        ds = xr.open_dataset(Path(root)/'NETCDF'/(stem+'.nc'), engine='netcdf4',
                             mask_and_scale=False)
    else:
        raise ValueError('fmt must be zarr or netcdf')
    return ds.set_coords(['lat', 'lon'])


def false_rgb(ds):
    """Packaged viewer style: I03/I02/I01, fixed 0–0.6 stretch, gamma 2.2.

    This is a display transform of reconstructed radiances, not reflectance.
    It differs from the older percentile-stretched cover image.
    """
    values = np.stack([ds[k].values for k in ('I03','I02','I01')], axis=-1)
    valid = np.isfinite(values).all(axis=-1) & (values >= 0).all(axis=-1)
    rgba = np.zeros(values.shape[:-1]+(4,), dtype=np.uint8)
    rgba[...,:3] = (np.nan_to_num(np.clip(values/.6, 0, 1))**(1/2.2)*255).astype('u1')
    rgba[...,3] = valid.astype('u1')*255
    return rgba


def nearest_pixel(ds, latitude, longitude):
    from pyproj import Geod
    lat, lon = ds.lat.values, ds.lon.values
    _, _, distance = Geod(ellps='WGS84').inv(
        np.full(lon.shape, longitude), np.full(lat.shape, latitude), lon, lat)
    return np.unravel_index(np.nanargmin(distance), lat.shape)


def web_raster(ds, rgba, width=1100):
    """Nearest native center onto a north-up EPSG:3857 raster.

    A curvilinear array cannot be correctly mapped by attaching its min/max
    coordinates to an image. Reproject pixel centers and mask the footprint.
    """
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    from matplotlib.path import Path as Polygon
    forward = Transformer.from_crs(4326,3857,always_xy=True)
    inverse = Transformer.from_crs(3857,4326,always_xy=True)
    x,y = forward.transform(ds.lon.values, ds.lat.values)
    west,east,south,north = x.min(),x.max(),y.min(),y.max()
    height=max(2,round(width*(north-south)/(east-west)))
    xx,yy=np.meshgrid(west+(np.arange(width)+.5)*(east-west)/width,
                      north-(np.arange(height)+.5)*(north-south)/height)
    edge=np.concatenate([np.column_stack((x[0],y[0])),np.column_stack((x[1:,-1],y[1:,-1])),
        np.column_stack((x[-1,-2::-1],y[-1,-2::-1])),np.column_stack((x[-2:0:-1,0],y[-2:0:-1,0]))])
    inside=Polygon(edge).contains_points(np.column_stack((xx.ravel(),yy.ravel()))).reshape(xx.shape)
    _,idx=cKDTree(np.column_stack((x.ravel(),y.ravel()))).query(np.column_stack((xx.ravel(),yy.ravel())))
    result=rgba.reshape(-1,4)[idx].reshape(height,width,4).copy()
    result[~inside,3]=0
    lo0,la0=inverse.transform(west,south);lo1,la1=inverse.transform(east,north)
    return result,[[la0,lo0],[la1,lo1]]


def interactive_map(ds, threshold=60):
    import folium
    from matplotlib import colormaps
    rgb,bounds=web_raster(ds,false_rgb(ds))
    m=folium.Map(tiles='OpenStreetMap', control_scale=True)
    folium.raster_layers.ImageOverlay(rgb,bounds,name='False RGB',opacity=1).add_to(m)
    score=ds.FireScore.values
    colors=(colormaps['inferno'](np.nan_to_num(score)/100)*255).astype('u1')
    colors[...,3]=np.where(np.isfinite(score)&(score>threshold),220,0).astype('u1')
    overlay,_=web_raster(ds,colors)
    folium.raster_layers.ImageOverlay(overlay,bounds,name=f'FireScore > {threshold}',opacity=.8).add_to(m)
    folium.LatLngPopup().add_to(m)
    folium.LayerControl().add_to(m)
    m.fit_bounds(bounds)
    return m


if __name__ == '__main__':
    import argparse
    import matplotlib.pyplot as plt
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data');p.add_argument('--format',choices=['zarr','netcdf'],default='netcdf')
    p.add_argument('--tag');p.add_argument('--output',default='outputs')
    a=p.parse_args();root=data_root(a.data);tag=a.tag or scenes(root,a.format)[0]
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    with open_scene(root,tag,a.format) as ds:
        plt.imsave(out/f'{tag}_false_rgb.png',false_rgb(ds))
        interactive_map(ds).save(str(out/f'{tag}_map.html'))
    print(f'Created PNG and interactive HTML map in {out.resolve()}')
