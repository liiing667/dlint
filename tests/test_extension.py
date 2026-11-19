#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import argparse
import contextlib
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
sys.path.append(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "dlint",
        "test"
    )
)

import base  # noqa: E402
import extension  # noqa: E402


def create_options(**kwargs):
    kwargs.setdefault("select", [])
    kwargs.setdefault("extended_default_select", ["DUO"])
    kwargs.setdefault("extended_default_ignore", [])
    kwargs.setdefault("ignore", [])
    kwargs.setdefault("extend_ignore", [])
    kwargs.setdefault("disable_noqa", False)
    kwargs.setdefault("enable_extensions", [])
    kwargs.setdefault("dlint_min_severity", None)

    return argparse.Namespace(**kwargs)


@contextlib.contextmanager
def extension_with_options(options):
    # Flake8 requires an extension's options to be set as a class
    # variable. We have to ensure options are reset back to None after the
    # extension is used or all class instances will retain the set options.
    ext = extension.Flake8Extension
    ext.options = options
    try:
        yield ext
    finally:
        ext.options = None
        ext.min_severity = None


class TestFlake8Extension(base.BaseTest):

    FIXED_FINDING_SOURCE = """
        import random
        import pickle
        random.random()
        pickle.loads(x)
    """

    def _run_extension(self, source, **option_kwargs):
        python_node = self.get_ast_node(source)
        options = create_options(**option_kwargs)

        ext = extension.Flake8Extension
        ext.options = options
        ext.min_severity = ext._parse_min_severity(
            options.dlint_min_severity
        )
        try:
            linter = extension.Flake8Extension(python_node, "unused")
            return list(linter.run())
        finally:
            ext.options = None
            ext.min_severity = None

    def test_flake8_extension_empty(self):
        python_node = self.get_ast_node(
            """
            """
        )

        linter = extension.Flake8Extension(python_node, "unused")

        result = list(linter.run())
        expected = []

        assert result == expected

    def test_flake8_extension_basic(self):
        python_node = self.get_ast_node(
            """
            exec('print "TEST"')
            """
        )

        linter = extension.Flake8Extension(python_node, "unused")

        result = list(linter.run())
        expected = [
            (
                2,
                0,
                extension.dlint.linters.BadExecUseLinter._error_tmpl,
                extension.dlint.linters.BadExecUseLinter
            )
        ]

        assert result == expected

    def test_flake8_extension_get_linter_classes_select(self):
        options = create_options(select=["DUO101"])

        with extension_with_options(options) as ext:
            result = ext.get_linter_classes()

        expected = (extension.dlint.linters.YieldReturnStatementLinter,)

        assert result == expected

    def test_flake8_extension_get_linter_classes_extended_default_select(self):
        options = create_options(extended_default_select=["DUO101"])

        with extension_with_options(options) as ext:
            result = ext.get_linter_classes()

        expected = (extension.dlint.linters.YieldReturnStatementLinter,)

        assert result == expected

    def test_flake8_extension_get_linter_classes_ignore(self):
        options = create_options(ignore=["DUO101"])

        with extension_with_options(options) as ext:
            result = ext.get_linter_classes()

        expected = list(extension.dlint.linters.ALL)
        expected.remove(extension.dlint.linters.YieldReturnStatementLinter)
        expected = tuple(expected)

        assert result == expected

    def test_flake8_extension_get_linter_classes_extend_ignore(self):
        options = create_options(extend_ignore=["DUO101"])

        with extension_with_options(options) as ext:
            result = ext.get_linter_classes()

        expected = list(extension.dlint.linters.ALL)
        expected.remove(extension.dlint.linters.YieldReturnStatementLinter)
        expected = tuple(expected)

        assert result == expected

    def test_flake8_extension_get_linter_classes_missing_options(self):
        ext = extension.Flake8Extension

        result = ext.get_linter_classes()
        expected = extension.dlint.linters.ALL

        assert result == expected

    def test_flake8_extension_fixed_findings_are_complete(self):
        result = self._run_extension(self.FIXED_FINDING_SOURCE)

        codes = [item[3]._code for item in result]

        assert codes == ["DUO103", "DUO102"]

    def test_flake8_extension_fixed_findings_sorted_by_severity(self):
        result = self._run_extension(self.FIXED_FINDING_SOURCE)

        severities = [
            item[3]._get_severity()
            for item in result
        ]

        # HIGH (pickle) must be reported before MEDIUM (random) even though
        # the medium finding appears earlier in the source.
        assert severities == [
            extension.dlint.severity.Severity("HIGH"),
            extension.dlint.severity.Severity("MEDIUM"),
        ]

    def test_flake8_extension_min_severity_filters_findings(self):
        result = self._run_extension(
            self.FIXED_FINDING_SOURCE,
            dlint_min_severity="HIGH"
        )

        codes = [item[3]._code for item in result]

        assert codes == ["DUO103"]

    def test_flake8_extension_min_severity_medium_keeps_both(self):
        result = self._run_extension(
            self.FIXED_FINDING_SOURCE,
            dlint_min_severity="MEDIUM"
        )

        codes = sorted(item[3]._code for item in result)

        assert codes == ["DUO102", "DUO103"]

    def test_flake8_extension_min_severity_low_keeps_both(self):
        result = self._run_extension(
            self.FIXED_FINDING_SOURCE,
            dlint_min_severity="LOW"
        )

        codes = sorted(item[3]._code for item in result)

        assert codes == ["DUO102", "DUO103"]

    def test_flake8_extension_min_severity_filters_linter_classes(self):
        options = create_options(dlint_min_severity="HIGH")

        ext = extension.Flake8Extension
        ext.options = options
        ext.min_severity = ext._parse_min_severity("HIGH")
        try:
            result = ext.get_linter_classes()
        finally:
            ext.options = None
            ext.min_severity = None

        assert all(
            linter_class._get_severity()
            >= extension.dlint.severity.Severity("HIGH")
            for linter_class in result
        )
        assert extension.dlint.linters.BadExecUseLinter in result
        assert extension.dlint.linters.BadRandomGeneratorUseLinter not in result

    def test_flake8_extension_unknown_min_severity_rejected(self):
        with self.assertRaises(
            extension.dlint.severity.InvalidSeverity
        ):
            extension.Flake8Extension._parse_min_severity("CRITICAL")

    def test_flake8_extension_unknown_rule_severity_rejected(self):
        class BrokenLinter(extension.dlint.linters.base.BaseLinter):
            _code = "DUOBROKEN"
            _error_tmpl = "DUOBROKEN error message"
            _severity = "unknown"

        with self.assertRaises(
            extension.dlint.severity.InvalidSeverity
        ):
            BrokenLinter()

    def test_flake8_extension_findings_have_identity(self):
        result = self._run_extension(self.FIXED_FINDING_SOURCE)

        # Every tuple position is populated so a finding has an
        # unambiguous identity and shares the rule's severity semantics.
        assert all(
            lineno >= 1
            and col_offset >= 0
            and message.startswith(linter_class._code)
            and linter_class._get_severity()
            in extension.dlint.severity.Severity.members()
            for lineno, col_offset, message, linter_class in result
        )


if __name__ == "__main__":
    unittest.main()
