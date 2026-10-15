"""Offline native-grid Wheeler County comparisons used by notebook 03."""
from pathlib import Path
from io import BytesIO
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
import cartopy.crs as ccrs
import shapely
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer
from IPython.display import display, Image

PRODUCTS = {
    'wfpi': ('USGS WFPI', 'Index'),
    'wfsp': ('USGS WFSP', '%'),
    'wlfp': ('USGS WLFP', 'Per million pixel-days'),
}
DATES = [f'2026-07-{d}' for d in range(13,17)]

def load(root):
    root = Path(root)
    county = shape(json.loads((root/'assets/boundaries/wheeler_county_41069.geojson').read_text())['features'][0]['geometry'])
    project = Transformer.from_crs('EPSG:4326','EPSG:5070',always_xy=True)
    county_m = transform(project.transform, county)
    data, rows = {}, []
    for product in PRODUCTS:
        data[product] = []
        for day in DATES:
            stem = root/'assets/fire_comparisons/numerical'/f'{product}_{day}'
            with np.load(stem.with_suffix('.npz')) as a:
                values, lon, lat = (a[k].copy() for k in ['values','lon_edges','lat_edges'])
            meta = json.loads(stem.with_suffix('.json').read_text())
            xx, yy = project.transform(lon,lat)
            vertices = np.stack([np.stack([xx[:-1,:-1],yy[:-1,:-1]],-1),
                np.stack([xx[:-1,1:],yy[:-1,1:]],-1),np.stack([xx[1:,1:],yy[1:,1:]],-1),
                np.stack([xx[1:,:-1],yy[1:,:-1]],-1)],axis=-2)
            polygons = shapely.polygons(vertices.reshape(-1,4,2))
            overlap = shapely.intersects(polygons,county_m)
            weights = np.zeros(len(polygons))
            weights[overlap] = shapely.area(shapely.intersection(polygons[overlap],county_m))
            weights = weights.reshape(values.shape)
            assert np.isclose(weights.sum(),county_m.area,rtol=1e-5), 'Subset does not cover entire county.'
            # USGS map legends define land/status codes beyond numeric values.
            # 249/250/251/252/253/254: outside US/snow/ag land/barren/marsh/water.
            # WLFP uses the same codes multiplied by ten. Preserve raw cached values.
            codes = np.arange(249,255) * (10 if product == 'wlfp' else 1)
            special = np.isin(values,codes) if not product.startswith('gridmet') else np.zeros(values.shape,dtype=bool)
            valid = (weights > 1e-3) & np.isfinite(values) & ~special
            assert valid.any(), f'No valid data: {product} {day}'
            samples, area = values[valid], weights[valid]
            mean = np.average(samples,weights=area)
            rows.append(dict(product=product,date=day,area_weighted_mean=mean,
                pixel_median=np.median(samples),pixel_min=samples.min(),pixel_max=samples.max(),
                native_pixels=len(samples),valid_county_area_pct=100*area.sum()/county_m.area,
                special_code_area_pct=100*weights[special].sum()/county_m.area,
                units=meta['units'],valid_date=meta['valid_date'],issue_time=meta['issue_time'],
                lead_hours=meta['lead_hours'],timing_note=meta['timing_note']))
            data[product].append(dict(values=values,lon=lon,lat=lat,weights=weights,valid=valid,
                samples=samples,metadata=meta))
    return county,data,pd.DataFrame(rows)

def show(fig):
    """Fixed canvas avoids Cartopy clip-path/tight-bbox cropping."""
    buffer = BytesIO()
    with plt.rc_context({'savefig.bbox':None}):
        fig.savefig(buffer,format='png',dpi=120,bbox_inches=None)
    plt.close(fig)
    display(Image(data=buffer.getvalue()))

def county_path(county):
    polygons = [county] if county.geom_type == 'Polygon' else county.geoms
    paths = []
    for polygon in polygons:
        for ring in [polygon.exterior,*polygon.interiors]:
            vertices = np.asarray(ring.coords)
            codes = np.full(len(vertices),MplPath.LINETO,dtype='uint8')
            codes[0],codes[-1] = MplPath.MOVETO,MplPath.CLOSEPOLY
            paths.append(MplPath(vertices,codes))
    return MplPath.make_compound_path(*paths)

