"""Revision 3: worker process activation on computers that remain awake."""
from contract import FEATURES, NAMES, project, choose

CONTEXT = (
    'State describes ONE dedicated compute worker process on an already-awake computer. '
    'Do not suspend, reboot, shut down or wake the computer itself. '
    'capable is required CPU or CUDA kernel support. readiness is 1 process running and ready, '
    '0 process stopped but its computer reachable and process can be started, -1 worker unavailable. '
    'free_capacity is available worker queue capacity. reliability is observed transport health. '
    'work_value is task demand times worker performance; high favors this worker for substantial work. '
    'energy_cost is relative execution energy; wake_cost is process startup overhead, not host boot cost. '
    'freshness is telemetry quality. All except readiness are 0..1. '
    'Favor ready efficient workers for small work; activate a capable powerful worker for demanding '
    'work when benefit justifies execution and startup costs. Busy, incapable, unreliable, stale '
    'or unavailable workers should not receive work. '
)
QUESTIONS = dict(zip(NAMES, [CONTEXT + question for question in (
    'How suitable is this worker for this task, including performance, execution energy and process startup cost?',
    'If this worker process is currently stopped (readiness 0), should it be activated for this task because its work value justifies its execution and startup costs?',
    'Is this worker busy, with insufficient free_capacity to accept this task now?',
    'Is this worker capable of executing the required task kernel?',
    'Is this worker transport sufficiently reliable (reliability at least 0.8)?',
    'Must telemetry be queried again because freshness is below 0.5?',
    'Should an alternative local execution path be considered because this worker cannot be used?',
    'Should this worker be rejected because it is incapable, busy, unreliable, stale or unavailable (readiness -1)?',
)]))
