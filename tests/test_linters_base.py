#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import unittest

import dlint


def get_linter_implementation(severity='HIGH'):
    class Cls(dlint.linters.base.BaseLinter):
        _code = 'DUOXXX'
        _error_tmpl = 'DUOXXX error message'
        _severity = severity

        def visit_Name(self, node):
            if node.id == 'foo':
                result, _finding = self.new_result(
                    node.lineno,
                    node.col_offset
                )
                self.results.append(result)

    return Cls


class TestBaseLinter(dlint.test.base.BaseTest):

    def test_default_severity_is_defined(self):
        linter_class = get_linter_implementation()

        assert linter_class._get_severity() == dlint.severity.Severity('HIGH')
        assert linter_class().code == 'DUOXXX'

    def test_finding_identity_matches_result(self):
        python_node = self.get_ast_node(
            """
            foo()
            """
        )

        linter = get_linter_implementation('LOW')()
        linter.visit(python_node)

        result = linter.get_results()
        findings = linter.get_findings()

        assert len(result) == 1
        assert len(findings) == 1

        finding = findings[0]
        assert finding.lineno == result[0].lineno
        assert finding.col_offset == result[0].col_offset
        assert finding.message == result[0].message
        assert finding.code == 'DUOXXX'
        assert finding.severity == dlint.severity.Severity('LOW')

    def test_new_result_pairs_result_and_finding(self):
        linter = get_linter_implementation('MEDIUM')()

        result, finding = linter.new_result(3, 7)

        assert result == dlint.linters.base.Flake8Result(
            lineno=3,
            col_offset=7,
            message='DUOXXX error message'
        )
        assert finding == dlint.linters.base.Finding(
            lineno=3,
            col_offset=7,
            message='DUOXXX error message',
            code='DUOXXX',
            severity=dlint.severity.Severity('MEDIUM')
        )

    def test_unknown_rule_severity_fails_closed(self):
        class BrokenLinter(dlint.linters.base.BaseLinter):
            _code = 'DUOBROKEN'
            _error_tmpl = 'DUOBROKEN error message'
            _severity = 'CRITICAL'

        with self.assertRaises(dlint.severity.InvalidSeverity):
            BrokenLinter()

    def test_missing_rule_severity_fails_closed(self):
        class BrokenLinter(dlint.linters.base.BaseLinter):
            _code = 'DUOBROKEN'
            _error_tmpl = 'DUOBROKEN error message'
            _severity = None

        with self.assertRaises(dlint.severity.InvalidSeverity):
            BrokenLinter()

    def test_all_shipped_linters_have_valid_severity(self):
        for linter_class in dlint.linters.ALL:
            parsed = dlint.severity.Severity.parse(linter_class._severity)
            assert linter_class._get_severity() == parsed


if __name__ == "__main__":
    unittest.main()
