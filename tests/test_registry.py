#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import unittest

import dlint
from dlint import registry
from dlint.linters import base


class ValidLinter(base.BaseLinter):
    _code = 'DUO900'
    _error_tmpl = 'DUO900 valid test linter'

    def visit_Name(self, node):
        self.results.append(
            base.Flake8Result(
                lineno=node.lineno,
                col_offset=node.col_offset,
                message=self._error_tmpl
            )
        )


class DuplicateCodeLinter(base.BaseLinter):
    _code = 'DUO900'
    _error_tmpl = 'DUO900 duplicate code linter'


class DuplicateClassNameLinter(ValidLinter):
    _code = 'DUO901'
    _error_tmpl = 'DUO901 duplicate class name linter'


DuplicateClassNameLinter.__name__ = str('ValidLinter')


class InvalidCodeLinter(base.BaseLinter):
    _code = 'XX902'
    _error_tmpl = 'XX902 invalid code prefix'


class MisclassifiedMessageLinter(base.BaseLinter):
    _code = 'DUO903'
    _error_tmpl = 'DUO999 message does not match its code'


class TestLinterRegistry(dlint.test.base.BaseTest):

    def test_builtin_registry_contains_all_linters(self):
        registered = dlint.linters.REGISTRY.get_linter_classes()

        assert registered == dlint.linters.ALL
        assert len(registered) == 38

    def test_builtin_registry_codes_are_unique_and_well_formed(self):
        codes = dlint.linters.REGISTRY.get_codes()

        assert len(codes) == len(set(codes))
        assert all(registry.CODE_RE.match(code) for code in codes)

    def test_builtin_registry_class_names_are_unique(self):
        class_names = [
            linter_class.__name__
            for linter_class in dlint.linters.REGISTRY
        ]

        assert len(class_names) == len(set(class_names))

    def test_builtin_registry_messages_match_their_code(self):
        for linter_class in dlint.linters.REGISTRY:
            assert linter_class._error_tmpl.startswith(
                linter_class._code + ' '
            )

    def test_registry_identity_is_the_code(self):
        linter_registry = registry.LinterRegistry()
        linter_registry.register(ValidLinter)

        assert linter_registry.get_linter_class('DUO900') is ValidLinter
        assert ValidLinter in linter_registry
        assert linter_registry.get_codes() == ('DUO900',)

    def test_register_rejects_duplicate_code(self):
        linter_registry = registry.LinterRegistry()
        linter_registry.register(ValidLinter)

        with self.assertRaises(registry.LinterRegistryError):
            linter_registry.register(DuplicateCodeLinter)

    def test_register_rejects_duplicate_class_name(self):
        linter_registry = registry.LinterRegistry()
        linter_registry.register(ValidLinter)

        with self.assertRaises(registry.LinterRegistryError):
            linter_registry.register(DuplicateClassNameLinter)

    def test_register_rejects_invalid_code_prefix(self):
        linter_registry = registry.LinterRegistry()

        with self.assertRaises(registry.LinterRegistryError):
            linter_registry.register(InvalidCodeLinter)

    def test_register_rejects_misclassified_message(self):
        linter_registry = registry.LinterRegistry()

        with self.assertRaises(registry.LinterRegistryError):
            linter_registry.register(MisclassifiedMessageLinter)

    def test_register_rejects_abstract_linter(self):
        linter_registry = registry.LinterRegistry()

        with self.assertRaises(registry.LinterRegistryError):
            linter_registry.register(
                dlint.linters.helpers.BadBuiltinUseLinter
            )

    def test_build_registry_fails_closed_on_duplicate(self):
        with self.assertRaises(registry.LinterRegistryError):
            registry.build_registry([ValidLinter, DuplicateCodeLinter])

    def test_registered_linter_still_hits_on_fixed_ast_fixture(self):
        python_node = self.get_ast_node(
            """
            exec('print("TEST")')
            """
        )

        linter = dlint.linters.BadExecUseLinter()
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            base.Flake8Result(
                lineno=2,
                col_offset=0,
                message=dlint.linters.BadExecUseLinter._error_tmpl
            )
        ]

        assert result == expected
        assert result[0].message.startswith(
            dlint.linters.BadExecUseLinter._code + ' '
        )

    def test_registry_linter_hits_on_fixed_ast_fixture(self):
        python_node = self.get_ast_node(
            """
            valid_name
            """
        )

        linter_registry = registry.build_registry([ValidLinter])
        linter = linter_registry.get_linter_class('DUO900')()
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            base.Flake8Result(
                lineno=2,
                col_offset=0,
                message='DUO900 valid test linter'
            )
        ]

        assert result == expected


if __name__ == "__main__":
    unittest.main()
