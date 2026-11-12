"""Audit supplied port data without changing project IDs or source workbooks."""
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from validation_common import coordinate_pair, distance_nm, duplicates, read_ports, sha256, write_json


def parse_locode_coordinates(value):
    match = re.fullmatch(r'(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])', value.strip())
    if not match:
        return None
    a, b, ns, c, d, ew = match.groups()
    if int(b) >= 60 or int(d) >= 60:
        return None
    return coordinate_pair((int(c)+int(d)/60) * (-1 if ew == 'W' else 1),
                           (int(a)+int(b)/60) * (-1 if ns == 'S' else 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--unlocode-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'results/t02.json')
    args = parser.parse_args()
    files = [args.unlocode_dir/f'UNLOCODE CodeListPart{i}.csv' for i in (1, 2, 3)]
    reference = defaultdict(list)
    for path in files:
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8-sig')
            encoding = 'utf-8-sig'
        except UnicodeDecodeError:
            text = raw.decode('latin1')
            encoding = 'latin1'
        for row in csv.reader(text.splitlines()):
            if len(row) >= 12 and row[1].strip() and row[2].strip():
                reference[(row[1]+row[2]).replace(' ', '').upper()].append({
                    'name': row[3], 'name_without_diacritics': row[4], 'subdivision': row[5],
                    'function': row[6], 'status': row[7], 'record_date_code': row[8],
                    'coordinates': row[10], 'change_indicator': row[0],
                    'file': path.name, 'encoding': encoding})
    ports = read_ports(args.workbook)
    checks = {
        'expected_port_count': 29, 'actual_port_count': len(ports),
        'port_count_matches': len(ports) == 29,
        'duplicate_project_port_ids': duplicates(p.get('port_id') for p in ports),
        'duplicate_supplied_un_locodes': duplicates(p.get('un_locode') for p in ports),
    }
    results = []
    for port in ports:
        code = str(port.get('un_locode') or '').replace(' ', '').upper()
        matches = reference.get(code, [])
        row = {'port_id': port.get('port_id'), 'port_name': port.get('port_name'),
               'supplied_un_locode': port.get('un_locode'), 'lookup_code': code,
               'identifier_match': bool(matches), 'reference_matches': matches, 'issues': []}
        if not re.fullmatch(r'[A-Z]{2}[A-Z2-9]{3}', code):
            row['issues'].append('Invalid UN/LOCODE format')
        if not matches:
            row['issues'].append('UN/LOCODE absent from supplied reference files')
        if len(matches) > 1:
            row['issues'].append('Multiple reference records; resolve before selecting one')
        if code[:2] != str(port.get('country_code') or '').upper():
            row['issues'].append('UN/LOCODE country prefix differs from country_code')
        if matches and not any(m['function'].startswith('1') for m in matches):
            row['issues'].append('Reference function does not identify a maritime port')
        for prefix in ('', 'approach_'):
            try:
                row[prefix+'coordinates_lon_lat'] = coordinate_pair(port.get(prefix+'longitude'), port.get(prefix+'latitude'))
            except (TypeError, ValueError) as exc:
                row['issues'].append(f'{prefix or "port_"}coordinates: {exc}')
        if len(matches) == 1 and 'coordinates_lon_lat' in row:
            point = parse_locode_coordinates(matches[0]['coordinates'])
            row['reference_coordinates_lon_lat'] = point
            row['distance_to_reference_point_nm'] = round(distance_nm(row['coordinates_lon_lat'], point), 3) if point else None
        # Explicit identity exceptions found in the supplied references. These are
        # review notes, not automatic changes to stable project keys or coordinates.
        if code == 'GIIBZ' and reference.get('GIGIB'):
            row['proposed_official_un_locode'] = 'GIGIB'
            row['proposal_evidence'] = reference['GIGIB']
            row['issues'].append('Gibraltar candidate GIGIB exists; retain project port_id GIIBZ')
        if code == 'CNSHA':
            row['identity_review_candidates'] = {c: reference[c] for c in ('CNSGH', 'CNSHG') if reference.get(c)}
            row['issues'].append('CNSHA identifies Hongqiao airport in these references; review Shanghai city/port identity separately')
        if code == 'PAMIT':
            row['issues'].append('PAMIT identifies Manzanillo; reconcile supplied Colon/Cristobal label and terminal scope')
        row['status'] = 'REVIEW_REQUIRED' if row['issues'] else 'CHECKS_PASSED'
        results.append(row)
    output = {
        'task': 'T02', 'workbook': str(args.workbook.resolve()), 'workbook_sha256': sha256(args.workbook),
        'reference_files': [{'path': str(p.resolve()), 'sha256': sha256(p)} for p in files],
        'reference_release': 'Not established from supplied filenames; record original download release separately',
        'checks': checks, 'matched_identifiers': sum(r['identifier_match'] for r in results),
        'ports_requiring_review': [r['port_id'] for r in results if r['issues']],
        'limitations': [
            'Matching a code does not establish the intended port, terminal, or coordinate accuracy.',
            'UN/LOCODE coordinates are location reference points, not verified approach points.',
            'Coordinate differences are descriptive, not official pass/fail tolerances.',
            'No source values, project IDs, or benchmark targets were changed.'],
        'ports': results}
    write_json(args.output, output)
    print(f'T02: {output["matched_identifiers"]}/{len(ports)} identifiers matched; review {output["ports_requiring_review"]}')
    print(f'Results: {args.output.resolve()}')


if __name__ == '__main__':
    main()
