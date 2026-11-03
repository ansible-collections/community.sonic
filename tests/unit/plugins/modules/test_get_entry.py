# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.community.sonic.plugins.modules import get_entry


def test_get_entry_returns_table_without_key(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VLAN': {'Vlan3600': {'vlanid': '3600'}}})
    result = run_module(get_entry, dict(table='VLAN'))
    assert result['value'] == {'Vlan3600': {'vlanid': '3600'}}
    assert 'key' not in result
    assert fake_swsscommon.writes == []


def test_get_entry_check_mode_reads(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VLAN': {'Vlan3600': {'vlanid': '3600'}}})
    result = run_module(get_entry, dict(table='VLAN', key='Vlan3600'), check_mode=True)
    assert result['value'] == {'vlanid': '3600'}
    assert result['key'] == 'Vlan3600'
