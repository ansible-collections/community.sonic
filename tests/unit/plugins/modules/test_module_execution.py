# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end module runs against the dict-backed fake CONFIG_DB."""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import config_db
from ansible_collections.community.sonic.plugins.modules import get_entry, sonic_interface_port, vlan, vlan_member


@pytest.mark.parametrize('module,params,table,key,current,wanted,extra', (
    (vlan, dict(vlanid=42),
     'VLAN', 'Vlan42', {}, {'vlanid': '42'}, {'interface': 'Vlan42'}),
    (vlan, dict(vlanid=42, dhcp_servers=['10.0.0.1', '2001:db8::1']),
     'VLAN', 'Vlan42', {'vlanid': '42'},
     {'vlanid': '42', 'dhcp_servers': ['10.0.0.1'], 'dhcpv6_servers': ['2001:db8::1']}, {'interface': 'Vlan42'}),
    (vlan, dict(vlanid=42, state='absent'),
     'VLAN', 'Vlan42', {'vlanid': '42'}, None, {'interface': 'Vlan42'}),
    (vlan_member, dict(vlanid=42, interface='Ethernet0', tagged=True),
     'VLAN_MEMBER', 'Vlan42|Ethernet0', {}, {'tagging_mode': 'tagged'}, {}),
    (vlan_member, dict(vlanid=42, interface='Ethernet0', tagged=False),
     'VLAN_MEMBER', 'Vlan42|Ethernet0', {'tagging_mode': 'tagged'}, {'tagging_mode': 'untagged'}, {}),
    (vlan_member, dict(vlanid=42, interface='Ethernet0', state='absent'),
     'VLAN_MEMBER', 'Vlan42|Ethernet0', {'tagging_mode': 'tagged'}, None, {}),
    (sonic_interface_port, dict(interface='Ethernet0', enabled=False),
     'PORT', 'Ethernet0', {'speed': '10000', 'admin_status': 'up'}, {'speed': '10000', 'admin_status': 'down'}, {'interface': 'Ethernet0'}),
    (sonic_interface_port, dict(interface='QSFP1', description='uplink', speed='100G', fec='rs'),
     'PORT', 'Ethernet0', {'alias': 'QSFP1', 'speed': '10000'},
     {'alias': 'QSFP1', 'speed': '100000', 'description': 'uplink', 'fec': 'rs'}, {'interface': 'Ethernet0'}),
))
@pytest.mark.parametrize('check_mode', (True, False))
@pytest.mark.parametrize('already_applied', (True, False))
def test_module_changes_and_diff(fake_swsscommon, run_module, module, params, table, key, current, wanted, extra,
                                 check_mode, already_applied):
    if already_applied:
        current = wanted or {}
    if current:
        fake_swsscommon.seed({table: {key: current}})

    result = run_module(module, params, check_mode=check_mode)

    assert result['changed'] is (not already_applied)
    assert result['diff'] == {'before': current, 'after': wanted or {}}
    for k, v in extra.items():
        assert result[k] == v
    assert fake_swsscommon.connectors[0].connected
    if check_mode or already_applied:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.get_entry(table, key) == current
    else:
        assert ('set_entry', table, key, wanted) in fake_swsscommon.writes
        assert fake_swsscommon.get_entry(table, key) == (wanted or {})
        assert fake_swsscommon.has_entry(table, key) is (wanted is not None)


def test_sonic_interface_port_clears_description_through_appl_db(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': {'Ethernet0': {'alias': 'QSFP1', 'speed': '10000', 'description': 'old'}}})
    result = run_module(sonic_interface_port, dict(interface='QSFP1'))
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet0'
    assert fake_swsscommon.writes == [
        ('mod_entry', 'PORT', 'Ethernet0', {'description': ''}),
        ('set_entry', 'PORT', 'Ethernet0', {'alias': 'QSFP1', 'speed': '10000'}),
    ]


def test_sonic_interface_port_unknown_interface(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': {'Ethernet0': {'alias': 'QSFP1'}}})
    result = run_module(sonic_interface_port, dict(interface='QSFP9'), expect_failure=True)
    assert result['msg'] == 'could not find interface "QSFP9"'
    assert fake_swsscommon.writes == []


def test_sonic_interface_port_invalid_speed(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': {'Ethernet0': {}}})
    result = run_module(sonic_interface_port, dict(interface='Ethernet0', speed='fast'), expect_failure=True)
    assert result['msg'] == 'could not parse speed "fast"'


def test_vlan_rejects_bad_dhcp_server(fake_swsscommon, run_module):
    result = run_module(vlan, dict(vlanid=42, dhcp_servers=['falafel']), expect_failure=True)
    assert result['msg'] == 'dhcp server address falafel is not a valid IP address'
    assert fake_swsscommon.connectors == []


def test_vlan_member_requires_tagged_when_present(fake_swsscommon, run_module):
    result = run_module(vlan_member, dict(vlanid=42, interface='Ethernet0'), expect_failure=True)
    assert 'tagged' in result['msg']


def test_get_entry_table_joins_compound_keys(fake_swsscommon, run_module):
    fake_swsscommon.seed({'VLAN_MEMBER': {
        'Vlan42|Ethernet0': {'tagging_mode': 'tagged'},
        'Vlan42|Ethernet4': {'tagging_mode': 'untagged'},
    }})
    result = run_module(get_entry, dict(table='VLAN_MEMBER'))
    assert result['changed'] is False
    assert result['table'] == 'VLAN_MEMBER'
    assert 'key' not in result
    assert result['value'] == {
        'Vlan42|Ethernet0': {'tagging_mode': 'tagged'},
        'Vlan42|Ethernet4': {'tagging_mode': 'untagged'},
    }


def test_get_entry_key(fake_swsscommon, run_module):
    fake_swsscommon.seed({'DEVICE_METADATA': {'localhost': {'hostname': 'sonic'}}})
    result = run_module(get_entry, dict(table='DEVICE_METADATA', key='localhost'))
    assert result == {'changed': False, 'table': 'DEVICE_METADATA', 'key': 'localhost', 'value': {'hostname': 'sonic'}}
    assert run_module(get_entry, dict(table='DEVICE_METADATA', key='nope'))['value'] == {}


@pytest.mark.parametrize('module,params', (
    (vlan, dict(vlanid=42)),
    (vlan_member, dict(vlanid=42, interface='Ethernet0', tagged=True)),
    (sonic_interface_port, dict(interface='Ethernet0')),
    (get_entry, dict(table='PORT')),
))
def test_missing_swsscommon(monkeypatch, run_module, module, params):
    monkeypatch.setattr(config_db, 'HAS_SWSSCOMMON', False)
    monkeypatch.setattr(config_db, 'SWSSCOMMON_IMPORT_ERROR', 'Traceback: no swsscommon')
    result = run_module(module, params, expect_failure=True)
    assert 'swsscommon' in result['msg']
    assert result['exception'] == 'Traceback: no swsscommon'
