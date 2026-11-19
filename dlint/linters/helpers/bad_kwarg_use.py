#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import abc
import ast
import itertools

from .. import base
from ... import tree
from ... import util


class BadKwargUseLinter(base.BaseLinter, util.ABC):
    """This abstract base class provides an simple interface for creating new
    lint rules that block bad kwarg use.
    """

    def __init__(self, *args, **kwargs):
        self.minimized_bad_kwarg_func = None
        self._current_call = None

        module_path_grouped = [
            (k, list(v))
            for k, v in itertools.groupby(
                sorted(self.kwargs, key=lambda k: k["module_path"]),
                key=lambda k: k["module_path"]
            )
        ]

        def predicate_matches(kwarg, node):
            return self._predicate_matches(kwarg, node)

        def minimized_illegal_module_imported(module_path, node):
            return any(
                self.module_imported(
                    module_path,
                    kwarg["module_path"],
                    node
                )
                and predicate_matches(kwarg, node)
                for illegal_module_path, kwargs in module_path_grouped
                for kwarg in kwargs
            )

        kwarg_predicate_grouped = [
            (k, list(v))
            for k, v in itertools.groupby(
                sorted(self.kwargs, key=lambda k: (k["kwarg_name"], id(k["predicate"]))),
                key=lambda k: (k["kwarg_name"], id(k["predicate"]))
            )
        ]

        def minimized_kwarg_predicate(module_path, node):
            return any(
                self.module_imported(
                    module_path,
                    kwarg["module_path"],
                    node
                )
                and predicate_matches(kwarg, node)
                for kwarg_predicate_tuple, kwargs in kwarg_predicate_grouped
                for kwarg in kwargs
            )

        # Minimize kwarg checks by grouping similar rules
        if (len(kwarg_predicate_grouped) < len(self.kwargs)
                and len(module_path_grouped) == len(self.kwargs)):
            self.minimized_bad_kwarg_func = minimized_kwarg_predicate
        else:
            self.minimized_bad_kwarg_func = minimized_illegal_module_imported

        super(BadKwargUseLinter, self).__init__(*args, **kwargs)

    @property
    @abc.abstractmethod
    def kwargs(self):
        """Subclasses must implement this property to return a list that
        looks like:

            [
                {
                    "module_path": "mod1.mod2.name1",
                    "kwarg_name": "kwarg1",
                    "predicate": <function>,
                },
            ]

        Which would represent 'mod1.mod2.name1(kwarg1=...)' where 'predicate'
        is a function that takes the Call object and a kwarg name and returns
        True|False.
        """

    def visit_Call(self, node):
        self.generic_visit(node)

        self._current_call = node

        func_origin = self._resolve_func(node)

        if func_origin is None or func_origin.state != tree.dataflow.STATE_KNOWN:
            # Unknown dynamic call, e.g. get_func()(...): retain an explicit
            # state instead of guessing the callee and risking a false report.
            return

        if func_origin.module_path is None:
            return

        bad_kwarg = self.minimized_bad_kwarg_func(func_origin.module_path, node)

        if bad_kwarg:
            self._append_kwarg_result(node, func_origin)

    def _append_kwarg_result(self, node, func_origin):
        # Combine the sink path with every tracked keyword value path so the
        # evidence shows both the dangerous call and the value that reached it.
        paths = [tree.dataflow.format_evidence(func_origin)]

        resolved_call = tree.dataflow.ResolvedCall(node, self.resolver)

        for keyword in resolved_call.keywords:
            if keyword.arg is None:
                continue

            kwarg_origin = self.resolver.resolve(keyword.value)
            paths.append(tree.dataflow.format_evidence(kwarg_origin))

        self.results.append(
            base.Flake8Result(
                lineno=node.lineno,
                col_offset=node.col_offset,
                message=self._error_tmpl
            )
        )
        self.evidence.append(paths)

    def _resolve_func(self, node):
        if not isinstance(node.func, (ast.Attribute, ast.Name)):
            return None

        return self.resolver.resolve(node.func)

    def _predicate_matches(self, kwarg, node):
        kwarg_name = kwarg["kwarg_name"]

        origin = tree.kwarg_origin(node, kwarg_name, self.resolver)
        predicate = kwarg["predicate"]

        if origin is None:
            # No value reached the call through a tracked path; only a
            # not-present style predicate can match in this case.
            return predicate(node, kwarg_name)

        if predicate is tree.kwarg_not_present:
            # An unpacked/dynamic container might still carry the keyword, so
            # keep the explicit state and stay on the safe side for rules
            # that require the defense to be present.
            return False

        # An explicit safe value or an unresolvable dynamic source keeps the
        # rule quiet even though the keyword is syntactically present.
        if self._inline_match_is_safe(kwarg, node, origin):
            return False

        if origin.state == tree.dataflow.STATE_DYNAMIC:
            return False

        # First run the original inline predicate so existing behavior for
        # literals written directly at the call site is unchanged.
        if predicate(node, kwarg_name):
            return True

        return self._origin_predicate_matches(kwarg, origin)

    def _inline_match_is_safe(self, kwarg, node, origin):
        """An explicit literal False/None at the call site is a deliberate
        safe value for presence-style rules and must not be reported even
        though the keyword technically exists.
        """
        if kwarg["predicate"] is not tree.kwarg_present:
            return False

        for keyword in node.keywords:
            if keyword.arg != kwarg["kwarg_name"]:
                continue

            if self._node_is_false_literal(keyword.value):
                return True

        return False

    @staticmethod
    def _node_is_false_literal(node):
        if hasattr(ast, "Constant") and isinstance(node, ast.Constant):
            return node.value is False

        if hasattr(ast, "NameConstant") and isinstance(node, ast.NameConstant):
            return node.value is False

        return False

    def _origin_predicate_matches(self, kwarg, origin):
        predicate = kwarg["predicate"]

        if predicate is tree.kwarg_present:
            # A dynamic/unknown source cannot be proven dangerous, so retain
            # the explicit state and stay silent to avoid false reports.
            if origin.state != tree.dataflow.STATE_KNOWN:
                return False

            if self._origin_is_constant(origin, False):
                return False

            return True

        if predicate in (tree.kwarg_false, tree.kwarg_true, tree.kwarg_none):
            return self._origin_is_constant(
                origin,
                {
                    tree.kwarg_false: False,
                    tree.kwarg_true: True,
                    tree.kwarg_none: None,
                }[predicate]
            )

        if predicate in (tree.kwarg_module_path, tree.kwarg_module_path_call):
            return (
                origin.state == tree.dataflow.STATE_KNOWN
                and origin.module_path is not None
                and self.module_imported(
                    origin.module_path,
                    kwarg["module_path"],
                    self._current_call
                )
            )

        # Custom predicates built on functools.partial (kwarg_str and
        # kwarg_module_path variants) are unwrapped and evaluated against the
        # resolved origin. Unknown predicates stay silent to avoid false
        # reports on clean code.
        if tree.kwarg_predicate_origin(
            self._current_call,
            kwarg["kwarg_name"],
            predicate,
            kwarg["module_path"],
            self.namespace,
            self.resolver,
            origin=origin
        ):
            return True

        # Closure-based predicates (e.g. urllib3/onelogin rules combining
        # several partials via kwarg_any) cannot be unwrapped. Re-run them
        # against a ResolvedCall whose keywords present the resolved source
        # nodes inline, so alias/attribute tracking stays on one path.
        if origin.state != tree.dataflow.STATE_KNOWN:
            return False

        resolved_call = tree.dataflow.ResolvedCall(
            self._current_call, self.resolver
        )
        materialized = self._materialize_resolved_keywords(resolved_call)

        try:
            local_imports = self.resolver.local_imports_for(self._current_call)
            with tree.call_override(materialized, local_imports):
                return predicate(self._current_call, kwarg["kwarg_name"])
        except TypeError:
            return False

    def _materialize_resolved_keywords(self, resolved_call):
        """Build a lightweight call-like object whose keywords carry the
        resolved source node of each value, letting legacy predicates see
        aliased and unpacked values as if written inline.
        """
        materialized = ast.Call(
            func=resolved_call.call.func,
            args=list(resolved_call.call.args),
            keywords=[]
        )

        for keyword in resolved_call.keywords:
            if isinstance(keyword, tree.dataflow._VirtualKeyword):
                source = keyword.value
            else:
                origin = self.resolver.resolve(keyword.value)
                source = (
                    self._terminal_value_node(keyword.value, origin)
                    if origin.state == tree.dataflow.STATE_KNOWN
                    else keyword.value
                )
            materialized.keywords.append(ast.keyword(arg=keyword.arg, value=source))

        return materialized

    def _terminal_value_node(self, node, origin):
        """Return the most-derived expression node backing a known origin.
        For 'c = ssl.CERT_NONE' that is the Attribute 'ssl.CERT_NONE', not
        the terminal import Name 'ssl'.
        """
        current = node

        while isinstance(current, ast.Name):
            assignment = self.resolver._nearest_assignment(current)

            if assignment is None:
                break

            current = assignment.value

        return current if current is not None else origin.source

    @staticmethod
    def _origin_is_constant(origin, expected):
        source = origin.source

        if hasattr(ast, "Constant") and isinstance(source, ast.Constant):
            return source.value == expected

        if hasattr(ast, "NameConstant") and isinstance(source, ast.NameConstant):
            return source.value == expected

        return False
