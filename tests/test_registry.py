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
from dlint import registry


def make_linter_class(name, code, message=None, base=None):
    namespace = {
        '_code': code,
        '_error_tmpl': message if message is not None else code + ' message',
    }
    return type(str(name), (base or dlint.linters.base.BaseLinter,), namespace)


def make_abstract_linter_class(name, code):
    class AbstractLinter(dlint.linters.helpers.bad_builtin_use.BadBuiltinUseLinter):
        _code = code
        _error_tmpl = code + ' message'

    AbstractLinter.__name__ = str(name)
    return AbstractLinter


class TestLinterRegistry(unittest.TestCase):
    def test_builtin_registry_contains_all_linters(self):
        result = dlint.linters.REGISTRY

        assert len(result) == len(dlint.linters.ALL)
        assert result.all() == dlint.linters.ALL

    def test_builtin_codes_are_unique(self):
        codes = [linter._code for linter in dlint.linters.ALL]

        assert len(codes) == len(set(codes))
        assert dlint.linters.REGISTRY.codes() == tuple(sorted(codes))

    def test_builtin_message_prefix_matches_code(self):
        for linter_class in dlint.linters.ALL:
            assert linter_class._error_tmpl.startswith(linter_class._code + ' ')

    def test_builtin_class_names_are_unique(self):
        names = [linter.__name__ for linter in dlint.linters.ALL]

        assert len(names) == len(set(names))

    def test_register_and_lookup(self):
        linter_class = make_linter_class('DlintTestLinter', 'DUO901')

        result = registry.LinterRegistry()
        result.register(linter_class)

        assert result.get_by_code('DUO901') is linter_class
        assert result.get_by_name('DlintTestLinter') is linter_class
        assert linter_class in result
        assert 'DUO901' in result
        assert len(result) == 1

    def test_register_same_class_twice_is_noop(self):
        linter_class = make_linter_class('DlintTestLinter', 'DUO901')

        result = registry.LinterRegistry()
        result.register(linter_class)
        result.register(linter_class)

        assert result.all() == (linter_class,)
        assert len(result) == 1

    def test_duplicate_code_conflict_fails_closed(self):
        first = make_linter_class('DlintFirstLinter', 'DUO901')
        second = make_linter_class('DlintSecondLinter', 'DUO901')

        result = registry.LinterRegistry()
        result.register(first)

        with self.assertRaises(registry.RegistryError):
            result.register(second)

        assert result.all() == (first,)

    def test_duplicate_class_name_conflict_fails_closed(self):
        first = make_linter_class('DlintSameNameLinter', 'DUO901')
        second = make_linter_class('DlintSameNameLinter', 'DUO902')

        result = registry.LinterRegistry()
        result.register(first)

        with self.assertRaises(registry.RegistryError):
            result.register(second)

        assert result.all() == (first,)

    def test_subclass_with_same_code_cannot_mask_parent(self):
        parent = make_linter_class('DlintParentLinter', 'DUO901')
        child = make_linter_class(
            'DlintChildLinter', 'DUO901', base=parent
        )

        result = registry.LinterRegistry()
        result.register(parent)

        with self.assertRaises(registry.RegistryError):
            result.register(child)

        assert result.get_by_code('DUO901') is parent

    def test_invalid_code_prefix_fails_closed(self):
        linter_class = make_linter_class('DlintBadPrefixLinter', 'XXX901')

        result = registry.LinterRegistry()

        with self.assertRaises(registry.RegistryError):
            result.register(linter_class)

        assert len(result) == 0

    def test_malformed_code_fails_closed(self):
        linter_class = make_linter_class('DlintMalformedLinter', 'DUO12')

        result = registry.LinterRegistry()

        with self.assertRaises(registry.RegistryError):
            result.register(linter_class)

    def test_message_prefix_mismatch_fails_closed(self):
        linter_class = make_linter_class(
            'DlintMismatchLinter', 'DUO901', message='DUO902 different code'
        )

        result = registry.LinterRegistry()

        with self.assertRaises(registry.RegistryError):
            result.register(linter_class)

    def test_abstract_linter_fails_closed(self):
        linter_class = make_abstract_linter_class(
            'DlintAbstractLinter', 'DUO901'
        )

        result = registry.LinterRegistry()

        with self.assertRaises(registry.RegistryError):
            result.register(linter_class)

    def test_non_class_fails_closed(self):
        result = registry.LinterRegistry()

        with self.assertRaises(registry.RegistryError):
            result.register('not-a-class')

    def test_build_registry(self):
        first = make_linter_class('DlintFirstLinter', 'DUO901')
        second = make_linter_class('DlintSecondLinter', 'DUO902')

        result = registry.build_registry([first, second])

        assert result.all() == (first, second)

    def test_registry_fixture_records_ast_hits(self):
        python_node = ast.parse(
            textwrap.dedent(
                """
                exec('print "TEST"')
                eval('1 + 1')
                """
            )
        )

        registered = dlint.linters.REGISTRY
        linter_instances = [linter_class() for linter_class in registered.all()]

        multi_visitor = dlint.multi.MultiNodeVisitor(linter_instances)
        multi_visitor.visit(python_node)

        hits = {}
        for linter_instance in linter_instances:
            for _result in linter_instance.get_results():
                hits.setdefault(
                    type(linter_instance)._code,
                    type(linter_instance).__name__
                )

        assert hits == {
            'DUO105': 'BadExecUseLinter',
            'DUO104': 'BadEvalUseLinter',
        }
        assert registered.get_by_code('DUO105') is dlint.linters.BadExecUseLinter
        assert registered.get_by_code('DUO104') is dlint.linters.BadEvalUseLinter


if __name__ == "__main__":
    unittest.main()
