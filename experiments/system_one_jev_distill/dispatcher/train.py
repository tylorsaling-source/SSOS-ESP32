"""New paid Jev dataset, independent of experiment one's preserved evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_jev_teacher as collector
import distill_system_one as distill
from contract import FEATURES, NAMES, QUESTIONS, project

def generate(count=512, seed=2102):
    rng = np.random.default_rng(seed)
    for _ in range(count):
        # Mix corners and continuous states, independent of named test workers.
        values = rng.choice([0., .1, .3, .6, .9, 1.], size=8)
        state = dict(zip(FEATURES, map(float, values)))
        state['capable'] = float(rng.choice([0, 1], p=[.15, .85]))
        state['readiness'] = float(rng.choice([-1, 0, 1], p=[.1, .3, .6]))
        state['free_capacity'] = float(rng.choice([0, 1], p=[.2, .8]))
        state['reliability'] = float(rng.choice([0, .5, 1], p=[.1, .1, .8]))
        state['freshness'] = float(rng.choice([0, .3, 1], p=[.05, .1, .85]))
        if state['readiness'] == 1:
            state['wake_cost'] = 0.
        yield {'state': state, 'x8': project(state)[:8]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    p.add_argument('--collect', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    states = args.output / 'states.jsonl'
    teacher = args.output / 'teacher.jsonl'
    if args.collect:
        with states.open('x') as stream:
            for row in generate():
                stream.write(json.dumps(row) + '\n')
        collector.QUESTIONS = QUESTIONS
        sys.argv = ['collector', str(states), str(teacher)]
        collector.main()
    x, y = distill.load_jsonl(teacher)
    distill.QUESTION_NAMES = NAMES
    q10, report = distill.fit_head(x, y, 2102)
    if np.any(np.abs(q10) > 8192):
        raise ValueError('Trained weights exceed existing V2 Q10 range; do not clip silently')
    order = np.random.default_rng(2102).permutation(len(x))
    tr, te = order[:int(.8*len(x))], order[int(.8*len(x)):]
    for i, metric in enumerate(report['per_head']):
        majority = np.mean(y[tr, i] >= .5) >= .5
        metric['majority_baseline_agreement'] = float(np.mean((y[te, i] >= .5) == majority))
    report.update(seed=2102, status='DESCRIPTIVE_ONLY_NOT_PHYSICAL_ACCEPTANCE',
                  teacher_sha256=hashlib.sha256(teacher.read_bytes()).hexdigest(),
                  teacher_models=sorted({json.loads(s)['teacher_model'] for s in teacher.read_text().splitlines()}))
    (args.output / 'rows.json').write_text(json.dumps(distill.model_document(q10), indent=2)+'\n')
    (args.output / 'training-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Dispatcher model frozen; physical acceptance remains pending.')

if __name__ == '__main__':
    main()
