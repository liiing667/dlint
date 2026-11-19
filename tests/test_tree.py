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

import pytest

import dlint


class TestTree(unittest.TestCase):

    def test_decorator_name_unknown_type(self):
        unknown_type = None

        with pytest.raises(TypeError):
            dlint.tree.decorator_name(unknown_type)

    def test_sink_node_returns_call_func(self):
        node = ast.parse("foo.bar(x)").body[0].value

        assert dlint.tree.sink_node(node) is node.func

    def test_sink_node_returns_other_node_unchanged(self):
        node = ast.parse("foo.bar").body[0].value

        assert dlint.tree.sink_node(node) is node

    def test_node_has_location(self):
        located = ast.parse("foo").body[0].value
        synthetic = ast.Name(id='foo')

        assert dlint.tree.node_has_location(located)
        assert not dlint.tree.node_has_location(synthetic)

    def test_node_start_position_falls_back_to_child(self):
        module = ast.parse(textwrap.dedent("""
            x = (
                foo.bar(
                    x
                )
            )
        """))
        call = module.body[0].value

        assert dlint.tree.node_start_position(call) == (3, 4)

        synthetic = ast.Name(id='foo')
        assert dlint.tree.node_start_position(synthetic) is None

    def test_decorator_start_position(self):
        module = ast.parse(textwrap.dedent("""
            @defer.inlineCallbacks
            def func():
                pass
        """))
        function = module.body[0]

        assert dlint.tree.decorator_start_position(
            function.decorator_list[0]
        ) == (2, 1)

        assert dlint.tree.decorator_start_position(ast.Name(id='defer')) is None


if __name__ == "__main__":
    unittest.main()
