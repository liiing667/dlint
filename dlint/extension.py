#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import importlib
import inspect
import pkgutil
import optparse
import sys

from flake8 import style_guide

import dlint
import dlint.limits

limits = dlint.limits


class Flake8Extension(object):
    name = dlint.__name__
    version = dlint.__version__
    options = None

    def __init__(self, tree, filename, budget=None):
        self.tree = tree
        self.filename = filename
        self.budget = budget or self.build_budget()
        self.incomplete = None

    @classmethod
    def add_options(cls, parser):
        try:
            parser.add_option(
                '--print-dlint-linters',
                action='store_true',
                help='Print Dlint linter information.',
                parse_from_config=False
            )
            parser.add_option(
                '--dlint-max-file-bytes',
                action='store',
                type='int',
                default=limits.DEFAULT_MAX_FILE_BYTES,
                help='Maximum source file size in bytes Dlint will scan.',
                parse_from_config=True
            )
            parser.add_option(
                '--dlint-max-ast-nodes',
                action='store',
                type='int',
                default=limits.DEFAULT_MAX_AST_NODES,
                help='Maximum number of AST nodes Dlint will visit per file.',
                parse_from_config=True
            )
            parser.add_option(
                '--dlint-max-results',
                action='store',
                type='int',
                default=limits.DEFAULT_MAX_RESULTS,
                help='Maximum number of results Dlint will report per file.',
                parse_from_config=True
            )
        except optparse.OptionConflictError:
            # Occurs during development when flake8 detects the dlint package
            # twice: once because it's been installed in editable mode, and
            # once from the local filesystem directory. We can safely nop here
            # since the option(s) have already been added.
            pass

    @classmethod
    def parse_options(cls, options):
        if options.print_dlint_linters:
            code_prefix_len = 7
            linters = cls.get_linter_classes()
            output_lines = [
                "{} {} {}".format(l._code, l.__name__, l._error_tmpl[code_prefix_len:])
                for l in sorted(linters, key=lambda li: li._code)
            ]
            print("\n".join(output_lines))
            EX_OK = 0
            sys.exit(EX_OK)

        cls.options = options
        cls.budget_limits = cls._budget_limits_from_options(options)

    @staticmethod
    def _budget_limits_from_options(options):
        return (
            getattr(options, 'dlint_max_file_bytes',
                    limits.DEFAULT_MAX_FILE_BYTES),
            getattr(options, 'dlint_max_ast_nodes',
                    limits.DEFAULT_MAX_AST_NODES),
            getattr(options, 'dlint_max_results',
                    limits.DEFAULT_MAX_RESULTS),
        )

    @classmethod
    def build_budget(cls):
        budget_limits = getattr(cls, 'budget_limits', None)
        if budget_limits is None:
            return limits.ResourceBudget()
        return limits.ResourceBudget(*budget_limits)

    def _mark_incomplete(self, exc):
        self.incomplete = limits.describe_failure(exc)

    def _enforce_budgets(self):
        """Enforce the shared file and AST budgets before running linters.

        On-disk files are re-read through the file budget so oversized or
        undecodable source is rejected early. Trees handed in directly,
        e.g. flake8 stdin processing, are charged against the AST budget.
        """
        if limits.is_real_file(self.filename):
            source = limits.read_source(self.filename, self.budget)
            self.tree = limits.parse_source(
                source, self.budget, self.filename
            )
        else:
            limits.count_ast_nodes(self.tree, self.budget)

    def _incomplete_result(self):
        return (
            1,
            0,
            limits.incomplete_message(self.incomplete),
            type(self)
        )

    @classmethod
    def get_plugin_linter_classes(cls):
        module_prefix = 'dlint_plugin_'
        class_prefix = 'Dlint'

        plugin_modules = [
            importlib.import_module(name)
            for finder, name, ispkg in pkgutil.iter_modules()
            if name.startswith(module_prefix)
        ]
        plugin_classes = [
            inner_cls
            for module in plugin_modules
            for name, inner_cls in inspect.getmembers(module, predicate=inspect.isclass)
            if name.startswith(class_prefix)
        ]

        return plugin_classes

    @classmethod
    def get_linter_classes(cls):
        linter_classes = dlint.linters.ALL + tuple(cls.get_plugin_linter_classes())

        if cls.options:
            engine = style_guide.DecisionEngine(cls.options)
            selected = style_guide.Decision.Selected
            linter_classes = tuple(
                linter_class for linter_class in linter_classes
                if engine.decision_for(linter_class._code) is selected
            )

        return linter_classes

    def run(self):
        try:
            self._enforce_budgets()
        except (limits.BudgetExceeded, limits.UnreadableSource) as exc:
            self._mark_incomplete(exc)
            yield self._incomplete_result()
            return

        linter_instances = [l() for l in self.get_linter_classes()]
        multi_visitor = dlint.multi.MultiNodeVisitor(linter_instances)

        try:
            multi_visitor.visit(self.tree)
        except MemoryError as exc:
            self._mark_incomplete(exc)
            yield self._incomplete_result()
            return

        for linter_instance in linter_instances:
            for result in linter_instance.get_results():
                try:
                    self.budget.charge_result()
                except limits.BudgetExceeded as exc:
                    self._mark_incomplete(exc)
                    yield self._incomplete_result()
                    return

                yield (
                    result.lineno,
                    result.col_offset,
                    result.message,
                    type(linter_instance)
                )
