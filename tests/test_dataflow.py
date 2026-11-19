#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast
import unittest

import dlint
from dlint import dataflow


class ResolverTest(dlint.test.base.BaseTest):
    def _resolver(self, source):
        node = self.get_ast_node(source)
        namespace = dlint.namespace.Namespace.from_module_node(node)
        return dataflow.Resolver(node, namespace), node

    def test_parent_chain_is_annotated(self):
        resolver, node = self._resolver(
            """
            import foo
            foo.bar()
            """
        )

        attribute = next(
            inner for inner in ast.walk(node)
            if isinstance(inner, ast.Attribute)
        )

        assert dataflow.get_parent(attribute) is not None
        assert dataflow.enclosing_scope(attribute) is node

    def test_direct_import_origin(self):
        resolver, node = self._resolver(
            """
            import foo
            foo.bar()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_KNOWN
        assert origin.module_path == "foo.bar"

    def test_import_alias_origin(self):
        resolver, node = self._resolver(
            """
            import foo.bar as baz
            baz.qux()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_KNOWN
        assert origin.module_path == "foo.bar.qux"

    def test_from_import_alias_origin(self):
        resolver, node = self._resolver(
            """
            from foo import bar as baz
            baz.qux()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_KNOWN
        assert origin.module_path == "foo.bar.qux"

    def test_assignment_alias_origin(self):
        resolver, node = self._resolver(
            """
            import subprocess
            sp = subprocess.Popen
            sp("ls")
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_KNOWN
        assert origin.module_path == "subprocess.Popen"
        assert any(record.kind == "assignment" for record in origin.evidence)

    def test_nested_attribute_origin(self):
        resolver, node = self._resolver(
            """
            import a
            a.b.c.d()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.module_path == "a.b.c.d"

    def test_unknown_dynamic_call_is_explicit(self):
        resolver, node = self._resolver(
            """
            factory = make_factory()
            factory("x")
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_DYNAMIC
        assert origin.module_path is None

    def test_wildcard_import_is_explicitly_unknown(self):
        resolver, node = self._resolver(
            """
            from foo import *
            bar()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_UNKNOWN
        assert origin.module_path is None
        assert any(record.kind == "wildcard-import" for record in origin.evidence)

    def test_parameter_reference_is_dynamic(self):
        resolver, node = self._resolver(
            """
            def run(value):
                return value.run()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func.value)

        assert origin.state == dataflow.STATE_DYNAMIC

    def test_subscript_value_is_dynamic(self):
        resolver, node = self._resolver(
            """
            config = {}
            config["shell"]
            """
        )

        subscript = next(
            inner for inner in ast.walk(node) if isinstance(inner, ast.Subscript)
        )
        origin = resolver.resolve(subscript)

        assert origin.state == dataflow.STATE_DYNAMIC

    def test_scope_rebinding_does_not_leak(self):
        resolver, node = self._resolver(
            """
            import bar

            def outer():
                obj = bar.Qux()

                def inner():
                    obj = bar.Baz()

                return obj
            """
        )

        names = [
            inner for inner in ast.walk(node)
            if isinstance(inner, ast.Name)
            and inner.id == "obj"
            and isinstance(inner.ctx, ast.Load)
        ]

        # The outer-scope reference resolves to bar.Qux, not the inner rebind.
        outer_load = names[-1]
        origin = resolver.resolve(outer_load)

        assert origin.module_path == "bar.Qux"

    def test_resolved_call_flattens_unpacked_dict(self):
        resolver, node = self._resolver(
            """
            import foo
            options = {"shell": True}
            foo.bar(**options)
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        resolved = resolver.resolve_call(call)

        assert [keyword.arg for keyword in resolved.keywords] == ["shell"]

    def test_dynamic_unpack_keeps_unknown_state(self):
        resolver, node = self._resolver(
            """
            import foo
            def run(options):
                foo.bar(**options)
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        resolved = resolver.resolve_call(call)
        keyword = resolved.keywords[0]
        origin = resolver.resolve(keyword.value)

        assert origin.state == dataflow.STATE_DYNAMIC

    def test_evidence_format_contains_locations(self):
        resolver, node = self._resolver(
            """
            import subprocess
            sp = subprocess.Popen
            sp("ls")
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)
        rendered = dataflow.format_evidence(origin)

        assert "assignment" in rendered
        assert "subprocess.Popen" in rendered
        assert "[" in rendered and "]" in rendered

    def test_self_referential_alias_does_not_recurse(self):
        resolver, node = self._resolver(
            """
            a = a.b
            a.c()
            """
        )

        call = next(inner for inner in ast.walk(node) if isinstance(inner, ast.Call))
        origin = resolver.resolve(call.func)

        assert origin.state == dataflow.STATE_DYNAMIC


if __name__ == "__main__":
    unittest.main()
