# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import mgmt_interface

V6_KEY = 'eth0|2001:db8:100::12/64'
V6_DIFF_KEY = 'MGMT_INTERFACE|' + V6_KEY
V4_KEY = 'eth0|192.0.2.10/24'
V4_DIFF_KEY = 'MGMT_INTERFACE|' + V4_KEY
PORT_DIFF_KEY = 'MGMT_PORT|eth0'


# -- pure helpers --------------------------------------------------------------

@pytest.mark.parametrize('address,expected,version', (
    ('192.0.2.10/24', '192.0.2.10/24', 4),
    ('2001:db8:100:0::12/64', '2001:db8:100::12/64', 6),
    ('2001:DB8::1/128', '2001:db8::1/128', 6),
))
def test_normalize_prefix(address, expected, version):
    assert mgmt_interface.normalize_prefix(address) == (expected, version)


@pytest.mark.parametrize('address', ('192.0.2.10', '2001:db8::1', 'falafel', '192.0.2.10/33', ''))
def test_normalize_prefix_rejects_bad_input(address):
    with pytest.raises(mgmt_interface.ModuleError):
        mgmt_interface.normalize_prefix(address)


def test_normalize_gateway():
    assert mgmt_interface.normalize_gateway('192.0.2.1', 4) == '192.0.2.1'
    assert mgmt_interface.normalize_gateway('2001:db8:100:0::1', 6) == '2001:db8:100::1'
    assert mgmt_interface.normalize_gateway('', 4) is None
    with pytest.raises(mgmt_interface.ModuleError, match='IPv6 but address is IPv4'):
        mgmt_interface.normalize_gateway('2001:db8::1', 4)
    with pytest.raises(mgmt_interface.ModuleError, match='not a valid IP address'):
        mgmt_interface.normalize_gateway('gateway', 4)


def test_normalize_forced_routes():
    assert mgmt_interface.normalize_forced_routes(['198.51.100.0/24', '2001:db8::1', '203.0.113.7/32']) == \
        ['198.51.100.0/24', '2001:db8::1', '203.0.113.7/32']
    with pytest.raises(mgmt_interface.ModuleError):
        mgmt_interface.normalize_forced_routes(['nowhere'])


def test_build_address_entry_only_includes_given_fields():
    assert mgmt_interface.build_address_entry(None, None, 4) == {}
    assert mgmt_interface.build_address_entry('192.0.2.1', None, 4) == {'gwaddr': '192.0.2.1'}
    assert mgmt_interface.build_address_entry('', [], 4) == {'gwaddr': None, 'forced_mgmt_routes': None}
    assert mgmt_interface.build_address_entry(None, ['198.51.100.0/24'], 4) == {'forced_mgmt_routes': ['198.51.100.0/24']}


def test_build_port_entry():
    assert mgmt_interface.build_port_entry() == {}
    assert mgmt_interface.build_port_entry(enabled=True, speed=1000, autoneg=False, mtu=1500, description='oob') == {
        'admin_status': 'up', 'speed': 1000, 'autoneg': 'off', 'mtu': 1500, 'description': 'oob'}
    assert mgmt_interface.build_port_entry(enabled=False, autoneg=True, description='') == {
        'admin_status': 'down', 'autoneg': 'on', 'description': None}


# -- module runs against the fake CONFIG_DB --------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address_with_gateway(fake_swsscommon, run_module, check_mode):
    result = run_module(mgmt_interface, dict(address='2001:db8:100:0::12/64', gateway='2001:db8:100::1'),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'eth0'
    assert result['address'] == '2001:db8:100::12/64'
    assert result['diff'] == {
        'before': {V6_DIFF_KEY: {}},
        'after': {V6_DIFF_KEY: {'gwaddr': '2001:db8:100::1'}},
    }
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry('MGMT_INTERFACE', V6_KEY)
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'MGMT_INTERFACE', V6_KEY, {'gwaddr': '2001:db8:100::1'})]
        assert fake_swsscommon.get_entry('MGMT_INTERFACE', V6_KEY) == {'gwaddr': '2001:db8:100::1'}


def test_add_address_without_gateway_creates_empty_entry(fake_swsscommon, run_module):
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24'))
    assert result['changed'] is True
    assert result['diff'] == {'before': {V4_DIFF_KEY: {}}, 'after': {V4_DIFF_KEY: {}}}
    assert fake_swsscommon.has_entry('MGMT_INTERFACE', V4_KEY)
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', V4_KEY) == {}

    again = run_module(mgmt_interface, dict(address='192.0.2.10/24'))
    assert again['changed'] is False
    assert len(fake_swsscommon.writes) == 1


