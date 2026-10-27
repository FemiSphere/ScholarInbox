"""Task contexts must survive concurrent dispatch without leaking between items."""
from contextvars import ContextVar

from literature_digest.concurrency import cooperative_map
from literature_digest.llm.base import current_llm_deadline, llm_time_budget
from literature_digest.telemetry import current_llm_operation, llm_operation


def test_parallel_tasks_inherit_deadline_and_get_independent_contexts():
    value = ContextVar('test_task_value', default=None)
    token = value.set('parent')
    def work(index):
        initial = value.get()
        value.set(index)
        return initial, current_llm_deadline(), current_llm_operation()
    try:
        with llm_time_budget(5), llm_operation('paper_ranking', 4):
            deadline = current_llm_deadline()
            results = cooperative_map(work, range(4), max_workers=2, thread_name_prefix='context-test')
        assert results == [('parent', deadline, 'paper_ranking')] * 4
        assert value.get() == 'parent'
        assert current_llm_deadline() is None
    finally:
        value.reset(token)
