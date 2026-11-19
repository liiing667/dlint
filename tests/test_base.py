#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import unittest

import dlint


class DummyLinter(dlint.linters.base.BaseLinter):
    _error_tmpl = 'DUOXXX error message'


class TestFlake8Result(unittest.TestCase):

    def test_result_from_located_node(self):
        node = ast.Name(id='foo', lineno=3, col_offset=7)

        result = dlint.linters.base.result_from_node(node, 'message')

        assert result == dlint.linters.base.Flake8Result(3, 7, 'message')

    def test_result_from_unknown_location_node(self):
        node = ast.Name(id='foo')

        result = dlint.linters.base.result_from_node(node, 'message')

        assert result == dlint.linters.base.Flake8Result(
            dlint.linters.base.UNKNOWN_LINENO,
            dlint.linters.base.UNKNOWN_COL_OFFSET,
            'message'
        )

    def test_node_position_unknown_sentinel(self):
        node = ast.Name(id='foo')

        assert dlint.linters.base.node_position(node) == (
            dlint.linters.base.UNKNOWN_LINENO,
            dlint.linters.base.UNKNOWN_COL_OFFSET
        )


class TestBaseLinter(unittest.TestCase):

    def _linter(self):
        linter = DummyLinter()
        linter.namespace = object()

        return linter

    def test_append_node_result_uses_node_position(self):
        linter = self._linter()
        node = ast.Name(id='foo', lineno=2, col_offset=4)

        linter.append_node_result(node)

        assert linter.get_results() == [
            dlint.linters.base.Flake8Result(2, 4, DummyLinter._error_tmpl)
        ]

    def test_append_node_result_merges_duplicates_stably(self):
        linter = self._linter()
        first = ast.Name(id='foo', lineno=2, col_offset=0)
        second = ast.Name(id='bar', lineno=3, col_offset=0)

        linter.append_node_result(first)
        linter.append_node_result(second)
        linter.append_node_result(first)

        assert linter.get_results() == [
            dlint.linters.base.Flake8Result(2, 0, DummyLinter._error_tmpl),
            dlint.linters.base.Flake8Result(3, 0, DummyLinter._error_tmpl),
        ]

    def test_extend_node_results_merges_duplicates(self):
        linter = self._linter()
        first = ast.Name(id='foo', lineno=2, col_offset=0)
        second = ast.Name(id='bar', lineno=3, col_offset=0)

        linter.extend_node_results([first, second, first])

        assert linter.get_results() == [
            dlint.linters.base.Flake8Result(2, 0, DummyLinter._error_tmpl),
            dlint.linters.base.Flake8Result(3, 0, DummyLinter._error_tmpl),
        ]

    def test_unknown_location_result_uses_sentinel(self):
        linter = self._linter()

        linter.append_node_result(ast.Name(id='foo'))

        assert linter.get_results() == [
            dlint.linters.base.Flake8Result(
                dlint.linters.base.UNKNOWN_LINENO,
                dlint.linters.base.UNKNOWN_COL_OFFSET,
                DummyLinter._error_tmpl
            )
        ]


if __name__ == "__main__":
    unittest.main()
