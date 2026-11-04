# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import l3_interface
from ansible_collections.community.sonic.plugins.modules import interface_ip

PORTS = {'PORT': {
    'Ethernet0': {'alias': 'fortyGigE0/0'},
    'Ethernet24': {'alias': 'fortyGigE0/24'},
}}


@pytest.mark.parametrize('given,expected', (
    ('192.0.2.1/31', '192.0.2.1/31'),
    ('192.0.2.1/32', '192.0.2.1/32'),
    ('10.0.0.1/24', '10.0.0.1/24'),
    (' 10.0.0.1/24 ', '10.0.0.1/24'),
    ('2001:db8:0:0::1/64', '2001:db8::1/64'),
    ('2001:DB8::1/128', '2001:db8::1/128'),
    ('fe80::1/64', 'fe80::1/64'),
))
def test_normalize_prefix(given, expected):
    assert l3_interface.normalize_prefix(given) == expected


@pytest.mark.parametrize('given,fragment', (
    ('192.0.2.1', 'must include a prefix length'),
    ('falafel/24', 'not a valid IP prefix'),
    ('192.0.2.1/33', 'not a valid IP prefix'),
    ('192.0.2.0/24', 'network address'),
    ('192.0.2.255/24', 'broadcast address'),
    ('0.0.0.0/0', 'unspecified'),
    ('224.0.0.1/32', 'multicast'),
    ('ff02::1/128', 'multicast'),
    ('::/0', 'unspecified'),
))
def test_normalize_prefix_rejects(given, fragment):
    with pytest.raises(l3_interface.InvalidAddressError) as excinfo:
        l3_interface.normalize_prefix(given)
    assert fragment in str(excinfo.value)


def test_member_of(fake_swsscommon, run_module):
    fake_swsscommon.seed({
        'VLAN_MEMBER': {'Vlan100|Ethernet0': {'tagging_mode': 'tagged'}},
        'PORTCHANNEL_MEMBER': {'PortChannel1|Ethernet4': {}},
    })
    from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB
    db = ConfigDB(None, connector=fake_swsscommon.ConfigDBConnector()).connect()
    assert l3_interface.member_of(db, 'Ethernet0') == 'Vlan100'
    assert l3_interface.member_of(db, 'Ethernet4') == 'PortChannel1'
    assert l3_interface.member_of(db, 'Ethernet8') is None


