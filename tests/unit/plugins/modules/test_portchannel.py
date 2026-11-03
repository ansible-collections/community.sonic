# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import portchannel


DEFAULT_ENTRY = {'admin_status': 'up', 'mtu': '9100', 'min_links': '1', 'lacp_key': 'auto'}


def test_build_entry_defaults():
    entry = portchannel.build_portchannel_entry(
        name='PortChannel3', state='present', enabled=True, mtu=9100, min_links=1, fast_rate=False,
        fallback=False, lacp_key='auto', description=None)
    assert entry == {'admin_status': 'up', 'mtu': 9100, 'min_links': 1, 'lacp_key': 'auto'}


def test_build_entry_all_fields():
    entry = portchannel.build_portchannel_entry(
        name='PortChannel3', state='present', enabled=False, mtu=1500, min_links=2, fast_rate=True,
        fallback=True, lacp_key='300', description='Peering')
    assert entry == {'admin_status': 'down', 'mtu': 1500, 'min_links': 2, 'lacp_key': '300',
                     'fast_rate': True, 'fallback': True, 'description': 'Peering'}


def test_build_entry_absent():
    assert portchannel.build_portchannel_entry(
        name='PortChannel3', state='absent', enabled=True, mtu=9100, min_links=1, fast_rate=False,
        fallback=False, lacp_key='auto', description=None) is None


@pytest.mark.parametrize('params,fragment', (
    (dict(name='Po3'), 'invalid PortChannel name'),
    (dict(name='PortChannel'), 'invalid PortChannel name'),
    (dict(name='PortChannel12345'), 'invalid PortChannel name'),
    (dict(name='portchannel3'), 'invalid PortChannel name'),
    (dict(name='PortChannel3', mtu=10), 'mtu 10 is out of range'),
    (dict(name='PortChannel3', mtu=9217), 'mtu 9217 is out of range'),
    (dict(name='PortChannel3', min_links=0), 'min_links must be at least 1'),
    (dict(name='PortChannel3', lacp_key='manual'), 'lacp_key must be'),
    (dict(name='PortChannel3', lacp_key='0'), 'lacp_key must be'),
    (dict(name='PortChannel3', lacp_key='65536'), 'lacp_key must be'),
))
def test_validate_params_rejects(params, fragment):
    defaults = dict(mtu=9100, min_links=1, lacp_key='auto')
    defaults.update(params)
    assert fragment in portchannel.validate_params(**defaults)


@pytest.mark.parametrize('params', (
    dict(name='PortChannel0'),
    dict(name='PortChannel9999'),
    dict(name='PortChannel3', mtu=68),
    dict(name='PortChannel3', mtu=9216),
    dict(name='PortChannel3', lacp_key='1'),
    dict(name='PortChannel3', lacp_key='65535'),
))
def test_validate_params_accepts(params):
    defaults = dict(mtu=9100, min_links=1, lacp_key='auto')
    defaults.update(params)
    assert portchannel.validate_params(**defaults) is None


def test_removal_blockers():
    assert portchannel.removal_blockers('PortChannel3', [], [], []) is None
    assert portchannel.removal_blockers(
        'PortChannel3', ['PortChannel4|Ethernet0'], ['Vlan10|PortChannel4'], ['PortChannel4', 'PortChannel4|10.0.0.1/31']) is None
    assert portchannel.removal_blockers(
        'PortChannel3', ['PortChannel3|Ethernet4', 'PortChannel3|Ethernet0'], [], []) == \
        'PortChannel3 still has members Ethernet0, Ethernet4; remove them with community.sonic.portchannel_member first'
    assert portchannel.removal_blockers('PortChannel3', [], ['Vlan10|PortChannel3'], []) == \
        'PortChannel3 is still a member of Vlan10; remove the VLAN membership first'
    assert 'IP address' in portchannel.removal_blockers('PortChannel3', [], [], ['PortChannel3|10.0.0.1/31'])
    assert 'IP address' in portchannel.removal_blockers('PortChannel3', [], [], ['PortChannel3'])


# -- end-to-end through the fake CONFIG_DB ----------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create(fake_swsscommon, run_module, check_mode):
    result = run_module(portchannel, dict(name='PortChannel3', description='Peering', fast_rate=True), check_mode=check_mode)
    wanted = dict(DEFAULT_ENTRY, description='Peering', fast_rate='true')
    assert result['changed'] is True
    assert result['interface'] == 'PortChannel3'
    assert result['diff'] == {'before': {}, 'after': wanted}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry('PORTCHANNEL', 'PortChannel3')
    else:
        assert fake_swsscommon.writes == [('set_entry', 'PORTCHANNEL', 'PortChannel3', wanted)]
        assert fake_swsscommon.get_entry('PORTCHANNEL', 'PortChannel3') == wanted


