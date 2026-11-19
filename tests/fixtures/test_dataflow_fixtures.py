#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import os
import unittest

import ast

import dlint


FIXTURE_DIR = os.path.dirname(__file__)


def read_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as fd:
        return fd.read()


class DataflowAliasFixtureTest(dlint.test.base.BaseTest):
    def test_alias_hits(self):
        python_node = self.get_ast_node(read_fixture("dataflow_alias_hits.py"))

        linter = dlint.linters.BadSubprocessUseLinter()
        linter.visit(python_node)

        result = linter.get_results()

        # Each aliased sink must be hit at its call location.
        assert [r.lineno for r in result] == [9, 16, 21]

        evidence = linter.get_evidence()
        assert len(evidence) == len(result)

        # Every finding carries a data-flow path ending at the resolved sink.
        for paths in evidence:
            assert paths
            assert any(path.endswith("subprocess.Popen") for path in paths)

        # The assignment hop that created the alias is visible evidence.
        assert "assignment" in " | ".join(evidence[0])

    def test_module_constant_alias_hit(self):
        python_node = self.get_ast_node(read_fixture("dataflow_alias_hits.py"))

        linter = dlint.linters.BadUrllib3KwargUseLinter()
        linter.visit(python_node)

        result = linter.get_results()

        assert len(result) == 1
        assert result[0].lineno == 29
        combined = " | ".join(linter.get_evidence()[0])
        assert "ssl.CERT_NONE" in combined
        assert "urllib3.PoolManager" in combined


class DataflowKwargFixtureTest(dlint.test.base.BaseTest):
    def test_kwarg_hits(self):
        python_node = self.get_ast_node(read_fixture("dataflow_kwarg_hits.py"))

        linter = dlint.linters.BadSubprocessUseLinter()
        linter.visit(python_node)

        result = linter.get_results()

        assert [r.lineno for r in result] == [8, 13]
        assert all(linter.get_evidence())

    def test_aliased_verify_false_hit(self):
        python_node = self.get_ast_node(read_fixture("dataflow_kwarg_hits.py"))

        linter = dlint.linters.BadRequestsUseLinter()
        linter.visit(python_node)

        result = linter.get_results()

        assert len(result) == 1
        assert result[0].lineno == 20


class DataflowDynamicUnknownFixtureTest(dlint.test.base.BaseTest):
    def test_unknown_dynamic_calls_are_silent(self):
        python_node = self.get_ast_node(read_fixture("dataflow_dynamic_unknown.py"))

        linter = dlint.linters.BadSubprocessUseLinter()
        linter.visit(python_node)

        # Only the statically known subprocess.Popen calls are eligible;
        # none of the dynamic/unknown forms match a known sink.
        assert linter.get_results() == []

    def test_unknown_origins_keep_explicit_state(self):
        python_node = self.get_ast_node(read_fixture("dataflow_dynamic_unknown.py"))

        namespace = dlint.namespace.Namespace.from_module_node(python_node)
        resolver = dlint.dataflow.Resolver(python_node, namespace)

        states = []

        for node in ast.walk(python_node):
            if not isinstance(node, ast.Call):
                continue

            origin = resolver.resolve(node.func)
            states.append(origin.state)

        # The dynamic factory call is retained as an explicit dynamic state.
        assert dlint.dataflow.STATE_DYNAMIC in states


class DataflowCleanFixtureTest(dlint.test.base.BaseTest):
    def test_clean_code_has_no_findings(self):
        python_node = self.get_ast_node(read_fixture("dataflow_clean.py"))

        linters = [
            dlint.linters.BadSubprocessUseLinter(),
            dlint.linters.BadRequestsUseLinter(),
            dlint.linters.BadUrllib3KwargUseLinter(),
        ]

        for linter in linters:
            linter.visit(python_node)
            assert linter.get_results() == []


if __name__ == "__main__":
    unittest.main()
