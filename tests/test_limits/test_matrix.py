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
import sys
import tempfile
import unittest

# Since extension imports dlint we cannot add it to the module or else we'll
# have circular imports. Thus we must come up with some tricks to import it
sys.path.append(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "dlint"
    )
)

import extension  # noqa: E402
import dlint  # noqa: E402


FIXTURE_DIRECTORY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'fixtures'
)


def fixture_path(name):
    return os.path.join(FIXTURE_DIRECTORY, name)


class TestOfflineFileMatrix(unittest.TestCase):
    """Fixed offline matrix proving rejection and compatibility behavior."""

    MATRIX = (
        # fixture, expected outcome
        ('normal_clean.py', 'compatible'),
        ('normal_findings.py', 'compatible_with_findings'),
        ('oversized_file.py', 'rejected_file'),
        ('too_many_nodes.py', 'rejected_ast'),
        ('undecodable_utf8.py', 'rejected_encoding'),
        ('utf16_source.py', 'rejected_encoding'),
    )

    def setUp(self):
        self.directory = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.directory)

    def _materialize(self, fixture, padding):
        """Copy a fixed fixture into a temp directory, optionally padding it."""
        source = fixture_path(fixture)
        destination = os.path.join(self.directory, fixture)

        with open(source, 'rb') as fd:
            content = fd.read()

        if padding == 'file':
            content = content.replace(
                b'# PADDING_MARKER',
                b'padding = "' + (b'a' * 512) + b'"\n'
            )
        elif padding == 'nodes':
            assignments = b'\n'.join(
                b'var_%d = %d' % (index, index) for index in range(200)
            )
            content = content.replace(b'# NODES_MARKER', assignments)

        with open(destination, 'wb') as fd:
            fd.write(content)

        return destination

    def _extension(self, path, **budget_kwargs):
        # The tree is re-parsed internally for on-disk files, so an empty
        # placeholder keeps the constructor signature unchanged.
        budget = dlint.limits.ResourceBudget(**budget_kwargs)
        return extension.Flake8Extension(ast.parse(''), path, budget)

    def _result_codes(self, results):
        return [result[2].split(' ', 1)[0] for result in results]

    def test_fixed_matrix_rejects_and_accepts_every_fixture(self):
        matrix_budget = dict(
            max_file_bytes=256,
            max_ast_nodes=100,
            max_results=10
        )

        observed = {}

        for fixture, expected in self.MATRIX:
            if fixture == 'oversized_file.py':
                path = self._materialize(fixture, 'file')
            elif fixture == 'too_many_nodes.py':
                path = self._materialize(fixture, 'nodes')
            else:
                path = self._materialize(fixture, None)

            linter = self._extension(path, **matrix_budget)
            results = list(linter.run())
            codes = self._result_codes(results)

            if expected in ('rejected_file', 'rejected_ast',
                            'rejected_encoding'):
                observed[fixture] = (
                    'rejected'
                    if dlint.limits.INCOMPLETE_CODE in codes
                    else 'silent'
                )
                assert linter.incomplete is not None
                assert len(results) == 1
                assert results[0][0] == 1
                assert results[0][1] == 0
            elif expected == 'compatible':
                observed[fixture] = (
                    'compatible' if not results else 'unexpected_findings'
                )
                assert linter.incomplete is None
            else:
                observed[fixture] = (
                    'compatible_with_findings'
                    if dlint.limits.INCOMPLETE_CODE not in codes and results
                    else 'missing_findings'
                )
                assert linter.incomplete is None
                assert dlint.linters.BadEvalUseLinter._code in codes

        expected_observed = {
            'normal_clean.py': 'compatible',
            'normal_findings.py': 'compatible_with_findings',
            'oversized_file.py': 'rejected',
            'too_many_nodes.py': 'rejected',
            'undecodable_utf8.py': 'rejected',
            'utf16_source.py': 'rejected',
        }

        assert observed == expected_observed

    def test_normal_source_scanned_with_default_budget(self):
        path = self._materialize('normal_findings.py', None)
        linter = self._extension(path)

        results = list(linter.run())
        codes = self._result_codes(results)

        assert dlint.linters.BadEvalUseLinter._code in codes
        assert dlint.limits.INCOMPLETE_CODE not in codes

    def test_incomplete_is_visible_not_silent_on_oversize(self):
        path = self._materialize('oversized_file.py', 'file')
        linter = self._extension(path, max_file_bytes=128)

        results = list(linter.run())

        assert len(results) == 1
        assert results[0][2].startswith(dlint.limits.INCOMPLETE_CODE)
        assert 'file budget exceeded' in results[0][2]

    def test_incomplete_is_visible_not_silent_on_bad_encoding(self):
        path = self._materialize('undecodable_utf8.py', None)
        linter = self._extension(path)

        results = list(linter.run())

        assert len(results) == 1
        assert results[0][2].startswith(dlint.limits.INCOMPLETE_CODE)
        assert 'encoding error' in results[0][2]

    def test_report_budget_emits_visible_incomplete(self):
        tree = ast.parse(
            '\n'.join('eval(%d)' % index for index in range(20))
        )
        budget = dlint.limits.ResourceBudget(
            max_file_bytes=1024,
            max_ast_nodes=10000,
            max_results=2
        )

        linter = extension.Flake8Extension(tree, 'stdin', budget)
        results = list(linter.run())
        codes = self._result_codes(results)

        assert codes.count(dlint.limits.INCOMPLETE_CODE) == 1
        assert codes[-1] == dlint.limits.INCOMPLETE_CODE
        assert linter.incomplete is not None

    def test_stdin_tree_uses_ast_budget_without_file_read(self):
        tree = ast.parse('x = 1\n')
        budget = dlint.limits.ResourceBudget(max_ast_nodes=1)

        linter = extension.Flake8Extension(tree, 'stdin', budget)
        results = list(linter.run())

        assert len(results) == 1
        assert results[0][2].startswith(dlint.limits.INCOMPLETE_CODE)
        assert 'ast budget exceeded' in results[0][2]


if __name__ == "__main__":
    unittest.main()
