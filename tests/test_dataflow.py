#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import ast

import dlint
from dlint import dataflow
from dlint import parents


class TestDataflowResolver(dlint.test.base.BaseTest):

    def _resolver(self, source):
        python_node = self.get_ast_node(source)
        parents.attach_parents(python_node)
        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        return dataflow.DataflowResolver(python_node, namespace), python_node

    def _calls(self, python_node):
        return [
            node for node in ast.walk(python_node)
            if isinstance(node, ast.Call)
        ]

    def _name_calls(self, python_node, name):
        return [
            node for node in self._calls(python_node)
            if isinstance(node.func, ast.Name) and node.func.id == name
        ]

    def test_direct_import_resolves(self):
        resolver, node = self._resolver(
            """
            import foo

            foo.bar()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.bar'
        # The root name is already an import binding, so resolution starts
        # at the attribute access; no alias hop is present.
        assert [step.kind for step in origin.steps] == ['attribute']

    def test_from_import_alias_resolves(self):
        resolver, node = self._resolver(
            """
            from foo import bar as baz

            baz()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.bar'

    def test_variable_alias_resolves_with_evidence_path(self):
        resolver, node = self._resolver(
            """
            import foo

            runner = foo.bar
            runner()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.bar'
        # The evidence path walks the alias back to its originating import.
        assert [step.kind for step in origin.steps] == [
            'alias',
            'attribute',
        ]
        alias_step = origin.steps[0]
        assert alias_step.description == 'runner'
        assert alias_step.lineno == 4

    def test_chained_alias_resolves(self):
        resolver, node = self._resolver(
            """
            import foo

            first = foo
            second = first.bar
            second()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.bar'

    def test_nested_attribute_on_alias_resolves(self):
        resolver, node = self._resolver(
            """
            import foo

            obj = foo.bar
            obj.baz.qux()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.bar.baz.qux'

    def test_reassignment_tracks_latest_value(self):
        resolver, node = self._resolver(
            """
            import foo

            runner = foo.bar
            runner = foo.safe
            runner()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.safe'

    def test_local_assignment_shadows_imported_name(self):
        resolver, node = self._resolver(
            """
            import foo

            foo = other
            foo.bar()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        # The local rebinding shadows the import, so resolution must follow
        # the assignment rather than the now-shadowed import binding.
        assert origin.state == dataflow.UNKNOWN_ARGUMENT
        assert origin.module_path is None

    def test_local_scope_shadows_module_scope(self):
        resolver, node = self._resolver(
            """
            import foo

            runner = foo.bar

            def func():
                runner = foo.safe
                runner()
            """
        )

        call = [
            call for call in self._calls(node)
            if call.lineno == 8
        ][0]
        origin = resolver.resolve(call.func)

        assert origin.state == 'known'
        assert origin.module_path == 'foo.safe'

    def test_dynamic_getattr_is_explicit_unknown(self):
        resolver, node = self._resolver(
            """
            import foo

            runner = getattr(foo, 'bar')
            runner()
            """
        )

        origin = resolver.resolve(self._name_calls(node, 'runner')[0].func)

        assert origin.state == dataflow.UNKNOWN_DYNAMIC
        assert origin.module_path is None

    def test_subscript_dispatch_is_explicit_unknown(self):
        resolver, node = self._resolver(
            """
            import foo

            runner = foo['bar']
            runner()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == dataflow.UNKNOWN_DYNAMIC
        assert origin.module_path is None

    def test_function_argument_is_explicit_unknown(self):
        resolver, node = self._resolver(
            """
            def func(runner):
                runner()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == dataflow.UNKNOWN_ARGUMENT
        assert origin.module_path is None

    def test_tuple_unpacking_is_explicit_unknown(self):
        resolver, node = self._resolver(
            """
            import foo

            runner, other = foo.bar, foo.baz
            runner()
            """
        )

        origin = resolver.resolve(self._calls(node)[0].func)

        assert origin.state == dataflow.UNKNOWN_REASSIGNED
        assert origin.module_path is None

    def test_unknown_state_keeps_evidence_steps(self):
        resolver, node = self._resolver(
            """
            import foo

            runner = getattr(foo, 'bar')
            runner()
            """
        )

        origin = resolver.resolve(self._name_calls(node, 'runner')[0].func)

        # Even unknown results keep the alias hop so the rule can explain
        # where resolution stopped.
        assert origin.steps
        assert [step.kind for step in origin.steps] == [
            'alias',
            'dynamic',
        ]
        assert origin.steps[-1].kind == 'dynamic'

    def test_constructor_call_originates_from_callee_path(self):
        resolver, node = self._resolver(
            """
            import bar

            def func():
                obj = bar.Baz()
                obj
            """
        )

        name_node = [
            inner for inner in ast.walk(node)
            if isinstance(inner, ast.Name) and inner.id == 'obj'
            and inner.lineno == 5
        ][0]
        origin = resolver.resolve(name_node)

        assert origin.state == 'known'
        assert origin.module_path == 'bar.Baz'
        assert [step.kind for step in origin.steps] == [
            'alias',
            'call',
        ]


class TestParentChain(dlint.test.base.BaseTest):

    def test_attach_parents_sets_direct_parent(self):
        python_node = self.get_ast_node(
            """
            foo.bar()
            """
        )
        parents.attach_parents(python_node)

        call = python_node.body[0].value
        attribute = call.func

        assert parents.get_parent(attribute) is call
        assert parents.get_parent(call) is python_node.body[0]
        assert parents.get_parent(python_node) is None

    def test_iter_parents_walks_to_root(self):
        python_node = self.get_ast_node(
            """
            foo.bar()
            """
        )
        parents.attach_parents(python_node)

        name_node = python_node.body[0].value.func.value
        chain = list(parents.iter_parents(name_node))

        assert python_node in chain
        assert all(isinstance(node, ast.AST) for node in chain)

    def test_attach_parents_is_idempotent(self):
        python_node = self.get_ast_node(
            """
            foo.bar()
            """
        )
        parents.attach_parents(python_node)
        parents.attach_parents(python_node)

        call = python_node.body[0].value
        assert parents.get_parent(call) is python_node.body[0]

    def test_enclosing_scope(self):
        python_node = self.get_ast_node(
            """
            import foo

            def func():
                foo.bar()
            """
        )
        parents.attach_parents(python_node)

        call = python_node.body[1].body[0].value
        scope = parents.get_enclosing_scope(call)

        assert isinstance(scope, ast.FunctionDef)
        assert scope.name == 'func'


if __name__ == "__main__":
    import unittest
    unittest.main()