@pytest.mark.parametrize('check_mode', (True, False))
def test_first_address_creates_parent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(PORTS)
    result = run_module(interface_ip, dict(interface='Ethernet24', address='192.0.2.1/31'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet24'
    assert result['address'] == '192.0.2.1/31'
    assert result['table'] == 'INTERFACE'
    assert result['addresses'] == ['192.0.2.1/31']
    assert result['parent_created'] is True
    assert result['parent_removed'] is False
    assert result['diff'] == {'before': {}, 'after': {'Ethernet24': {}, 'Ethernet24|192.0.2.1/31': {}}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_table('INTERFACE') == {}
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'INTERFACE', 'Ethernet24', {}),
            ('set_entry', 'INTERFACE', 'Ethernet24|192.0.2.1/31', {}),
        ]
        assert fake_swsscommon.get_table('INTERFACE') == {'Ethernet24': {}, 'Ethernet24|192.0.2.1/31': {}}


def test_second_address_keeps_parent(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    fake_swsscommon.seed({'INTERFACE': {'Ethernet24': {'vrf_name': 'Vrf1'}, 'Ethernet24|192.0.2.1/31': {}}})
    result = run_module(interface_ip, dict(interface='Ethernet24', address='2001:db8:0:0::1/64'))
    assert result['changed'] is True
    assert result['address'] == '2001:db8::1/64'
    assert result['addresses'] == ['192.0.2.1/31', '2001:db8::1/64']
    assert result['parent_created'] is False
    assert result['diff'] == {'before': {}, 'after': {'Ethernet24|2001:db8::1/64': {}}}
    assert fake_swsscommon.writes == [('set_entry', 'INTERFACE', 'Ethernet24|2001:db8::1/64', {})]
    assert fake_swsscommon.get_entry('INTERFACE', 'Ethernet24') == {'vrf_name': 'Vrf1'}


@pytest.mark.parametrize('check_mode', (True, False))
def test_present_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(PORTS)
    fake_swsscommon.seed({'INTERFACE': {'Ethernet24': {}, 'Ethernet24|2001:db8::1/64': {}}})
    result = run_module(interface_ip, dict(interface='fortyGigE0/24', address='2001:DB8:0::1/64'), check_mode=check_mode)
    assert result['changed'] is False
    assert result['interface'] == 'Ethernet24'
    assert result['diff'] == {'before': {}, 'after': {}}
    assert result['parent_created'] is False
    assert fake_swsscommon.writes == []


def test_alias_is_resolved(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(interface_ip, dict(interface='fortyGigE0/24', address='192.0.2.1/31'))
    assert result['interface'] == 'Ethernet24'
    assert fake_swsscommon.has_entry('INTERFACE', 'Ethernet24|192.0.2.1/31')


@pytest.mark.parametrize('interface,table,defining', (
    ('PortChannel2', 'PORTCHANNEL_INTERFACE', {'PORTCHANNEL': {'PortChannel2': {'admin_status': 'up'}}}),
    ('Vlan100', 'VLAN_INTERFACE', {'VLAN': {'Vlan100': {'vlanid': '100'}}}),
    ('Loopback1', 'LOOPBACK_INTERFACE', {}),
))
def test_table_selection(fake_swsscommon, run_module, interface, table, defining):
    fake_swsscommon.seed(defining)
    result = run_module(interface_ip, dict(interface=interface, address='203.0.113.2/24'))
    assert result['changed'] is True
    assert result['table'] == table
    assert result['parent_created'] is True
    assert fake_swsscommon.get_table(table) == {interface: {}, interface + '|203.0.113.2/24': {}}


@pytest.mark.parametrize('interface', ('PortChannel2', 'Vlan100'))
def test_undefined_interface_fails(fake_swsscommon, run_module, interface):
    result = run_module(interface_ip, dict(interface=interface, address='203.0.113.2/24'), expect_failure=True)
    assert result['msg'] == 'interface "%s" does not exist' % interface
    assert fake_swsscommon.writes == []


def test_unknown_port_fails(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(interface_ip, dict(interface='Ethernet99', address='203.0.113.2/24'), expect_failure=True)
    assert result['msg'] == 'could not find interface "Ethernet99"'


def test_bad_loopback_name_fails(fake_swsscommon, run_module):
    result = run_module(interface_ip, dict(interface='Loopback1000', address='203.0.113.2/24'), expect_failure=True)
    assert 'invalid loopback interface name "Loopback1000"' in result['msg']


def test_invalid_address_fails_before_connecting(fake_swsscommon, run_module):
    result = run_module(interface_ip, dict(interface='Ethernet24', address='192.0.2.1'), expect_failure=True)
    assert result['msg'] == 'address "192.0.2.1" must include a prefix length, for example 192.0.2.1/31'
    assert fake_swsscommon.connectors == []


def test_vlan_member_port_is_rejected(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    fake_swsscommon.seed({'VLAN_MEMBER': {'Vlan100|Ethernet24': {'tagging_mode': 'untagged'}}})
    result = run_module(interface_ip, dict(interface='Ethernet24', address='192.0.2.1/31'), expect_failure=True)
    assert result['msg'] == 'interface "Ethernet24" is a member of Vlan100 and cannot have an IP address'
    assert fake_swsscommon.writes == []


def test_portchannel_member_port_is_rejected(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    fake_swsscommon.seed({'PORTCHANNEL_MEMBER': {'PortChannel1|Ethernet24': {}}})
    result = run_module(interface_ip, dict(interface='fortyGigE0/24', address='192.0.2.1/31'), expect_failure=True)
    assert result['msg'] == 'interface "Ethernet24" is a member of PortChannel1 and cannot have an IP address'


def test_portchannel_vlan_member_is_rejected(fake_swsscommon, run_module):
    fake_swsscommon.seed({
        'PORTCHANNEL': {'PortChannel1': {}},
        'VLAN_MEMBER': {'Vlan100|PortChannel1': {'tagging_mode': 'tagged'}},
    })
    result = run_module(interface_ip, dict(interface='PortChannel1', address='192.0.2.1/31'), expect_failure=True)
    assert result['msg'] == 'interface "PortChannel1" is a member of Vlan100 and cannot have an IP address'


def test_absent_member_port_does_not_fail(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    fake_swsscommon.seed({'VLAN_MEMBER': {'Vlan100|Ethernet24': {'tagging_mode': 'untagged'}}})
    result = run_module(interface_ip, dict(interface='Ethernet24', address='192.0.2.1/31', state='absent'))
    assert result['changed'] is False


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent_keeps_parent_when_addresses_remain(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'LOOPBACK_INTERFACE': {
        'Loopback1': {}, 'Loopback1|192.0.2.1/32': {}, 'Loopback1|2001:db8::1/128': {},
    }})
    result = run_module(interface_ip, dict(interface='Loopback1', address='192.0.2.1/32', state='absent', remove_parent=True),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['addresses'] == ['2001:db8::1/128']
    assert result['parent_removed'] is False
    assert result['diff'] == {'before': {'Loopback1|192.0.2.1/32': {}}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', 'LOOPBACK_INTERFACE', 'Loopback1|192.0.2.1/32', None)]
        assert fake_swsscommon.get_table('LOOPBACK_INTERFACE') == {'Loopback1': {}, 'Loopback1|2001:db8::1/128': {}}


def test_absent_last_address_keeps_parent_by_default(fake_swsscommon, run_module):
    fake_swsscommon.seed({'LOOPBACK_INTERFACE': {'Loopback1': {}, 'Loopback1|192.0.2.1/32': {}}})
    result = run_module(interface_ip, dict(interface='Loopback1', address='192.0.2.1/32', state='absent'))
    assert result['changed'] is True
    assert result['addresses'] == []
    assert result['parent_removed'] is False
    assert fake_swsscommon.get_table('LOOPBACK_INTERFACE') == {'Loopback1': {}}


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent_last_address_removes_parent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'LOOPBACK_INTERFACE': {
        'Loopback0': {}, 'Loopback0|10.1.0.1/32': {},
        'Loopback1': {'vrf_name': 'Vrf1'}, 'Loopback1|192.0.2.1/32': {},
    }})
    result = run_module(interface_ip, dict(interface='Loopback1', address='192.0.2.1/32', state='absent', remove_parent=True),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['addresses'] == []
    assert result['parent_removed'] is True
    assert result['diff'] == {'before': {'Loopback1|192.0.2.1/32': {}, 'Loopback1': {'vrf_name': 'Vrf1'}}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('LOOPBACK_INTERFACE', 'Loopback1')
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'LOOPBACK_INTERFACE', 'Loopback1|192.0.2.1/32', None),
            ('set_entry', 'LOOPBACK_INTERFACE', 'Loopback1', None),
        ]
        assert fake_swsscommon.get_table('LOOPBACK_INTERFACE') == {'Loopback0': {}, 'Loopback0|10.1.0.1/32': {}}


def test_absent_remove_parent_without_address(fake_swsscommon, run_module):
    """An address that is already gone still lets remove_parent clean up an empty parent entry."""
    fake_swsscommon.seed({'INTERFACE': {'Ethernet24': {}}})
    fake_swsscommon.seed(PORTS)
    result = run_module(interface_ip, dict(interface='Ethernet24', address='192.0.2.1/31', state='absent', remove_parent=True))
    assert result['changed'] is True
    assert result['parent_removed'] is True
    assert result['diff'] == {'before': {'Ethernet24': {}}, 'after': {}}
    assert fake_swsscommon.get_table('INTERFACE') == {}


@pytest.mark.parametrize('check_mode', (True, False))
def test_absent_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(PORTS)
    result = run_module(interface_ip, dict(interface='Ethernet24', address='192.0.2.1/31', state='absent', remove_parent=True),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert result['parent_removed'] is False
    assert fake_swsscommon.writes == []
