"""A baseline diagnostic plus a separately sourced independent Pub. 151 check.

This calls the library directly, not the group's API. It is not API acceptance.
"""
import argparse
import importlib.metadata
from pathlib import Path

import openpyxl
import searoute

from T03_approach_validation import validate_feature
from validation_common import coordinate_pair, read_ports, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'results/t13_bm002.json')
    args = parser.parse_args()
    ports = {p['port_id']: p for p in read_ports(args.workbook)}
    book = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    try:
        rows = iter(book['Benchmark Routes'].values)
        header = next(rows)
        target = next(dict(zip(header, r)) for r in rows if r[0] == 'BM_002')
    finally:
        book.close()
    coordinates = [coordinate_pair(ports[target[k]]['longitude'], ports[target[k]]['latitude'])
                   for k in ('origin_id', 'destination_id')]
    config = dict(units='naut', append_orig_dest=False, include_ports=False,
                  restrictions=['northwest'], return_passages=True, algorithm='dijkstra', backend='networkx')
    route = searoute.searoute(*coordinates, **config)
    _, calculated = validate_feature(route)
    expected, tolerance = float(target['expected_distance_nm']), float(target['acceptable_tolerance_nm'])
    independent = 307.0
    result = {
        'task': 'T13 initial independent spot-check', 'benchmark_id': 'BM_002',
        'workbook': str(args.workbook.resolve()), 'workbook_sha256': sha256(args.workbook),
        'searoute_version': importlib.metadata.version('searoute'), 'configuration': config,
        'input_coordinates_lon_lat': coordinates, 'calculated_distance_nm': calculated,
        'supplied_expected_distance_nm': expected, 'supplied_tolerance_nm': tolerance,
        'absolute_error_against_supplied_nm': abs(calculated-expected),
        'within_supplied_tolerance': abs(calculated-expected) <= tolerance,
        'independent_reference': {'publisher': 'National Geospatial-Intelligence Agency',
            'title': 'Publication 151, Distances Between Ports', 'edition': '11th edition, 2001',
            'section': 'ROTTERDAM, NETHERLANDS, Ports, Hamburg, Germany', 'printed_page': 94,
            'distance_nm': independent, 'access_date': '2026-11-11',
            'url': 'https://msi.nga.mil/api/publications/download?key=16694076%2FSFH00000%2FPub151bk.pdf&type=view'},
        'calculated_minus_independent_nm': calculated-independent,
        'absolute_difference_percent_of_independent': 100*abs(calculated-independent)/independent,
        'limitations': ['Direct library diagnostic; the group API and its error handling were not tested.',
            'The supplied model-derived target remains the acceptance target; Pub. 151 is a separate spot-check.',
            'Pub. 151 uses different reference points and routing conventions. The cause of the difference is not established.',
            'Passing BM_002 does not validate the other nine benchmarks or the full service.'],
        'raw_library_route': route}
    write_json(args.output, result)
    print(f'BM_002 library diagnostic: {calculated:.3f} nm; supplied {expected:g} +/- {tolerance:g}; Pub. 151 {independent:g} nm')


if __name__ == '__main__':
    main()
