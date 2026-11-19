#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import os
import shutil
import tempfile
import unittest

import dlint


class TestResourceBudget(unittest.TestCase):

    def test_charge_file_within_budget(self):
        budget = dlint.limits.ResourceBudget(max_file_bytes=10)

        budget.charge_file(b'12345')
        budget.charge_file(b'67890')

        assert budget.file_bytes == 10
        assert budget.exceeded_stage is None

    def test_charge_file_exceeded(self):
        budget = dlint.limits.ResourceBudget(max_file_bytes=4)

        with self.assertRaises(dlint.limits.BudgetExceeded) as context:
            budget.charge_file(b'12345')

        assert context.exception.stage == 'file'
        assert budget.exceeded_stage == 'file'

    def test_charge_ast_node_exceeded(self):
        budget = dlint.limits.ResourceBudget(max_ast_nodes=2)

        budget.charge_ast_node()
        budget.charge_ast_node()

        with self.assertRaises(dlint.limits.BudgetExceeded) as context:
            budget.charge_ast_node()

        assert context.exception.stage == 'ast'
        assert budget.exceeded_stage == 'ast'

    def test_charge_result_exceeded(self):
        budget = dlint.limits.ResourceBudget(max_results=1)

        budget.charge_result()

        with self.assertRaises(dlint.limits.BudgetExceeded) as context:
            budget.charge_result()

        assert context.exception.stage == 'report'
        assert budget.exceeded_stage == 'report'

    def test_stages_share_one_budget_instance(self):
        budget = dlint.limits.ResourceBudget(
            max_file_bytes=100, max_ast_nodes=100, max_results=100
        )

        budget.charge_file(b'x' * 50)
        budget.charge_ast_node()
        budget.charge_result()

        assert (budget.file_bytes, budget.ast_nodes, budget.results) == (
            50, 1, 1
        )


class TestReadSource(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.directory)

    def _write(self, name, content):
        path = os.path.join(self.directory, name)
        with open(path, 'wb') as fd:
            fd.write(content)
        return path

    def test_read_source_within_budget(self):
        path = self._write('small.py', b'x = 1\n')
        budget = dlint.limits.ResourceBudget(max_file_bytes=64)

        source = dlint.limits.read_source(path, budget)

        assert source == 'x = 1\n'
        assert budget.file_bytes == 6

    def test_read_source_oversized_rejected_early(self):
        path = self._write('big.py', b'x' * 256)
        budget = dlint.limits.ResourceBudget(max_file_bytes=32)

        with self.assertRaises(dlint.limits.BudgetExceeded) as context:
            dlint.limits.read_source(path, budget)

        assert context.exception.stage == 'file'
        assert budget.file_bytes > 32

    def test_read_source_undecodable_rejected(self):
        path = self._write('bad.py', b'# \xff\xfe\n')
        budget = dlint.limits.ResourceBudget()

        with self.assertRaises(dlint.limits.UnreadableSource) as context:
            dlint.limits.read_source(path, budget)

        assert context.exception.stage == 'encoding'

    def test_read_source_missing_file(self):
        budget = dlint.limits.ResourceBudget()

        with self.assertRaises(dlint.limits.UnreadableSource) as context:
            dlint.limits.read_source(
                os.path.join(self.directory, 'missing.py'), budget
            )

        assert context.exception.stage == 'file'


class TestAstBudgets(unittest.TestCase):

    def test_count_ast_nodes_within_budget(self):
        tree = ast.parse('x = 1\ny = 2\n')
        budget = dlint.limits.ResourceBudget(max_ast_nodes=100)

        count = dlint.limits.count_ast_nodes(tree, budget)

        assert count == budget.ast_nodes
        assert count > 0

    def test_count_ast_nodes_exceeded(self):
        tree = ast.parse('x = 1\n')
        budget = dlint.limits.ResourceBudget(max_ast_nodes=1)

        with self.assertRaises(dlint.limits.BudgetExceeded) as context:
            dlint.limits.count_ast_nodes(tree, budget)

        assert context.exception.stage == 'ast'

    def test_parse_source_charges_ast_budget(self):
        budget = dlint.limits.ResourceBudget(max_ast_nodes=100)

        tree = dlint.limits.parse_source('x = 1\n', budget)

        assert isinstance(tree, ast.Module)
        assert budget.ast_nodes > 0

    def test_parse_source_exceeded(self):
        budget = dlint.limits.ResourceBudget(max_ast_nodes=1)

        with self.assertRaises(dlint.limits.BudgetExceeded):
            dlint.limits.parse_source('x = 1\n', budget)


class TestMessages(unittest.TestCase):

    def test_incomplete_message(self):
        message = dlint.limits.incomplete_message('file budget exceeded')

        assert message.startswith(dlint.limits.INCOMPLETE_CODE)
        assert 'file budget exceeded' in message

    def test_incomplete_message_with_detail(self):
        message = dlint.limits.incomplete_message('rejected', 'limit 1')

        assert message.startswith(dlint.limits.INCOMPLETE_CODE)
        assert 'rejected' in message
        assert 'limit 1' in message

    def test_describe_budget_failure(self):
        exc = dlint.limits.BudgetExceeded('ast', 10, 11)

        reason = dlint.limits.describe_failure(exc)

        assert 'ast' in reason
        assert '10' in reason
        assert '11' in reason

    def test_describe_memory_error(self):
        reason = dlint.limits.describe_failure(MemoryError())

        assert 'memory' in reason


class TestIsRealFile(unittest.TestCase):

    def test_stdin_is_not_real_file(self):
        assert dlint.limits.is_real_file('stdin') is False

    def test_empty_name_is_not_real_file(self):
        assert dlint.limits.is_real_file('') is False

    def test_existing_file_is_real_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)

        try:
            assert dlint.limits.is_real_file(path) is True
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
