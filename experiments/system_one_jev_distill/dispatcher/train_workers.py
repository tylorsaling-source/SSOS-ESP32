"""Separately frozen Jev worker-process experiment; prior models are immutable."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_jev_teacher as collector
import distill_system_one as distill
from worker_contract import FEATURES, NAMES, QUESTIONS, project
from audit_model import audit_wake

SEED = 2103


def generate(count=512):
    rng = np.random.default_rng(SEED)
    for i in range(count):
        state = dict(zip(FEATURES, map(float, rng.choice([0., .1, .3, .6, .9, 1.], size=8))))
        state.update(capable=float(rng.choice([0, 1], p=[.15,.85])),
                     readiness=float(rng.choice([-1, 0, 1], p=[.1,.45,.45])),
                     free_capacity=float(rng.choice([0,1], p=[.15,.85])),
                     reliability=float(rng.choice([0,.5,1],p=[.1,.1,.8])),
                     freshness=float(rng.choice([0,.3,1],p=[.05,.1,.85])))
        # Predeclared coverage of healthy inactive workers across benefit/cost.
        # This does not assign labels: every target still comes from live Jev.
        if i % 2 == 0:
            state.update(capable=1., readiness=0., free_capacity=1., reliability=1., freshness=1.)
        if state['readiness'] == 1:
            state['wake_cost'] = 0.
        yield {'state': state, 'x8': project(state)[:8]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    states, teacher = args.output/'states.jsonl', args.output/'teacher.jsonl'
    if args.collect:
        with states.open('x') as stream:
            for row in generate():
                stream.write(json.dumps(row)+'\n')
        collector.QUESTIONS = QUESTIONS
        sys.argv = ['collector', str(states), str(teacher)]
        collector.main()
    x, y = distill.load_jsonl(teacher)
    distill.QUESTION_NAMES = NAMES
    q10, report = distill.fit_head(x, y, SEED)
    order = np.random.default_rng(SEED).permutation(len(x))
    tr, te = order[:int(.8*len(x))], order[int(.8*len(x)):]
    # Wake is consumed only for readiness 0. Fit that head on the matching
    # training subset; never use held-out rows or manually chosen target labels.
    mask = x[tr,1] == 0
    tx = np.column_stack([x, np.ones(len(x))])
    subset = tr[mask]
    if len(subset) < 32:
        raise ValueError('Insufficient inactive-worker training data')
    w = np.zeros(9)
    for _ in range(2400):
        p = distill.sigmoid(tx[subset] @ w)
        w -= .15 * (tx[subset].T @ (p-y[subset,1]))/len(subset)
    q10[1] = np.rint(w*1024).astype(np.int32)
    if np.any(np.abs(q10)>8192):
        raise ValueError('Existing Q10 range exceeded')
    predictions = distill.sigmoid(tx[te] @ (q10/1024).T)
    metrics=[]
    for i,name in enumerate(NAMES):
        selected = (x[te,1] == 0) if i == 1 else np.ones(len(te),dtype=bool)
        labels, pred = y[te,i][selected] >= .5, predictions[:,i][selected] >= .5
        train_subset = subset if i == 1 else tr
        majority = np.mean(y[train_subset,i] >= .5) >= .5
        positive = labels.sum()
        negative = (~labels).sum()
        metrics.append(dict(name=name, test_examples=int(selected.sum()),
            agreement=float(np.mean(labels==pred)), majority_baseline=float(np.mean(labels==majority)),
            positive_recall=float(np.mean(pred[labels])) if positive else None,
            negative_recall=float(np.mean(~pred[~labels])) if negative else None,
            positives=int(positive), negatives=int(negative),
            scope='inactive_workers_only' if i==1 else 'all_workers'))
    model=distill.model_document(q10)
    model['contract']='worker-process-v3'
    report=dict(seed=SEED, examples=len(x), train_examples=len(tr), test_examples=len(te),
                wake_train_examples=len(subset), wake_training='readiness_0_training_subset_only',
                teacher_sha256=hashlib.sha256(teacher.read_bytes()).hexdigest(), per_head=metrics,
                status='DESCRIPTIVE_NOT_PHYSICAL_ACCEPTANCE', wake_capability=audit_wake(model),
                teacher_models=sorted({json.loads(line)['teacher_model'] for line in teacher.read_text().splitlines()}))
    for name,data in [('rows.json',model),('training-report.json',report)]:
        with (args.output/name).open('x') as stream:
            json.dump(data,stream,indent=2)
    print('Worker-process candidate frozen; physical acceptance still required.')


if __name__ == '__main__':
    main()
