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
    kwargs.setdefault("ignore", [])
    kwargs.setdefault("extend_ignore", [])
    kwargs.setdefault("disable_noqa", False)
    kwargs.setdefault("enable_extensions", [])

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


class TestFlake8Extension(base.BaseTest):

    def test_flake8_extension_plugin_duplicate_code_fails_closed(self):
        class DlintDuplicateLinter(extension.dlint.linters.base.BaseLinter):
            _code = extension.dlint.linters.BadEvalUseLinter._code
            _error_tmpl = (
                extension.dlint.linters.BadEvalUseLinter._code
                + " duplicate plugin rule"
            )
        original_plugin_classes = (
            extension.Flake8Extension.get_plugin_linter_classes
        )

        extension.Flake8Extension.get_plugin_linter_classes = classmethod(
            lambda cls: [DlintDuplicateLinter]
        )
        try:
            with self.assertRaises(extension.dlint.registry.RegistryError):
                extension.Flake8Extension.get_linter_classes()
        finally:
            extension.Flake8Extension.get_plugin_linter_classes = (
                original_plugin_classes
            )

        # The built-in registry itself is left untouched by the failed merge.
        builtin_registry = extension.dlint.linters.REGISTRY
        assert (
            builtin_registry.get_by_code(
                extension.dlint.linters.BadEvalUseLinter._code
            )
            is extension.dlint.linters.BadEvalUseLinter
        )

    def test_flake8_extension_plugin_same_class_is_deduplicated(self):
        linter_class = extension.dlint.linters.BadEvalUseLinter
        original_plugin_classes = (
            extension.Flake8Extension.get_plugin_linter_classes
        )

        extension.Flake8Extension.get_plugin_linter_classes = classmethod(
            lambda cls: [linter_class, linter_class]
        )
        try:
            result = extension.Flake8Extension.get_linter_classes()
        finally:
            extension.Flake8Extension.get_plugin_linter_classes = (
                original_plugin_classes
            )

        assert result == extension.dlint.linters.ALL

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


if __name__ == "__main__":
    unittest.main()
