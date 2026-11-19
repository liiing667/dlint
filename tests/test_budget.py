#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import unittest

import pytest

import dlint


class TestScanBudget(unittest.TestCase):

    def test_budget_consume_within_limit(self):
        scan_budget = dlint.budget.ScanBudget(10)

        scan_budget.consume(4, dlint.budget.ScanBudget.STAGE_FILE)
        scan_budget.consume(6, dlint.budget.ScanBudget.STAGE_AST)

        assert scan_budget.used == 10
        assert scan_budget.remaining() == 0
        assert not scan_budget.exceeded

    def test_budget_consume_shared_across_stages(self):
        scan_budget = dlint.budget.ScanBudget(10)

        scan_budget.charge_file(4)

        with pytest.raises(dlint.budget.BudgetExceeded) as exc_info:
            scan_budget.consume(7, dlint.budget.ScanBudget.STAGE_AST)

        error = exc_info.value

        assert error.stage == dlint.budget.ScanBudget.STAGE_AST
        assert error.limit == 10
        assert error.used == 11
        assert scan_budget.exceeded
        assert scan_budget.exceeded_stage == dlint.budget.ScanBudget.STAGE_AST

    def test_budget_exceeded_keeps_raising(self):
        scan_budget = dlint.budget.ScanBudget(1)

        with pytest.raises(dlint.budget.BudgetExceeded):
            scan_budget.charge_file(2)

        with pytest.raises(dlint.budget.BudgetExceeded):
            scan_budget.charge_report()

    def test_budget_stage_helpers(self):
        scan_budget = dlint.budget.ScanBudget(100)

        scan_budget.charge_file(40)
        scan_budget.charge_report(10)

        assert scan_budget.used == 50

    def test_budget_negative_limit_rejected(self):
        with pytest.raises(ValueError):
            dlint.budget.ScanBudget(-1)

    def test_budget_negative_consume_rejected(self):
        scan_budget = dlint.budget.ScanBudget(10)

        with pytest.raises(ValueError):
            scan_budget.consume(-1, dlint.budget.ScanBudget.STAGE_AST)


class TestBudgetedNodeVisitor(unittest.TestCase):

    def test_visitor_charges_each_node(self):
        tree = ast.parse("x = 1\ny = 2\n")
        node_count = dlint.budget.count_ast_nodes(tree)
        scan_budget = dlint.budget.ScanBudget(node_count)

        class Collector(dlint.budget.BudgetedNodeVisitor):
            def __init__(self, budget):
                self.visited = 0
                super(Collector, self).__init__(budget)

            def visit(self, node):
                self.visited += 1
                super(Collector, self).visit(node)

        collector = Collector(scan_budget)
        collector.visit(tree)

        assert collector.visited == node_count
        assert scan_budget.used == node_count

    def test_visitor_stops_when_budget_exceeded(self):
        tree = ast.parse("x = 1\ny = 2\nz = 3\n")
        node_count = dlint.budget.count_ast_nodes(tree)
        scan_budget = dlint.budget.ScanBudget(2)

        visitor = dlint.budget.BudgetedNodeVisitor(scan_budget)

        with pytest.raises(dlint.budget.BudgetExceeded) as exc_info:
            visitor.visit(tree)

        assert exc_info.value.stage == dlint.budget.ScanBudget.STAGE_AST
        assert scan_budget.exceeded
        assert scan_budget.used <= node_count


if __name__ == "__main__":
    unittest.main()
