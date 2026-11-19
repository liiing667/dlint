#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast


class BudgetExceeded(Exception):
    """Raised when a shared :class:`ScanBudget` has been exhausted."""

    def __init__(self, budget, stage, limit, used):
        self.budget = budget
        self.stage = stage
        self.limit = limit
        self.used = used

        message = (
            "scan budget of {limit} units exceeded during the {stage} stage "
            "after {used} units"
        ).format(limit=limit, stage=stage, used=used)

        super(BudgetExceeded, self).__init__(message)


class ScanBudget(object):
    """Shared budget for the file, AST and reporting stages of a scan.

    Every stage draws from the same pool of abstract "units" so that a single
    pathological input cannot exhaust memory in one stage while the others
    remain unaware. A stage asks the budget to ``consume`` units as it works;
    the first request that would push usage past the limit raises
    :class:`BudgetExceeded` instead of silently dropping the scan.
    """

    STAGE_FILE = 'file'
    STAGE_AST = 'ast'
    STAGE_REPORT = 'report'

    def __init__(self, limit):
        if limit < 0:
            raise ValueError(
                'budget limit must be zero or positive, received {}'.format(limit)
            )

        self.limit = limit
        self.used = 0
        self.exceeded = False
        self.exceeded_stage = None

    def remaining(self):
        return self.limit - self.used

    def consume(self, units, stage):
        if units < 0:
            raise ValueError(
                'consumed units must be zero or positive, received {}'.format(units)
            )

        if self.exceeded:
            raise BudgetExceeded(
                self, self.exceeded_stage, self.limit, self.used
            )

        self.used += units

        if self.used > self.limit:
            self.exceeded = True
            self.exceeded_stage = stage
            raise BudgetExceeded(self, stage, self.limit, self.used)

    def charge_file(self, byte_count):
        """Charge the raw byte size of a source file to the file stage."""
        self.consume(byte_count, self.STAGE_FILE)

    def charge_report(self, result_count=1):
        """Charge findings emitted during the report stage."""
        self.consume(result_count, self.STAGE_REPORT)


class BudgetedNodeVisitor(ast.NodeVisitor):
    """Wrap an AST walk so every visited node charges the shared budget.

    Visitors receive the same node callbacks as a plain ``ast.NodeVisitor``,
    but each traversed node consumes one unit from ``budget``. When the budget
    is exhausted :class:`BudgetExceeded` propagates out of :meth:`visit` and
    the partially walked tree is left in place.
    """

    def __init__(self, budget, *args, **kwargs):
        self.budget = budget

        super(BudgetedNodeVisitor, self).__init__(*args, **kwargs)

    def visit(self, node):
        self.budget.consume(1, ScanBudget.STAGE_AST)

        return self.dispatch(node)

    def dispatch(self, node):
        """Visit ``node`` after the AST charge has been applied.

        Subclasses override this to customize node dispatch without
        bypassing the shared budget charge.
        """
        return super(BudgetedNodeVisitor, self).visit(node)


def count_ast_nodes(tree):
    """Return the number of AST nodes rooted at ``tree``."""
    return sum(1 for _ in ast.walk(tree))