@pytest.mark.parametrize('check_mode', (True, False))
def test_add_address_is_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'MGMT_INTERFACE': {V6_KEY: {'gwaddr': '2001:db8:100::1'}}})
    result = run_module(mgmt_interface, dict(address='2001:db8:100::12/64', gateway='2001:db8:100::1'),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff']['before'] == result['diff']['after'] == {V6_DIFF_KEY: {'gwaddr': '2001:db8:100::1'}}
    assert fake_swsscommon.writes == []


def test_other_addresses_are_left_alone(fake_swsscommon, run_module):
    fake_swsscommon.seed({'MGMT_INTERFACE': {V6_KEY: {'gwaddr': '2001:db8:100::1'}}})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', gateway='192.0.2.1'))
    assert result['changed'] is True
    assert set(result['diff']['after']) == {V4_DIFF_KEY}
    assert fake_swsscommon.get_table('MGMT_INTERFACE') == {
        V6_KEY: {'gwaddr': '2001:db8:100::1'},
        V4_KEY: {'gwaddr': '192.0.2.1'},
    }


@pytest.mark.parametrize('check_mode', (True, False))
def test_update_gateway(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'MGMT_INTERFACE': {V4_KEY: {'gwaddr': '192.0.2.1', 'forced_mgmt_routes': ['198.51.100.0/24']}}})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', gateway='192.0.2.254'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['diff'] == {
        'before': {V4_DIFF_KEY: {'gwaddr': '192.0.2.1', 'forced_mgmt_routes': ['198.51.100.0/24']}},
        'after': {V4_DIFF_KEY: {'gwaddr': '192.0.2.254', 'forced_mgmt_routes': ['198.51.100.0/24']}},
    }
    expected = {'gwaddr': '192.0.2.254', 'forced_mgmt_routes': ['198.51.100.0/24']}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.get_entry('MGMT_INTERFACE', V4_KEY) == expected
        # forced_mgmt_routes was not given, so it is kept.
        assert fake_swsscommon.writes == [('mod_entry', 'MGMT_INTERFACE', V4_KEY, {'gwaddr': '192.0.2.254'})]


def test_remove_gateway_with_empty_string(fake_swsscommon, run_module):
    fake_swsscommon.seed({'MGMT_INTERFACE': {V4_KEY: {'gwaddr': '192.0.2.1'}}})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', gateway=''))
    assert result['changed'] is True
    assert result['diff']['after'] == {V4_DIFF_KEY: {}}
    assert fake_swsscommon.has_entry('MGMT_INTERFACE', V4_KEY)
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', V4_KEY) == {}


def test_forced_mgmt_routes(fake_swsscommon, run_module):
    fake_swsscommon.seed({'MGMT_INTERFACE': {V4_KEY: {'gwaddr': '192.0.2.1'}}})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', forced_mgmt_routes=['198.51.100.0/24', '203.0.113.9']))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', V4_KEY) == {
        'gwaddr': '192.0.2.1', 'forced_mgmt_routes': ['198.51.100.0/24', '203.0.113.9']}

    again = run_module(mgmt_interface, dict(address='192.0.2.10/24', forced_mgmt_routes=['198.51.100.0/24', '203.0.113.9']))
    assert again['changed'] is False

    cleared = run_module(mgmt_interface, dict(address='192.0.2.10/24', forced_mgmt_routes=[]))
    assert cleared['changed'] is True
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', V4_KEY) == {'gwaddr': '192.0.2.1'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_address(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'MGMT_INTERFACE': {
        V4_KEY: {'gwaddr': '192.0.2.1'},
        V6_KEY: {'gwaddr': '2001:db8:100::1'},
    }})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['address'] == '192.0.2.10/24'
    assert result['diff'] == {'before': {V4_DIFF_KEY: {'gwaddr': '192.0.2.1'}}, 'after': {V4_DIFF_KEY: {}}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('MGMT_INTERFACE', V4_KEY)
    else:
        assert fake_swsscommon.writes == [('set_entry', 'MGMT_INTERFACE', V4_KEY, None)]
        assert not fake_swsscommon.has_entry('MGMT_INTERFACE', V4_KEY)
    # The IPv6 address is untouched either way.
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', V6_KEY) == {'gwaddr': '2001:db8:100::1'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_missing_address_is_idempotent(fake_swsscommon, run_module, check_mode):
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', state='absent'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': {V4_DIFF_KEY: {}}, 'after': {V4_DIFF_KEY: {}}}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_port_fields_merge_into_existing_entry(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'MGMT_PORT': {'eth0': {'alias': 'eth0', 'admin_status': 'up'}}})
    result = run_module(mgmt_interface, dict(description='OOB uplink', speed=1000, autoneg=False, mtu=1500),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'eth0'
    assert 'address' not in result
    after = {'alias': 'eth0', 'admin_status': 'up', 'description': 'OOB uplink', 'speed': '1000', 'autoneg': 'off', 'mtu': '1500'}
    assert result['diff'] == {
        'before': {PORT_DIFF_KEY: {'alias': 'eth0', 'admin_status': 'up'}},
        'after': {PORT_DIFF_KEY: after},
    }
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry('MGMT_PORT', 'eth0') == {'alias': 'eth0', 'admin_status': 'up'}
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'MGMT_PORT', 'eth0',
                                           {'description': 'OOB uplink', 'speed': '1000', 'autoneg': 'off', 'mtu': '1500'})]
        assert fake_swsscommon.get_entry('MGMT_PORT', 'eth0') == after