@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, check_mode):
    current = dict(DEFAULT_ENTRY, description='Peering', fast_rate='true')
    fake_swsscommon.seed({'PORTCHANNEL': {'PortChannel3': current}})
    result = run_module(portchannel, dict(name='PortChannel3', description='Peering', fast_rate=True), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': current, 'after': current}
    assert fake_swsscommon.writes == []


def test_cli_created_portchannel_is_unchanged_with_defaults(fake_swsscommon, run_module):
    # `config portchannel add PortChannel3` (default options) writes exactly this.
    current = {'admin_status': 'up', 'mtu': '9100', 'lacp_key': 'auto', 'min_links': '1'}
    fake_swsscommon.seed({'PORTCHANNEL': {'PortChannel3': current}})
    result = run_module(portchannel, dict(name='PortChannel3'))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_update(fake_swsscommon, run_module, check_mode):
    current = dict(DEFAULT_ENTRY, description='old', fast_rate='true')
    fake_swsscommon.seed({'PORTCHANNEL': {'PortChannel3': current}})
    result = run_module(portchannel, dict(name='PortChannel3', enabled=False, mtu=1500, min_links=2, lacp_key=300),
                        check_mode=check_mode)
    wanted = {'admin_status': 'down', 'mtu': '1500', 'min_links': '2', 'lacp_key': '300'}
    assert result['changed'] is True
    assert result['diff'] == {'before': current, 'after': wanted}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('PORTCHANNEL', 'PortChannel3') == current
    else:
        assert fake_swsscommon.writes == [('set_entry', 'PORTCHANNEL', 'PortChannel3', wanted)]
        assert fake_swsscommon.get_entry('PORTCHANNEL', 'PortChannel3') == wanted


@pytest.mark.parametrize('description', (None, ''))
def test_omitted_description_is_removed(fake_swsscommon, run_module, description):
    fake_swsscommon.seed({'PORTCHANNEL': {'PortChannel3': dict(DEFAULT_ENTRY, description='old')}})
    params = dict(name='PortChannel3')
    if description is not None:
        params['description'] = description
    result = run_module(portchannel, params)
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('PORTCHANNEL', 'PortChannel3') == DEFAULT_ENTRY


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORTCHANNEL': {'PortChannel3': DEFAULT_ENTRY}})
    result = run_module(portchannel, dict(name='PortChannel3', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'PortChannel3'
    assert result['diff'] == {'before': DEFAULT_ENTRY, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('PORTCHANNEL', 'PortChannel3')
    else:
        assert fake_swsscommon.writes == [('set_entry', 'PORTCHANNEL', 'PortChannel3', None)]
        assert not fake_swsscommon.has_entry('PORTCHANNEL', 'PortChannel3')


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_absent_is_idempotent(fake_swsscommon, run_module, check_mode):
    result = run_module(portchannel, dict(name='PortChannel3', state='absent'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_refuses_with_members(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({
        'PORTCHANNEL': {'PortChannel3': DEFAULT_ENTRY},
        'PORTCHANNEL_MEMBER': {'PortChannel3|Ethernet0': {}, 'PortChannel4|Ethernet4': {}},
    })
    result = run_module(portchannel, dict(name='PortChannel3', state='absent'), check_mode=check_mode, expect_failure=True)
    assert result['msg'] == \
        'PortChannel3 still has members Ethernet0; remove them with community.sonic.portchannel_member first'
    assert fake_swsscommon.writes == []
    assert fake_swsscommon.has_entry('PORTCHANNEL', 'PortChannel3')


def test_remove_refuses_vlan_member(fake_swsscommon, run_module):
    fake_swsscommon.seed({
        'PORTCHANNEL': {'PortChannel3': DEFAULT_ENTRY},
        'VLAN_MEMBER': {'Vlan100|PortChannel3': {'tagging_mode': 'tagged'}},
    })
    result = run_module(portchannel, dict(name='PortChannel3', state='absent'), expect_failure=True)
    assert result['msg'] == 'PortChannel3 is still a member of Vlan100; remove the VLAN membership first'
    assert fake_swsscommon.writes == []


def test_remove_refuses_with_ip(fake_swsscommon, run_module):
    fake_swsscommon.seed({
        'PORTCHANNEL': {'PortChannel3': DEFAULT_ENTRY},
        'PORTCHANNEL_INTERFACE': {'PortChannel3': {}, 'PortChannel3|10.0.0.1/31': {}},
    })
    result = run_module(portchannel, dict(name='PortChannel3', state='absent'), expect_failure=True)
    assert 'IP address' in result['msg']
    assert fake_swsscommon.writes == []


def test_invalid_name_fails_before_connecting(fake_swsscommon, run_module):
    result = run_module(portchannel, dict(name='Po3'), expect_failure=True)
    assert 'invalid PortChannel name' in result['msg']
    assert fake_swsscommon.connectors == []
