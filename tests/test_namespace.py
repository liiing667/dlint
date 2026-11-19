#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import unittest

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

    def test_dotted_import_binds_top_level_name(self):
        python_node = self.get_ast_node(
            """
            import foo.bar
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        assert namespace.name_imported("foo") is True
        assert namespace.name_imported("unrelated") is False

    def test_illegal_module_imported_nested_attribute(self):
        python_node = self.get_ast_node(
            """
            import foo
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        # A deeper attribute path on an illegal origin is still illegal.
        result = namespace.illegal_module_imported(
            "foo.bar.baz.qux",
            "foo.bar"
        )

        assert result is True

    def test_illegal_module_imported_lexical_sibling_is_safe(self):
        python_node = self.get_ast_node(
            """
            import foo
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        # Prefix matching must be component based, not lexical.
        result = namespace.illegal_module_imported(
            "foo.barbar",
            "foo.bar"
        )

        assert result is False

    def test_illegal_module_imported_wildcard_resolved_path(self):
        python_node = self.get_ast_node(
            """
            from m1.m2 import *
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        # Fully resolved wildcard paths, including nested attributes on the
        # illegal origin, are recognized.
        result = namespace.illegal_module_imported(
            "m1.m2.m3.m4.bad_attribute",
            "m1.m2.m3.m4"
        )

        assert result is True

    def test_illegal_module_imported_wildcard_relative_path(self):
        python_node = self.get_ast_node(
            """
            from m1.m2.m3 import *
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        # The legacy relative-path calling convention still canonicalizes.
        result = namespace.illegal_module_imported(
            "m4.bad_attribute",
            "m1.m2.m3.m4.bad_attribute"
        )

        assert result is True

    def test_illegal_module_imported_wildcard_safe_name(self):
        python_node = self.get_ast_node(
            """
            from m1.m2 import *
            """
        )

        namespace = dlint.namespace.Namespace.from_module_node(python_node)

        result = namespace.illegal_module_imported(
            "m1.m2.innocent.thing",
            "m1.m2.m3.m4"
        )

        assert result is False

    def test_from_module_node_unknown_type(self):
        unknown_type = None

        with pytest.raises(TypeError):
            dlint.namespace.Namespace.from_module_node(unknown_type)


if __name__ == "__main__":
    unittest.main()