def maps(product,county,data):
    name,unit = PRODUCTS[product]
    group = data[product]
    low = min(x['samples'].min() for x in group)
    high = max(x['samples'].max() for x in group)
    if product == 'wfpi':
        low, high = 0, 150
    if high == low: high = low + 1
    geo = ccrs.PlateCarree()
    fig,axes = plt.subplots(2,2,figsize=(11,10),subplot_kw={'projection':geo})
    fig.subplots_adjust(left=.10,right=.96,bottom=.15,top=.88,wspace=.18,hspace=.25)
    west,south,east,north = county.bounds
    cmap = plt.get_cmap('RdYlGn_r').copy()
    cmap.set_bad('#dddddd')
    for ax,day,item in zip(axes.flat,DATES,group):
        ax.set_extent([west-.035,east+.035,south-.035,north+.035],geo)
        ax.add_geometries([county],geo,facecolor='#dddddd',edgecolor='none',zorder=0)
        a = np.ma.masked_where(~item['valid'],item['values'])
        mesh = ax.pcolormesh(item['lon'],item['lat'],a,transform=geo,
            cmap=cmap,vmin=low,vmax=high,shading='flat',rasterized=True,zorder=1)
        mesh.set_clip_path(PathPatch(county_path(county),transform=ax.transData))
        ax.add_geometries([county],geo,facecolor='none',edgecolor='#333333',linewidth=.8)
        grid = ax.gridlines(draw_labels=True,linewidth=.4,alpha=.35)
        grid.top_labels = grid.right_labels = False
        grid.xlabel_style = grid.ylabel_style = {'size':8}
        ax.text(.5,1.06,day,transform=ax.transAxes,ha='center',fontsize=11)
    fig.colorbar(mesh,cax=fig.add_axes([.20,.085,.65,.025]),orientation='horizontal',label=unit)
    status = 'Retrospective daily field | fuel model G' if product.startswith('gridmet') else 'Day 1 archive | valid dates shown; exact issue time not supplied'
    fig.suptitle(f'Wheeler County | {name}',fontsize=16,y=.98)
    fig.text(.5,.935,status,ha='center',fontsize=10)
    fig.text(.5,.015,'Gray: special land/status codes or missing data; excluded from numerical summaries.',ha='center',fontsize=8)
    show(fig)

def distributions(products,data,summary):
    fig,axes = plt.subplots(len(products),2,figsize=(13,3.3*len(products)),squeeze=False)
    fig.subplots_adjust(left=.10,right=.97,bottom=.10,top=.87,hspace=.65,wspace=.30)
    labels = ['Jul 13','Jul 14','Jul 15','Jul 16']
    for pair,product in zip(axes,products):
        name,unit = PRODUCTS[product]
        bp = pair[0].boxplot([x['samples'] for x in data[product]],patch_artist=True,whis=1.5,showfliers=True)
        for patch in bp['boxes']: patch.set_facecolor('#d5e3c4')
        pair[0].set_xticks(range(1,5),labels)
        pair[0].set_title(f'{name} | native-pixel distribution',fontsize=10)
        s = summary.loc[summary['product']==product]
        pair[1].plot(range(4),s.area_weighted_mean,'o-',color='#b33b29',linewidth=2)
        pair[1].set_xticks(range(4),labels)
        pair[1].set_title(f'{name} | area-weighted county mean',fontsize=10)
        for ax in pair:
            ax.set_ylabel(unit)
            ax.grid(axis='y',alpha=.25)
    fig.suptitle('Wheeler County | Daily distributions and time series',fontsize=15,y=.98)
    fig.text(.5,.025,'Boxplots: all valid intersecting cells, unweighted; whiskers: 1.5×IQR. Means: county-overlap area weights; missing cells excluded.',ha='center',fontsize=8)
    show(fig)

