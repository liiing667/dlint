#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import argparse
import ast
import os
import sys
import unittest

# Since extension imports dlint we cannot add it to the module or else we'll
# have circular imports. Thus we must come up with some tricks to import it
sys.path.append(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "dlint"
    )
)

import extension  # noqa: E402


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_path(name):
    return os.path.join(FIXTURE_DIR, name)


def create_options(**kwargs):
    kwargs.setdefault("select", ["DUO"])
    kwargs.setdefault("extended_default_select", [])
    kwargs.setdefault("ignore", [])
    kwargs.setdefault("extend_ignore", [])
    kwargs.setdefault("extend_select", [])
    kwargs.setdefault("extended_default_ignore", [])
    kwargs.setdefault("disable_noqa", False)
    kwargs.setdefault("enable_extensions", [])
    kwargs.setdefault(
        "dlint_budget_limit",
        extension.Flake8Extension.DEFAULT_BUDGET_LIMIT
    )

    return argparse.Namespace(**kwargs)


def parse_fixture(name):
    with open(fixture_path(name), "rb") as fd:
        return ast.parse(fd.read())


def result_codes(results):
    return [message.split(" ", 1)[0] for _, _, message, _ in results]


class TestScanBudgetMatrix(unittest.TestCase):
    """Fixed, offline matrix proving rejection and compatibility paths."""

    REJECTED_MATRIX = (
        ("oversized.py", extension.Flake8Extension.INCOMPLETE_CODE),
        ("encoding_invalid.py", extension.Flake8Extension.INCOMPLETE_CODE),
    )

    COMPATIBLE_MATRIX = (
        ("compatible_clean.py", []),
        ("compatible_findings.py", ["DUO103", "DUO104"]),
        ("compatible_utf8.py", []),
        ("compatible_latin1.py", []),
    )

    def setUp(self):
        self.ext = extension.Flake8Extension
        self.previous_options = self.ext.options
        self.ext.options = create_options()

    def tearDown(self):
        self.ext.options = self.previous_options

    def test_matrix_covers_both_rejection_and_compatibility(self):
        rejected_names = [name for name, _ in self.REJECTED_MATRIX]
        compatible_names = [name for name, _ in self.COMPATIBLE_MATRIX]

        for name in rejected_names + compatible_names:
            assert os.path.isfile(fixture_path(name)), name

        assert rejected_names
        assert compatible_names

    def test_file_ast_and_report_share_one_budget_pool(self):
        filename = fixture_path("compatible_findings.py")
        tree = parse_fixture("compatible_findings.py")
        byte_count = os.path.getsize(filename)
        node_count = extension.dlint.budget.count_ast_nodes(tree)

        # The limit is smaller than the three stages combined, so even
        # though each stage would fit on its own, the shared pool must run
        # out during the AST stage.
        self.ext.options.dlint_budget_limit = byte_count + node_count - 1

        linter = extension.Flake8Extension(tree, filename)
        results = list(linter.run())

        assert result_codes(results) == [
            extension.Flake8Extension.INCOMPLETE_CODE
        ]
        assert linter.scan_budget.exceeded_stage == "ast"
        assert linter.scan_budget.used == byte_count + node_count

    def test_oversized_file_is_rejected_with_incomplete_status(self):
        filename = fixture_path("oversized.py")
        tree = parse_fixture("oversized.py")

        options = self.ext.options
        options.dlint_budget_limit = os.path.getsize(filename) - 1

        linter = extension.Flake8Extension(tree, filename)
        results = list(linter.run())

        codes = result_codes(results)

        assert codes == [extension.Flake8Extension.INCOMPLETE_CODE]
        assert linter.scan_budget.exceeded
        assert linter.scan_budget.exceeded_stage == "file"

    def test_encoding_anomaly_is_rejected_with_incomplete_status(self):
        filename = fixture_path("encoding_invalid.py")

        reason = extension.Flake8Extension._detect_encoding_error(filename)
        assert reason is not None

        linter = extension.Flake8Extension(
            ast.parse(""), filename
        )
        results = list(linter.run())

        codes = result_codes(results)

        assert codes == [extension.Flake8Extension.INCOMPLETE_CODE]
        assert "not decodable" in results[0][2]

    def test_ast_stage_exhaustion_is_visible(self):
        tree = parse_fixture("oversized.py")
        node_count = extension.dlint.budget.count_ast_nodes(tree)

        options = self.ext.options
        options.dlint_budget_limit = node_count - 1

        linter = extension.Flake8Extension(tree, "stdin")
        results = list(linter.run())

        codes = result_codes(results)

        assert codes == [extension.Flake8Extension.INCOMPLETE_CODE]
        assert linter.scan_budget.exceeded_stage == "ast"

    def test_zero_budget_rejects_even_an_empty_tree(self):
        self.ext.options.dlint_budget_limit = 0

        linter = extension.Flake8Extension(ast.parse(""), "stdin")
        results = list(linter.run())

        assert result_codes(results) == [
            extension.Flake8Extension.INCOMPLETE_CODE
        ]
        assert linter.scan_budget.exceeded_stage == "ast"

    def test_report_stage_exhaustion_is_visible(self):
        tree = parse_fixture("compatible_findings.py")

        options = self.ext.options
        # File and AST stages fit, but the report budget cannot hold a
        # single finding.
        options.dlint_budget_limit = extension.dlint.budget.count_ast_nodes(
            tree
        )

        linter = extension.Flake8Extension(tree, "stdin")
        results = list(linter.run())

        codes = result_codes(results)

        assert codes == [extension.Flake8Extension.INCOMPLETE_CODE]
        assert linter.scan_budget.exceeded_stage == "report"

    def test_findings_before_report_budget_exhaustion_remain_visible(self):
        tree = parse_fixture("compatible_findings.py")
        node_count = extension.dlint.budget.count_ast_nodes(tree)

        self.ext.options.dlint_budget_limit = node_count + 1

        linter = extension.Flake8Extension(tree, "stdin")
        results = list(linter.run())
        codes = result_codes(results)

        # One finding fits the remaining budget, the second one trips the
        # report stage and is replaced by the incomplete marker.
        assert codes[-1] == extension.Flake8Extension.INCOMPLETE_CODE
        assert len(codes) == 2
        assert codes[0] in ("DUO103", "DUO104")

    def test_compatible_matrix_still_scans_normally(self):
        for filename, expected_codes in self.COMPATIBLE_MATRIX:
            tree = parse_fixture(filename)
            linter = extension.Flake8Extension(tree, fixture_path(filename))

            results = list(linter.run())
            codes = result_codes(results)

            assert sorted(codes) == sorted(expected_codes), filename
            assert not linter.scan_budget.exceeded, filename

    def test_rejected_matrix_never_reports_clean(self):
        for filename, expected_code in self.REJECTED_MATRIX:
            if filename == "oversized.py":
                tree = parse_fixture(filename)
                options = self.ext.options
                options.dlint_budget_limit = os.path.getsize(
                    fixture_path(filename)
                ) - 1
            else:
                tree = ast.parse("")

            linter = extension.Flake8Extension(tree, fixture_path(filename))
            results = list(linter.run())

            assert result_codes(results) == [expected_code], filename


if __name__ == "__main__":
    unittest.main()
