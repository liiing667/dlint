#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import textwrap
import unittest

import dlint


class TestFlake8Result(unittest.TestCase):

    def test_node_result_matches_node_location(self):
        python_node = ast.parse(
            textwrap.dedent(
                """
                foo(bar)
                """
            )
        )

        call_node = python_node.body[0].value
        message = 'DUOXXX error message'

        result = dlint.linters.base.node_result(call_node, message)

        expected = dlint.linters.base.Flake8Result(
            lineno=call_node.lineno,
            col_offset=call_node.col_offset,
            message=message
        )

        assert result == expected
        assert result.lineno == 2
        assert result.col_offset == 0

    def test_node_result_unknown_location_is_explicit(self):
        class LocationlessNode(ast.AST):
            pass

        result = dlint.linters.base.node_result(
            LocationlessNode(),
            'DUOXXX error message'
        )

        assert result.lineno == dlint.linters.base.UNKNOWN_LINENO
        assert result.col_offset == dlint.linters.base.UNKNOWN_COL_OFFSET
        assert result.lineno < 0
        assert result.col_offset < 0


class RecordingLinter(dlint.linters.base.BaseLinter):
    _error_tmpl = 'DUOXXX error message'


class TestBaseLinterResults(unittest.TestCase):

    def test_append_node_result_deduplicates_fingerprints(self):
        python_node = ast.parse(
            textwrap.dedent(
                """
                foo(bar)
                """
            )
        )

        call_node = python_node.body[0].value
        linter = RecordingLinter()

        linter.append_node_result(call_node, linter._error_tmpl)
        linter.append_node_result(call_node, linter._error_tmpl)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=2,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_results_preserve_first_seen_ordering(self):
        python_node = ast.parse(
            textwrap.dedent(
                """
                first()
                second()
                third()
                """
            )
        )

        call_nodes = [statement.value for statement in python_node.body]
        linter = RecordingLinter()

        # Report out of order, then repeat a node; ordering must stay stable.
        linter.append_node_result(call_nodes[2], linter._error_tmpl)
        linter.append_node_result(call_nodes[0], linter._error_tmpl)
        linter.append_node_result(call_nodes[1], linter._error_tmpl)
        linter.append_node_result(call_nodes[2], linter._error_tmpl)

        result = linter.get_results()

        assert [r.lineno for r in result] == [4, 2, 3]
        assert len(result) == 3

    def test_extend_node_results_deduplicates(self):
        python_node = ast.parse(
            textwrap.dedent(
                """
                foo(bar)
                """
            )
        )

        call_node = python_node.body[0].value
        linter = RecordingLinter()

        linter.extend_node_results(
            [call_node, call_node],
            linter._error_tmpl
        )

        assert len(linter.get_results()) == 1

    def test_unknown_location_results_are_deduplicated(self):
        class LocationlessNode(ast.AST):
            pass

        linter = RecordingLinter()
        linter.append_node_result(LocationlessNode(), linter._error_tmpl)
        linter.append_node_result(LocationlessNode(), linter._error_tmpl)

        result = linter.get_results()

        assert len(result) == 1
        assert result[0].lineno == dlint.linters.base.UNKNOWN_LINENO
        assert result[0].col_offset == dlint.linters.base.UNKNOWN_COL_OFFSET


if __name__ == "__main__":
    unittest.main()
