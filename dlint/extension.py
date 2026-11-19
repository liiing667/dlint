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
from dlint import severity


class Flake8Extension(object):
    name = dlint.__name__
    version = dlint.__version__
    options = None
    min_severity = None

    def __init__(self, tree, filename):
        self.tree = tree
        self.filename = filename

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
                '--dlint-min-severity',
                default=None,
                help=(
                    'Only report Dlint findings at or above the given '
                    'severity (INFO, LOW, MEDIUM, HIGH). An unknown '
                    'severity fails closed.'
                ),
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
                "{} {} {} {}".format(
                    linter._code,
                    linter.__name__,
                    linter._get_severity(),
                    linter._error_tmpl[code_prefix_len:]
                )
                for linter in sorted(
                    linters,
                    key=lambda li: (li._get_severity().rank, li._code)
                )
            ]
            print("\n".join(output_lines))
            EX_OK = 0
            sys.exit(EX_OK)

        cls.min_severity = cls._parse_min_severity(
            getattr(options, 'dlint_min_severity', None)
        )
        cls.options = options

    @staticmethod
    def _parse_min_severity(value):
        if value is None or value == '':
            return None
        # Fail closed: an unrecognized severity must never be accepted,
        # otherwise a filter could silently drop high-risk findings.
        return severity.Severity.parse(value)

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

        if getattr(cls, 'min_severity', None) is not None:
            linter_classes = tuple(
                linter_class
                for linter_class in linter_classes
                if linter_class._get_severity() >= cls.min_severity
            )

        if cls.options:
            engine = style_guide.DecisionEngine(cls.options)
            selected = style_guide.Decision.Selected
            linter_classes = tuple(
                linter_class for linter_class in linter_classes
                if engine.decision_for(linter_class._code) is selected
            )

        return linter_classes

    def run(self):
        linter_instances = [l() for l in self.get_linter_classes()]
        multi_visitor = dlint.multi.MultiNodeVisitor(linter_instances)
        multi_visitor.visit(self.tree)

        findings = []
        for linter_instance in linter_instances:
            findings.extend(
                (finding, type(linter_instance))
                for finding in linter_instance.get_findings()
            )

        for finding, linter_class in sorted(
            findings,
            key=lambda item: self._finding_sort_key(item[0])
        ):
            yield (
                finding.lineno,
                finding.col_offset,
                finding.message,
                linter_class
            )

    @staticmethod
    def _finding_sort_key(finding):
        # Highest risk first, then source order and rule identity so the
        # ordering is total and independent of linter registration order.
        return (
            -finding.severity.rank,
            finding.lineno,
            finding.col_offset,
            finding.code,
            finding.message
        )
