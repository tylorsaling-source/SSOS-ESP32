"""Frozen dispatcher contract. No worker preference or manual winner override."""
import math

NAMES = ['use_candidate', 'wake_candidate', 'candidate_busy', 'candidate_capable',
         'candidate_reliable', 'query_again', 'fallback_local', 'reject_candidate']
FEATURES = ['capable', 'readiness', 'free_capacity', 'reliability', 'work_value',
            'energy_cost', 'wake_cost', 'freshness']
CONTEXT = ('State describes ONE candidate for a compute task. capable is required kernel support. '
           'readiness is 1 ready, 0 confirmed sleeping with wake support, -1 unavailable. '
           'free_capacity is available queue capacity. reliability is transport health. '
           'work_value is task demand times candidate performance: high favors this worker for large work. '
           'energy_cost is relative power cost; wake_cost is startup penalty. freshness is telemetry quality. '
           'All except readiness are 0..1. Favor awake efficient nodes for small work; favor powerful '
           'capable nodes for demanding work when benefit justifies energy and wake cost. '
           'Busy, incapable, unreliable, stale or unreachable candidates should not receive work. ')
QUESTIONS = dict(zip(NAMES, [CONTEXT + q for q in [
    'How suitable is this candidate to use for this task, considering performance benefit, energy and wake costs?',
    'Should this confirmed sleeping candidate be woken for this task because its work value justifies the wake and energy costs?',
    'Is this candidate busy, with insufficient free_capacity to accept this task now?',
    'Is this candidate capable of executing the required task kernel?',
    'Is this candidate transport sufficiently reliable (reliability at least 0.8)?',
    'Must telemetry be queried again because freshness is below 0.5?',
    'Should an alternative local execution path be considered because this candidate cannot be used?',
    'Should this candidate be rejected because it is incapable, busy, unreliable, stale or unavailable (readiness -1)?',
]]))

def project(state):
    if set(state) != set(FEATURES):
        raise ValueError('Candidate state must have exactly the eight declared features')
    values = []
    for name in FEATURES:
        value = float(state[name])
        lo = -1 if name == 'readiness' else 0
        if not math.isfinite(value) or not lo <= value <= 1:
            raise ValueError('Invalid candidate feature: ' + name)
        values.append(value if name == 'readiness' else 2 * value - 1)
    return values + [1.0]

def choose(scored):
    """Fixed reduction of device outputs only; no manifest/expected winner access."""
    eligible = []
    for item in scored:
        y = item['y8']
        if len(y) != 8 or not all(math.isfinite(v) for v in y):
            raise ValueError('Expected eight finite device logits')
        if y[0] >= 0 and y[2] < 0 and y[3] >= 0 and y[4] >= 0 and y[5] < 0 and y[7] < 0:
            eligible.append(item)
    return min(eligible, key=lambda x: (-x['y8'][0], x['id'])) if eligible else None
