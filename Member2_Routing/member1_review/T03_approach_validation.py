"""Measure network snapping and test actual routes; does not certify water access."""
import argparse
import importlib.metadata
import math
import warnings
from pathlib import Path

import searoute

from validation_common import coordinate_pair, distance_nm, read_ports, sha256, write_json


def validate_feature(route):
    if not isinstance(route, dict) or route.get('type') != 'Feature':
        raise ValueError('Expected a GeoJSON Feature')
    geometry = route.get('geometry') or {}
    points = geometry.get('coordinates')
    if geometry.get('type') != 'LineString' or not isinstance(points, (list, tuple)) or len(points) < 2:
        raise ValueError('Expected a nonempty LineString with at least two vertices')
    # searoute may unwrap longitudes past +/-180 for a continuous path across
    # the date line. Normalize for measurements, retaining the raw route below.
    measured_points = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ValueError('Invalid route vertex')
        lon, lat = point[:2]
        if isinstance(lon, bool) or not isinstance(lon, (int, float)) or not math.isfinite(lon):
            raise ValueError('Invalid longitude in route vertex')
        measured_points.append(coordinate_pair((lon + 180) % 360 - 180, lat))
    props = route.get('properties') or {}
    length = props.get('length')
    if isinstance(length, bool) or not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0:
        raise ValueError('Route must have a finite positive length')
    if props.get('units') != 'naut':
        raise ValueError('Route length units must be nautical miles (naut)')
    return measured_points, float(length)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--review-snap-nm', type=float, default=10,
                        help='Analyst review trigger only, not a supplied accuracy tolerance (default 10 nm)')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'results/t03.json')
    args = parser.parse_args()
    if not math.isfinite(args.review_snap_nm) or args.review_snap_nm < 0:
        parser.error('--review-snap-nm must be finite and nonnegative')
    ports = read_ports(args.workbook)
    anchors = {p['port_id']: p for p in ports if p.get('port_id') in ('SGSIN', 'NLRTM')}
    if set(anchors) != {'SGSIN', 'NLRTM'}:
        parser.error('Workbook must contain SGSIN and NLRTM as test anchors')
    results = []
    config = {'units': 'naut', 'append_orig_dest': False, 'include_ports': False,
              'restrictions': ['northwest'], 'return_passages': True,
              'algorithm': 'dijkstra', 'backend': 'networkx'}
    for port in ports:
        anchor = anchors['NLRTM' if port['port_id'] == 'SGSIN' else 'SGSIN']
        row = {'port_id': port['port_id'], 'port_name': port['port_name'],
               'test_destination_port_id': anchor['port_id'], 'route_returned': False,
               'approach_approved': False, 'warnings': []}
        try:
            origin = coordinate_pair(port['approach_longitude'], port['approach_latitude'])
            destination = coordinate_pair(anchor['approach_longitude'], anchor['approach_latitude'])
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                route = searoute.searoute(origin, destination, **config)
            row['warnings'] = [str(w.message) for w in caught]
            points, length = validate_feature(route)
            snap = distance_nm(origin, points[0])
            row.update({'route_returned': True, 'status': 'REVIEW_SNAP' if snap > args.review_snap_nm else 'ROUTE_CHECK_PASSED',
                        'approach_coordinates_lon_lat': origin, 'network_start_lon_lat': points[0],
                        'origin_snap_nm': round(snap, 3), 'destination_snap_nm': round(distance_nm(destination, points[-1]), 3),
                        'distance_nm': length, 'vertex_count': len(points),
                        'passages_reported_by_library': route['properties'].get('traversed_passages', []),
                        'raw_library_route': route,
                        'unwrapped_longitude_vertices': sum(abs(p[0]) > 180 for p in route['geometry']['coordinates'])})
        except Exception as exc:
            row.update({'status': 'FAILED', 'error': f'{type(exc).__name__}: {exc}'})
        results.append(row)
    result = {'task': 'T03', 'workbook': str(args.workbook.resolve()), 'workbook_sha256': sha256(args.workbook),
              'searoute_version': importlib.metadata.version('searoute'), 'configuration': config,
              'network_provenance': 'Unmodified network bundled with the installed searoute distribution',
              'review_snap_nm': args.review_snap_nm,
              'review_threshold_basis': 'Analyst-selected triage trigger; not a course tolerance or navigational standard',
              'ports_tested': len(results), 'valid_routes': sum(r['route_returned'] for r in results),
              'ports_flagged_for_snap_review': [r['port_id'] for r in results if r['status'] == 'REVIEW_SNAP'],
              'failed_ports': [r['port_id'] for r in results if r['status'] == 'FAILED'],
              'limitations': ['No land mask, chart, bathymetry, draft, or port-access validation was performed.',
                              'A valid network route and a short snap do not certify a navigable port approach.',
                              'Endpoint snaps are measured to the returned network vertices, with input endpoints not appended.',
                              'Network-only length excludes the input-to-network connector; original inputs are retained.',
                              'All approach_approved flags remain false pending geographic review by the team.',
                              'Raw library geometry can contain unwrapped longitudes at the date line; measurements normalize these, and map rendering needs separate date-line handling.'],
              'ports': results}
    write_json(args.output, result)
    print(f'T03: {result["valid_routes"]}/{len(results)} valid routes; snap review {result["ports_flagged_for_snap_review"]}; failures {result["failed_ports"]}')
    print(f'Results: {args.output.resolve()}')


if __name__ == '__main__':
    main()
