# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import l3_interface
from ansible_collections.community.sonic.plugins.modules import loopback

TABLE = 'LOOPBACK_INTERFACE'


def test_build_loopback_entry():
    assert loopback.build_loopback_entry({}, None) == {}
    assert loopback.build_loopback_entry({'nat_zone': '1'}, None) == {'nat_zone': '1'}
    assert loopback.build_loopback_entry({}, 'Vrf1') == {'vrf_name': 'Vrf1'}
    assert loopback.build_loopback_entry({'vrf_name': 'Vrf1', 'nat_zone': '1'}, '') == {'nat_zone': '1'}
    assert loopback.build_loopback_entry({'vrf_name': 'Vrf1'}, 'Vrf2') == {'vrf_name': 'Vrf2'}


@pytest.mark.parametrize('name', ('Loopback0', 'Loopback1', 'Loopback999'))
def test_validate_loopback_name_ok(name):
    assert l3_interface.validate_loopback_name(name) == name


@pytest.mark.parametrize('name', ('Loopback', 'loopback0', 'Loopback1000', 'Loopback01x', 'Ethernet0', 'lo'))
def test_validate_loopback_name_bad(name):
    with pytest.raises(l3_interface.InvalidLoopbackNameError):
        l3_interface.validate_loopback_name(name)


@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    result = run_module(loopback, dict(name='Loopback1'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'Loopback1'
    assert result['table'] == TABLE
    assert result['addresses'] == []
    assert result['diff'] == {'before': {}, 'after': {'Loopback1': {}}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry(TABLE, 'Loopback1')
    else:
        assert fake_swsscommon.writes == [('set_entry', TABLE, 'Loopback1', {})]
        assert fake_swsscommon.has_entry(TABLE, 'Loopback1')
        assert fake_swsscommon.get_entry(TABLE, 'Loopback1') == {}


def test_create_idempotent(fake_swsscommon, run_module):
    fake_swsscommon.seed({TABLE: {'Loopback1': {}, 'Loopback1|192.0.2.1/32': {}}})
    result = run_module(loopback, dict(name='Loopback1'))
    assert result['changed'] is False
    assert result['addresses'] == ['192.0.2.1/32']
    assert result['diff'] == {'before': {'Loopback1': {}}, 'after': {'Loopback1': {}}}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_create_with_vrf(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'VRF': {'Vrf-blue': {}}})
    result = run_module(loopback, dict(name='Loopback2', vrf='Vrf-blue'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {'before': {}, 'after': {'Loopback2': {'vrf_name': 'Vrf-blue'}}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.get_entry(TABLE, 'Loopback2') == {'vrf_name': 'Vrf-blue'}


def test_vrf_mgmt_is_accepted(fake_swsscommon, run_module):
    result = run_module(loopback, dict(name='Loopback2', vrf='mgmt'))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry(TABLE, 'Loopback2') == {'vrf_name': 'mgmt'}


def test_vrf_must_exist(fake_swsscommon, run_module):
    result = run_module(loopback, dict(name='Loopback2', vrf='Vrf-nope'), expect_failure=True)
    assert result['msg'] == 'VRF "Vrf-nope" does not exist'
    assert fake_swsscommon.writes == []


def test_vrf_change_keeps_other_fields(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VRF': {'Vrf-red': {}}, TABLE: {'Loopback1': {'vrf_name': 'Vrf-blue', 'nat_zone': '1'}}})
    result = run_module(loopback, dict(name='Loopback1', vrf='Vrf-red'))
    assert result['changed'] is True
    assert result['diff'] == {
        'before': {'Loopback1': {'vrf_name': 'Vrf-blue', 'nat_zone': '1'}},
        'after': {'Loopback1': {'vrf_name': 'Vrf-red', 'nat_zone': '1'}},
    }
    assert fake_swsscommon.get_entry(TABLE, 'Loopback1') == {'vrf_name': 'Vrf-red', 'nat_zone': '1'}


def test_vrf_omitted_keeps_binding(fake_swsscommon, run_module):
    fake_swsscommon.seed({TABLE: {'Loopback1': {'vrf_name': 'Vrf-blue'}}})
    result = run_module(loopback, dict(name='Loopback1'))
    assert result['changed'] is False
    assert fake_swsscommon.get_entry(TABLE, 'Loopback1') == {'vrf_name': 'Vrf-blue'}


def test_vrf_empty_removes_binding(fake_swsscommon, run_module):
    fake_swsscommon.seed({TABLE: {'Loopback1': {'vrf_name': 'Vrf-blue'}}})
    result = run_module(loopback, dict(name='Loopback1', vrf=''))
    assert result['changed'] is True
    assert result['diff'] == {'before': {'Loopback1': {'vrf_name': 'Vrf-blue'}}, 'after': {'Loopback1': {}}}
    assert fake_swsscommon.writes == [('set_entry', TABLE, 'Loopback1', {})]
    assert fake_swsscommon.has_entry(TABLE, 'Loopback1')
    assert fake_swsscommon.get_entry(TABLE, 'Loopback1') == {}


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent_removes_addresses(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({TABLE: {
        'Loopback0': {},
        'Loopback0|10.1.0.1/32': {},
        'Loopback1': {'vrf_name': 'Vrf-blue'},
        'Loopback1|192.0.2.1/32': {},
        'Loopback1|2001:db8::1/128': {},
        'Loopback10': {},
        'Loopback10|192.0.2.10/32': {},
    }})
    result = run_module(loopback, dict(name='Loopback1', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['addresses'] == ['192.0.2.1/32', '2001:db8::1/128']
    assert result['diff'] == {
        'before': {'Loopback1': {'vrf_name': 'Vrf-blue'}, 'Loopback1|192.0.2.1/32': {}, 'Loopback1|2001:db8::1/128': {}},
        'after': {},
    }
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry(TABLE, 'Loopback1')
    else:
        assert sorted(fake_swsscommon.get_table(TABLE)) == ['Loopback0', 'Loopback0|10.1.0.1/32', 'Loopback10', 'Loopback10|192.0.2.10/32']


def test_absent_idempotent(fake_swsscommon, run_module):
    result = run_module(loopback, dict(name='Loopback1', state='absent'))
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_bad_name(fake_swsscommon, run_module):
    result = run_module(loopback, dict(name='lo0'), expect_failure=True)
    assert 'invalid loopback interface name "lo0"' in result['msg']
    assert fake_swsscommon.connectors == []