def test_port_fields_are_idempotent_and_removable(fake_swsscommon, run_module):
    fake_swsscommon.seed({'MGMT_PORT': {'eth0': {'alias': 'eth0', 'admin_status': 'up', 'description': 'OOB uplink'}}})
    result = run_module(mgmt_interface, dict(description='OOB uplink', enabled=True))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []

    result = run_module(mgmt_interface, dict(description='', enabled=False))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('MGMT_PORT', 'eth0') == {'alias': 'eth0', 'admin_status': 'down'}


def test_address_and_port_in_one_run(fake_swsscommon, run_module):
    fake_swsscommon.seed({'MGMT_PORT': {'eth0': {'alias': 'eth0'}}})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', gateway='192.0.2.1', description='oob'))
    assert result['changed'] is True
    assert result['diff'] == {
        'before': {V4_DIFF_KEY: {}, PORT_DIFF_KEY: {'alias': 'eth0'}},
        'after': {V4_DIFF_KEY: {'gwaddr': '192.0.2.1'}, PORT_DIFF_KEY: {'alias': 'eth0', 'description': 'oob'}},
    }
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', V4_KEY) == {'gwaddr': '192.0.2.1'}
    assert fake_swsscommon.get_entry('MGMT_PORT', 'eth0') == {'alias': 'eth0', 'description': 'oob'}

    # Only the port part changes on the second run; the address is already there.
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', gateway='192.0.2.1', description='oob2'))
    assert result['changed'] is True
    assert result['diff']['before'][V4_DIFF_KEY] == result['diff']['after'][V4_DIFF_KEY]


def test_absent_address_still_applies_port_fields(fake_swsscommon, run_module):
    fake_swsscommon.seed({'MGMT_INTERFACE': {V4_KEY: {'gwaddr': '192.0.2.1'}}})
    result = run_module(mgmt_interface, dict(address='192.0.2.10/24', state='absent', enabled=True))
    assert result['changed'] is True
    assert not fake_swsscommon.has_entry('MGMT_INTERFACE', V4_KEY)
    assert fake_swsscommon.get_entry('MGMT_PORT', 'eth0') == {'admin_status': 'up'}


def test_other_management_port(fake_swsscommon, run_module):
    result = run_module(mgmt_interface, dict(interface='eth1', address='192.0.2.10/24', gateway='192.0.2.1'))
    assert result['interface'] == 'eth1'
    assert fake_swsscommon.get_entry('MGMT_INTERFACE', 'eth1|192.0.2.10/24') == {'gwaddr': '192.0.2.1'}


# -- failures --------------------------------------------------------------------

@pytest.mark.parametrize('params,message', (
    (dict(address='192.0.2.10'), 'must include a prefix length'),
    (dict(address='not-an-address/24'), 'not a valid IP address with prefix length'),
    (dict(address='192.0.2.10/24', gateway='2001:db8::1'), 'IPv6 but address is IPv4'),
    (dict(address='192.0.2.10/24', gateway='router'), 'gateway "router" is not a valid IP address'),
    (dict(address='192.0.2.10/24', forced_mgmt_routes=['everywhere']), 'not a valid IP address or prefix'),
    (dict(interface='Ethernet0', address='192.0.2.10/24'), 'not a management port'),
    (dict(gateway='192.0.2.1', enabled=True), 'missing parameter(s) required by \'gateway\': address'),
    (dict(state='absent', enabled=True), 'state is absent but all of the following are missing: address'),
    (dict(interface='eth0'), 'one of the following is required'),
))
def test_failures(fake_swsscommon, run_module, params, message):
    result = run_module(mgmt_interface, params, expect_failure=True)
    assert result['failed'] is True
    assert message in result['msg']
    assert fake_swsscommon.writes == []
