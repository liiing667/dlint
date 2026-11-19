#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import unittest

import dlint


class TestSeverity(unittest.TestCase):

    def test_ordering(self):
        info = dlint.severity.Severity('INFO')
        low = dlint.severity.Severity('LOW')
        medium = dlint.severity.Severity('MEDIUM')
        high = dlint.severity.Severity('HIGH')

        assert info < low < medium < high
        assert high > medium > low > info
        assert medium == dlint.severity.Severity('medium')
        assert low != high

    def test_parse_accepts_members_and_names(self):
        high = dlint.severity.Severity('HIGH')

        assert dlint.severity.Severity.parse(high) is high
        assert dlint.severity.Severity.parse('HIGH') == high
        assert dlint.severity.Severity.parse(' high ') == high
        assert dlint.severity.Severity.parse(dlint.severity.Severity.HIGH) == high

    def test_member_level_and_copy_construction(self):
        high = dlint.severity.Severity(
            dlint.severity.Severity.HIGH
        )
        copy = dlint.severity.Severity(high)

        assert high == dlint.severity.Severity('HIGH')
        assert copy == high
        assert high.rank == 3
        assert high.name == 'HIGH'

    def test_bogus_member_level_fails_closed(self):
        bogus = dlint.severity._SeverityLevel('BOGUS', 99)

        with self.assertRaises(dlint.severity.InvalidSeverity):
            dlint.severity.Severity(bogus)

    def test_members_are_fully_ordered(self):
        names = [member.name for member in dlint.severity.Severity.members()]

        assert names == ['INFO', 'LOW', 'MEDIUM', 'HIGH']

    def test_unknown_string_fails_closed(self):
        with self.assertRaises(dlint.severity.InvalidSeverity):
            dlint.severity.Severity('CRITICAL')

    def test_unknown_none_fails_closed(self):
        with self.assertRaises(dlint.severity.InvalidSeverity):
            dlint.severity.Severity(None)

    def test_unknown_type_fails_closed(self):
        with self.assertRaises(dlint.severity.InvalidSeverity):
            dlint.severity.Severity(42)

    def test_parse_unknown_fails_closed(self):
        with self.assertRaises(dlint.severity.InvalidSeverity):
            dlint.severity.Severity.parse('unknown')

    def test_string_name(self):
        assert str(dlint.severity.Severity('LOW')) == 'LOW'
        assert repr(
            dlint.severity.Severity('LOW')
        ) == "Severity('LOW')"

    def test_hashable_and_set_membership(self):
        severities = {
            dlint.severity.Severity('LOW'),
            dlint.severity.Severity('LOW'),
            dlint.severity.Severity('HIGH'),
        }

        assert len(severities) == 2

    def test_comparison_against_unknown_is_not_implemented(self):
        medium = dlint.severity.Severity('MEDIUM')

        assert medium.__eq__('BOGUS') is NotImplemented
        assert medium.__lt__('BOGUS') is NotImplemented


if __name__ == "__main__":
    unittest.main()