def matrix(county, data, flare, wider=False):
    """Rows are dates; columns retain actual units and fixed per-product limits."""
    perimeter_path = Path(__file__).resolve().parents[1] / 'assets/fire_comparisons/crosswhite_early_perimeter.geojson'
    perimeter_feature = json.loads(perimeter_path.read_text())['features'][0]
    perimeter = shape(perimeter_feature['geometry'])
    discovery_day = pd.Timestamp(perimeter_feature['properties']['attr_FireDiscoveryDateTime'], unit='ms', tz='UTC').date()
    products = ['flare', 'flare_custom', 'wfpi', 'wfsp', 'wlfp']
    categories = [dict(item, values=item['categories'],
        valid=(item['county_mask'] & (item['categories'] >= 1) & (item['categories'] <= 6))) for item in flare]
    custom = []
    for item in flare:
        values = item['categories']
        valid = item['county_mask'] & (values >= 1) & (values <= 6)
        custom.append(dict(item, values=values, valid=valid))
    groups = dict(data, flare=flare, flare_category=categories, flare_custom=custom)
    names = dict(PRODUCTS, flare=('FLARE FireOutlook', 'Index'), flare_category=('FLARE FireOutlook category', 'Stored category'),
        flare_custom=('FLARE FireOutlook category', 'Category'))
    geo = ccrs.PlateCarree()
    fig, axes = plt.subplots(4, 5, figsize=(19, 14), subplot_kw={'projection': geo})
    fig.subplots_adjust(left=.065, right=.985, bottom=.14, top=.88, wspace=.08, hspace=.10)
    west, south, east, north = county.bounds
    padding = .15 if wider else .035
    if wider:
        origin = json.loads((perimeter_path.parent / 'crosswhite_origin.json').read_text())
        west, south, east, north = perimeter.bounds
        padding = 0
    cmap = plt.get_cmap('RdYlGn_r').copy()
    cmap.set_bad('#dddddd')
    for col, product in enumerate(products):
        group = groups[product]
        first = group[0]
        area_transform = Transformer.from_crs('EPSG:4326', 'EPSG:5070', always_xy=True)
        px, py = area_transform.transform(first['lon'], first['lat'])
        vx = np.stack([px[:-1,:-1], px[:-1,1:], px[1:,1:], px[1:,:-1]], axis=-1)
        vy = np.stack([py[:-1,:-1], py[:-1,1:], py[1:,1:], py[1:,:-1]], axis=-1)
        pixel_area = .5 * np.abs(np.sum(vx*np.roll(vy,-1,axis=-1)-vy*np.roll(vx,-1,axis=-1),axis=-1))
        median_area = np.median(pixel_area[first['valid']]) / 1e6
        low = 0 if product == 'flare' else min(x['samples'].min() for x in group)
        high = 1 if product == 'flare' else max(x['samples'].max() for x in group)
        if product == 'wfpi':
            low, high = 0, 150
        if high == low: high = low + 1
        from matplotlib.colors import BoundaryNorm, Normalize
        categorical = product in ('flare_category', 'flare_custom')
        column_cmap = plt.get_cmap('RdYlGn_r', 6).copy() if categorical else cmap
        column_cmap.set_bad('#dddddd')
        norm = BoundaryNorm(np.arange(.5,7,1),6) if categorical else Normalize(low,high)
        for row, item in enumerate(group):
            ax = axes[row,col]
            ax.set_extent([west-padding, east+padding, south-padding, north+padding], geo)
            ax.add_geometries([county], geo, facecolor='#dddddd', edgecolor='none', zorder=0)
            mesh = ax.pcolormesh(item['lon'], item['lat'],
                np.ma.masked_where(~item['valid'], item['values']), transform=geo,
                cmap=column_cmap, norm=norm, shading='flat', rasterized=True, zorder=1)
            if not wider:
                mesh.set_clip_path(PathPatch(county_path(county), transform=ax.transData))
            ax.add_geometries([county], geo, facecolor='none', edgecolor='#333333', linewidth=.6)
            # Fixed early footprint for retrospective comparison, not daily growth.
            before_discovery = pd.Timestamp(DATES[row]).date() < discovery_day
            ax.add_geometries([perimeter], geo, facecolor='none', edgecolor='black',
                linewidth=1.5, linestyle='--' if before_discovery else '-', zorder=5)
            if wider:
                import matplotlib.patheffects as pe
                ax.plot(origin['longitude'], origin['latitude'], marker='+', markersize=13,
                    markeredgewidth=1.5, color='black', linestyle='none', transform=geo, zorder=7,
                    path_effects=[pe.Stroke(linewidth=3, foreground='white'), pe.Normal()])
            grid_ticks = (dict(xlocs=np.linspace(west,east,4)[1:-1],
                ylocs=np.linspace(south,north,4)[1:-1]) if wider else
                dict(xlocs=[-120.4,-120.1,-119.8], ylocs=[44.4,44.7,45.0]))
            grid = ax.gridlines(draw_labels=True, linewidth=.3, alpha=.25, **grid_ticks)
            grid.top_labels = grid.right_labels = False
            grid.left_labels = col == 0
            grid.bottom_labels = row == 3
            grid.xlabel_style = grid.ylabel_style = {'size':7}
            if row == 0:
                kind = 'Forecast' if product.startswith('flare') else 'Day 1 forecast'
                heading_bounds = ax.get_position()
                fig.text((heading_bounds.x0+heading_bounds.x1)/2,.895,
                    f'{names[product][0]}\n{kind}\nMedian pixel area: {median_area:.3f} km²', ha='center', va='bottom', fontsize=9)
        bounds = axes[-1,col].get_position()
        cb = fig.colorbar(mesh, cax=fig.add_axes([bounds.x0+.008,.087,bounds.width-.016,.016]),
            orientation='horizontal', extend='neither')
        from matplotlib.ticker import MaxNLocator
        if categorical:
            cb.set_ticks(np.arange(1,7))
            labels = ['Minimal','Low','Moderate','High','Very high','Extreme']
            cb.set_ticklabels(labels,rotation=40,ha='right')
        elif product == 'flare':
            cb.set_ticks([0,.2,.4,.6,.8,1.0])
        else:
            cb.locator = MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.ax.tick_params(labelsize=8)
        cb.set_label(names[product][1], fontsize=9)
    for row, day in enumerate(DATES):
        bounds = axes[row,0].get_position()
        fig.text(.015,(bounds.y0+bounds.y1)/2,pd.Timestamp(day).strftime('%b %d'),
            rotation=90,ha='center',va='center',fontsize=14)
    fig.suptitle(('Crosswhite — early fire perimeter bounds' if wider else 'Wheeler County') + ' | July 13–16, 2026', fontsize=21, y=.975)
    fig.text(.5,.950,'Actual values · same green-to-red palette · one fixed original-unit scale per column',ha='center',fontsize=12)
    fig.text(.5,.932,'Crosswhite July 16 footprint: dashed before discovery; solid on/after July 16 (UTC)',ha='center',fontsize=10)
    footer = ('Crosshair = NIFC reported origin. White outside county = not displayed. ' if wider else '')
    footer += 'Gray = unavailable/special codes. Native grids retained; issuance and valid windows differ.'
    fig.text(.5,.018,footer,ha='center',fontsize=10)
    show(fig)
