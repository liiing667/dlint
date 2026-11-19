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
import os
import sys
import tokenize

from flake8 import style_guide

import dlint
from dlint import budget


class Flake8Extension(object):
    name = dlint.__name__
    version = dlint.__version__
    options = None

    # Meta-diagnostic emitted when the shared scan budget is exhausted. It
    # keeps an over-sized or encoding-odd file from being reported as clean.
    INCOMPLETE_CODE = 'DUO139'
    INCOMPLETE_ERROR_TMPL = (
        'DUO139 scan incomplete: {reason}; results above may be partial'
    )

    DEFAULT_BUDGET_LIMIT = 10 * 1024 * 1024

    def __init__(self, tree, filename):
        self.tree = tree
        self.filename = filename
        # Build the budget lazily in run() so options changed after
        # construction (e.g. in tests) still take effect, and so every run
        # against this instance shares a single fresh budget.
        self.scan_budget = None

    @classmethod
    def _get_budget_limit(cls):
        if not cls.options:
            return cls.DEFAULT_BUDGET_LIMIT

        return getattr(
            cls.options, 'dlint_budget_limit', cls.DEFAULT_BUDGET_LIMIT
        )

    @classmethod
    def _build_budget(cls):
        return budget.ScanBudget(cls._get_budget_limit())

    @classmethod
    def _file_byte_count(cls, filename):
        if not filename or filename in ('-', 'stdin'):
            # flake8 already read stdin into memory; size cannot be checked
            # again here, so the AST and report stages still apply.
            return 0

        try:
            return os.path.getsize(filename)
        except (IOError, OSError):
            # Let flake8 surface the unreadable file through its own
            # diagnostics rather than masking it with a budget failure.
            return 0

    @classmethod
    def _incomplete_result(cls, reason, lineno=0, col_offset=0):
        return (
            lineno,
            col_offset,
            cls.INCOMPLETE_ERROR_TMPL.format(reason=reason),
            cls
        )

    def _incomplete_result_from_error(self, error):
        reason = str(error)

        return self._incomplete_result(reason)

    @staticmethod
    def _detect_encoding_error(filename):
        """Return a human-readable reason if ``filename`` cannot be decoded.

        flake8 silently falls back to latin-1 when a source file declares an
        encoding that cannot represent its bytes, which skips AST plugins and
        makes the file look clean. Detect that case up-front so it can be
        reported as an incomplete scan instead.
        """
        try:
            with open(filename, 'rb') as fd:
                readline = fd.readline
                encoding, _ = tokenize.detect_encoding(readline)

                fd.seek(0)
                fd.read().decode(encoding)
        except (SyntaxError, UnicodeError, LookupError) as error:
            return "{}: {}".format(type(error).__name__, error)
        except (IOError, OSError):
            return None

        return None

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
                '--dlint-budget-limit',
                action='store',
                type=int,
                default=cls.DEFAULT_BUDGET_LIMIT,
                parse_from_config=True,
                help=(
                    'Shared budget (in abstract units) for reading files, '
                    'walking the AST and reporting results. Files which '
                    'exhaust the budget are reported with an incomplete '
                    'scan diagnostic (DUO139).'
                )
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
        if self.scan_budget is None:
            self.scan_budget = self._build_budget()

        if self.filename not in (None, '-', 'stdin'):
            encoding_error = self._detect_encoding_error(self.filename)
            if encoding_error:
                yield self._incomplete_result(
                    "source file is not decodable ({})".format(encoding_error)
                )
                return

        try:
            self.scan_budget.charge_file(
                self._file_byte_count(self.filename)
            )
        except budget.BudgetExceeded as error:
            yield self._incomplete_result_from_error(error)
            return

        linter_instances = [l() for l in self.get_linter_classes()]
        multi_visitor = dlint.multi.MultiNodeVisitor(
            linter_instances, self.scan_budget
        )

        try:
            multi_visitor.visit(self.tree)
        except budget.BudgetExceeded as error:
            yield self._incomplete_result_from_error(error)
            return

        for linter_instance in linter_instances:
            for result in linter_instance.get_results():
                try:
                    self.scan_budget.charge_report()
                except budget.BudgetExceeded as error:
                    yield self._incomplete_result_from_error(error)
                    return

                yield (
                    result.lineno,
                    result.col_offset,
                    result.message,
                    type(linter_instance)
                )
