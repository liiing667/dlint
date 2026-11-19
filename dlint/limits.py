#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import os


INCOMPLETE_CODE = 'DUO139'

DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_AST_NODES = 500000
DEFAULT_MAX_RESULTS = 100000

READ_CHUNK_BYTES = 64 * 1024


class BudgetExceeded(Exception):
    """Raised when a shared scan budget is exhausted.

    The ``stage`` attribute identifies which budget was exceeded:
    ``'file'``, ``'ast'``, or ``'report'``.
    """

    def __init__(self, stage, limit, observed):
        self.stage = stage
        self.limit = limit
        self.observed = observed
        super(BudgetExceeded, self).__init__(
            '{} budget exceeded: observed {} exceeds limit {}'.format(
                stage, observed, limit
            )
        )


class UnreadableSource(Exception):
    """Raised when a file cannot be read or decoded as Python source."""

    def __init__(self, stage, detail):
        self.stage = stage
        self.detail = detail
        super(UnreadableSource, self).__init__(
            '{} unreadable: {}'.format(stage, detail)
        )


class ResourceBudget(object):
    """Track the file, AST, and report budgets shared by a single scan.

    Every stage of a scan draws against the same budget object so that an
    oversized or malformed file is rejected before it can exhaust memory,
    and so that a pathological AST cannot produce an unbounded report.
    """

    def __init__(
        self,
        max_file_bytes=DEFAULT_MAX_FILE_BYTES,
        max_ast_nodes=DEFAULT_MAX_AST_NODES,
        max_results=DEFAULT_MAX_RESULTS
    ):
        self.max_file_bytes = max_file_bytes
        self.max_ast_nodes = max_ast_nodes
        self.max_results = max_results

        self.file_bytes = 0
        self.ast_nodes = 0
        self.results = 0

        self.exceeded_stage = None

    def charge_file(self, chunk):
        """Charge a decoded source chunk against the file budget."""
        self.file_bytes += len(chunk)

        if self.file_bytes > self.max_file_bytes:
            self.exceeded_stage = 'file'
            raise BudgetExceeded('file', self.max_file_bytes, self.file_bytes)

        return self.file_bytes

    def charge_ast_node(self):
        """Charge a single AST node against the AST budget."""
        self.ast_nodes += 1

        if self.ast_nodes > self.max_ast_nodes:
            self.exceeded_stage = 'ast'
            raise BudgetExceeded('ast', self.max_ast_nodes, self.ast_nodes)

        return self.ast_nodes

    def charge_result(self):
        """Charge a single linter result against the report budget."""
        self.results += 1

        if self.results > self.max_results:
            self.exceeded_stage = 'report'
            raise BudgetExceeded('report', self.max_results, self.results)

        return self.results


def read_source(filename, budget):
    """Read and decode a source file while charging the shared file budget.

    Reads in fixed-size chunks so that an oversized file is rejected as
    soon as the budget is exhausted instead of being buffered entirely in
    memory. Encoding failures are surfaced as ``UnreadableSource``.
    """
    source_parts = []

    try:
        with open(filename, 'rb') as fd:
            while True:
                chunk = fd.read(READ_CHUNK_BYTES)
                if not chunk:
                    break

                budget.charge_file(chunk)
                source_parts.append(chunk)
    except BudgetExceeded:
        raise
    except (IOError, OSError) as exc:
        raise UnreadableSource('file', str(exc))

    raw_source = b''.join(source_parts)

    try:
        return raw_source.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise UnreadableSource('encoding', str(exc))


def count_ast_nodes(tree, budget):
    """Count AST nodes while charging the shared AST budget.

    Uses an explicit stack rather than recursion so deeply nested, but
    still budget-compliant, source cannot overflow the Python stack.
    """
    pending = [tree]

    while pending:
        node = pending.pop()
        budget.charge_ast_node()

        for child_node in ast.iter_child_nodes(node):
            pending.append(child_node)

    return budget.ast_nodes


def parse_source(source, budget, filename='<unknown>'):
    """Parse source into an AST after charging the shared AST budget.

    The node budget is enforced up front so an oversized parse is rejected
    before visitors run, and ``MemoryError`` from a pathological parse is
    translated into a visible budget failure instead of a crash.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except MemoryError:
        budget.exceeded_stage = 'ast'
        raise BudgetExceeded('ast', budget.max_ast_nodes, budget.ast_nodes)

    count_ast_nodes(tree, budget)

    return tree


def incomplete_message(reason, detail=None):
    """Build the visible diagnostic emitted for an incomplete scan."""
    message = '{} scan incomplete: {}'.format(INCOMPLETE_CODE, reason)

    if detail:
        message = '{} ({})'.format(message, detail)

    return message


def describe_failure(exc):
    """Translate a budget or decoding failure into a human-readable reason."""
    if isinstance(exc, BudgetExceeded):
        return '{} budget exceeded (limit {}, observed {})'.format(
            exc.stage, exc.limit, exc.observed
        )

    if isinstance(exc, UnreadableSource):
        return '{} error: {}'.format(exc.stage, exc.detail)

    if isinstance(exc, MemoryError):
        return 'out of memory'

    return 'unexpected error: {}'.format(exc)


def is_real_file(filename):
    """Whether ``filename`` is an on-disk file subject to file budgets."""
    return bool(filename) and filename != 'stdin' and os.path.isfile(filename)
