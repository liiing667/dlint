#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import unittest

import ast
import pytest

import dlint


class TestNamespace(dlint.test.base.BaseTest):

    def test_basic_import(self):
        python_node = self.get_ast_node(
            """
            import foo
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = namespace.name_imported("foo")
        expected = True

        assert result == expected

    def test_basic_from_import(self):
        python_node = self.get_ast_node(
            """
            from foo import bar
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = namespace.name_imported("bar")
        expected = True

        assert result == expected

    def test_basic_as_import(self):
        python_node = self.get_ast_node(
            """
            import foo as bar
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = namespace.name_imported("bar")
        expected = True

        assert result == expected

    def test_basic_as_from_import(self):
        python_node = self.get_ast_node(
            """
            from foo import bar as baz
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = namespace.name_imported("baz")
        expected = True

        assert result == expected

    def test_as_import_mismatch(self):
        python_node = self.get_ast_node(
            """
            import foo as bar
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = namespace.name_imported("foo")
        expected = False

        assert result == expected

    def test_as_from_import_mismatch(self):
        python_node = self.get_ast_node(
            """
            from foo import bar as baz
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = (
            namespace.name_imported("foo")
            or namespace.name_imported("bar")
        )
        expected = False

        assert result == expected

    def test_from_module_node_unknown_type(self):
        unknown_type = None

        with pytest.raises(TypeError):
            dlint.namespace.Namespace.from_module_node(unknown_type)

    def test_function_scope_import_visible_inside(self):
        python_node = self.get_ast_node(
            """
            def func():
                import foo
                foo.bar()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'bar'
        )

        result = namespace.illegal_module_imported_in_scope(
            call_node,
            "foo",
            "foo"
        )

        assert result is True

    def test_function_scope_import_hidden_outside(self):
        python_node = self.get_ast_node(
            """
            def func():
                import foo

            foo.bar()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'bar'
        )

        result = namespace.illegal_module_imported_in_scope(
            call_node,
            "foo",
            "foo"
        )

        assert result is False

    def test_conditional_and_try_scope_imports(self):
        python_node = self.get_ast_node(
            """
            if True:
                import foo

            try:
                import baz
            except ImportError:
                pass
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        assert namespace.name_imported("foo")
        assert namespace.name_imported("baz")

    def test_relative_import_resolution_is_uncertain(self):
        python_node = self.get_ast_node(
            """
            from . import foo

            foo.bar()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'bar'
        )

        is_illegal, reason = namespace.illegal_module_imported_with_reason(
            "foo",
            "foo",
            call_node
        )

        assert is_illegal is True
        assert reason is not None
        assert "relative import" in reason

    def test_conflicting_binding_resolution_is_uncertain(self):
        python_node = self.get_ast_node(
            """
            import safe as foo
            import foo

            foo.bar()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'bar'
        )

        is_illegal, reason = namespace.illegal_module_imported_with_reason(
            "foo",
            "foo",
            call_node
        )

        assert is_illegal is True
        assert reason is not None
        assert "conflicting import bindings" in reason

    def test_unknown_binding_not_imported(self):
        python_node = self.get_ast_node(
            """
            foo = None

            foo.bar()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'bar'
        )

        is_illegal, reason = namespace.illegal_module_imported_with_reason(
            "foo",
            "foo",
            call_node
        )

        assert is_illegal is False
        assert reason is None

    def test_wildcard_import_canonicalization(self):
        python_node = self.get_ast_node(
            """
            from pkg import *

            bar.baz()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'baz'
        )

        canonical, reason = namespace.resolve_module_path(
            call_node,
            "bar"
        )

        assert canonical == ("pkg", "bar")
        assert reason is None

    def test_alias_chain_canonicalization(self):
        python_node = self.get_ast_node(
            """
            import foo.bar as baz

            baz.qux()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'qux'
        )

        canonical, reason = namespace.resolve_module_path(
            call_node,
            "baz"
        )

        assert canonical == ("foo", "bar")
        assert reason is None

    def test_dotted_import_head_name_not_duplicated(self):
        python_node = self.get_ast_node(
            """
            import foo.bar.baz

            foo.bar.baz.qux()
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        call_node = next(
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Attribute) and node.attr == 'qux'
        )

        canonical, reason = namespace.resolve_module_path(
            call_node,
            "foo.bar.baz"
        )

        assert canonical == ("foo", "bar", "baz")
        assert reason is None


if __name__ == "__main__":
    unittest.main()
