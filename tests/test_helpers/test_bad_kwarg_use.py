#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import unittest

import dlint


def get_bad_kwarg_use_implementation(kwargs):
    class Cls(dlint.linters.helpers.bad_kwarg_use.BadKwargUseLinter):
        _code = 'DUOXXX'
        _error_tmpl = 'DUOXXX error message'

        @property
        def kwargs(self):
            return kwargs

    return Cls()


class TestBadKwargUse(dlint.test.base.BaseTest):

    def test_empty(self):
        python_node = self.get_ast_node(
            """
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo",
                    "kwarg_name": "bar",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_empty_kwargs(self):
        python_node = self.get_ast_node(
            """
            import foo
            """
        )

        linter = get_bad_kwarg_use_implementation([])
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_present_true(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_present_false(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_not_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_present_true_missing(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar()
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_present_false_missing(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar()
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_not_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_same_name_different_kwarg(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg2="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg1",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_different_name_same_kwarg(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar2(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar1",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_multi(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg1="test")
            foo.baz(kwarg2="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg1",
                    "predicate": dlint.tree.kwarg_present,
                },
                {
                    "module_path": "foo.baz",
                    "kwarg_name": "kwarg2",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            ),
            dlint.linters.base.Flake8Result(
                lineno=5,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_nested_calls(self):
        python_node = self.get_ast_node(
            """
            from foo import Bar

            Bar.baz(kwarg="test")()()
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.Bar.baz",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_subscript_calls(self):
        python_node = self.get_ast_node(
            """
            from foo import Bar

            Bar.baz(kwarg="test")["qux"]()
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.Bar.baz",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_primitive_true(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg=True)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_true,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_primitive_false(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg=False)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_false,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_primitive_none(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg=None)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_none,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_present_module_path(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar.baz(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar.baz",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_present_different_module_path(self):
        python_node = self.get_ast_node(
            """
            import foo
            import boo

            boo.bar.baz(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar.baz",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_present_from_module_path(self):
        python_node = self.get_ast_node(
            """
            from foo import bar

            bar.baz(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar.baz",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=4,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_missing_module_path(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar.baz(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar.baz",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_not_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = []

        assert result == expected

    def test_kwargs_aliased_call_target(self):
        python_node = self.get_ast_node(
            """
            import foo

            bar = foo.bar
            bar(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=5,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected
        assert linter.get_evidence()

    def test_kwargs_aliased_keyword_value(self):
        python_node = self.get_ast_node(
            """
            import foo

            value = True
            foo.bar(kwarg=value)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=5,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_unpacked_dictionary(self):
        python_node = self.get_ast_node(
            """
            import foo

            options = {"kwarg": "test"}
            foo.bar(**options)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        result = linter.get_results()
        expected = [
            dlint.linters.base.Flake8Result(
                lineno=5,
                col_offset=0,
                message=linter._error_tmpl
            )
        ]

        assert result == expected

    def test_kwargs_dynamic_value_is_silent(self):
        python_node = self.get_ast_node(
            """
            import foo

            def run(value):
                foo.bar(kwarg=value)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        assert linter.get_results() == []

    def test_kwargs_indirect_dynamic_call_is_silent(self):
        python_node = self.get_ast_node(
            """
            import foo

            factory = make_factory()
            factory(kwarg="test")
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        assert linter.get_results() == []

    def test_kwargs_explicit_false_is_safe_for_present_rule(self):
        python_node = self.get_ast_node(
            """
            import foo

            foo.bar(kwarg=False)
            """
        )

        linter = get_bad_kwarg_use_implementation(
            [
                {
                    "module_path": "foo.bar",
                    "kwarg_name": "kwarg",
                    "predicate": dlint.tree.kwarg_present,
                },
            ]
        )
        linter.visit(python_node)

        assert linter.get_results() == []


if __name__ == "__main__":
    unittest.main()
