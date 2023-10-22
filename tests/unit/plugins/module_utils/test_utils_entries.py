# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.community.sonic.plugins.module_utils.entries import compare_entries


def test_compare_entries_both_empty():
    changed = compare_entries(None, {})
    assert not changed


def test_compare_entries_new_empty():
    cur = {
        'key': 'value',
    }
    changed = compare_entries({}, cur)
    assert changed


def test_compare_entries_cur_empty():
    new = {
        'key': 'value',
    }
    changed = compare_entries(new, None)
    assert changed


def test_compare_entries_same():
    new = {
        'key': 'value',
    }
    cur = {
        'key': 'value',
    }
    changed = compare_entries(new, cur)
    assert not changed


def test_compare_entries_different():
    new = {
        'key': 'value',
    }
    cur = {
        'key': 'other value',
    }
    changed = compare_entries(new, cur)
    assert changed
