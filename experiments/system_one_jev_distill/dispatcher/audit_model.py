"""Analytical capability check, separate from physical routing acceptance."""
import argparse
import json
import math
from pathlib import Path

from contract import FEATURES, NAMES, project


def audit_wake(model):
    if model.get('skills') != NAMES:
        raise ValueError('Expected dispatcher head names')
    rows = model['rows']
    if len(rows) != 8 or any(len(row) != 9 for row in rows):
        raise ValueError('Expected 8x9 rows')
    if not all(math.isfinite(v) for row in rows for v in row):
        raise ValueError('Nonfinite model weights')
    row = rows[NAMES.index('wake_candidate')]
    # A linear function on a box reaches its maximum at a corner. Fix readiness
    # to confirmed sleep (0), then maximize every other legal feature separately.
    state = {name: 0 if name == 'readiness' else int(row[i] >= 0)
             for i, name in enumerate(FEATURES)}
    maximum = sum(a*b for a, b in zip(row, project(state)))
    return {'status': 'FAIL' if maximum < 0 else 'POSSIBLE_NOT_VALIDATED',
            'check': 'wake_head_can_reach_nonnegative_for_confirmed_sleep',
            'maximum_sleeping_wake_logit': maximum,
            'maximizing_state': state,
            'meaning': 'A negative upper bound proves every legal sleeping state is denied wake. '
                       'A nonnegative bound does not establish correct routing or physical wake.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', type=Path)
    args = parser.parse_args()
    result = audit_wake(json.loads(args.model.read_text()))
    print(json.dumps(result, indent=2))
    raise SystemExit(2 if result['status'] == 'FAIL' else 0)
