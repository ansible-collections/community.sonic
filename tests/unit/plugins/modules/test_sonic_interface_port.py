# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy

import pytest

from ansible_collections.community.sonic.plugins.modules import sonic_interface_port


PORT_TABLE = {
    'Ethernet0': {
        'alias': 'qsfp1',
        'speed': '10000',
    }
}


def test_set_description_by_alias():
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', description='foobar')
    assert changed, 'state was expected to change'
    assert new_state['description'] == 'foobar'


# Test clearing both by unsetting the field and by setting an empty string
@pytest.mark.parametrize('value', (None, ''))
def test_clear_description_by_alias(value):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0']['description'] = 'foobar'
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        port_table, interface='qsfp1', description=value)
    assert changed, 'state was expected to change'
    assert 'description' not in new_state


@pytest.mark.parametrize('value,expected', (
    ('1G', '1000'),
    ('100M', '100'),
    ('400G', '400000')))
def test_set_speed(value, expected):
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', speed=value)
    assert changed, 'state was expected to change'
    assert new_state['speed'] == expected, f"got speed {new_state['speed']}"


def test_set_invalid_speed():
    with pytest.raises(sonic_interface_port.InvalidSpeedError):
        sonic_interface_port.mutate_state(PORT_TABLE, interface='qsfp1', speed='foobar')


def test_set_enable_then_disable():
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', enabled=True)
    assert changed, 'state was expected to change'
    assert new_state['admin_status'] == 'up', f"got admin_status {new_state['admin_status']}"
    new_port_table = {'Ethernet0': new_state}
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        new_port_table, interface='qsfp1', enabled=False)
    assert changed, 'state was expected to change'
    assert new_state['admin_status'] == 'down', f"got admin_status {new_state['admin_status']}"


def test_set_fec():
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', fec='rs')
    assert changed, 'state was expected to change'
    assert new_state['fec'] == 'rs', f"got fec {new_state['fec']}"


def test_set_fec_implicit_downgrade():
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0']['speed'] = '100000'
    port_table['Ethernet0']['fec'] = 'rs'
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        port_table, interface='qsfp1', speed='40G')
    assert changed, 'state was expected to change'
    assert new_state['fec'] == 'none', f"got fec {new_state['fec']}"


# Regression test for https://github.com/ansible-collections/community.sonic/issues/17:
# disabling a port must not crash when CONFIG_DB has no admin_status field
# (factory default) and must be idempotent once the port is down.
@pytest.mark.parametrize('admin_status', (None, 'down', 'up'))
def test_disable_is_idempotent(admin_status):
    port_table = copy.deepcopy(PORT_TABLE)
    if admin_status is not None:
        port_table['Ethernet0']['admin_status'] = admin_status
    old_state, new_state, ifname, changed = sonic_interface_port.mutate_state(
        port_table, interface='qsfp1', enabled=False)
    assert old_state == port_table['Ethernet0']
    if admin_status == 'up':
        assert changed, 'state was expected to change'
        assert new_state['admin_status'] == 'down'
    else:
        # Absent admin_status means down in SONiC, so nothing changes.
        assert not changed, 'state was not expected to change'
        assert new_state == old_state
    _, repeated_state, _, repeated_changed = sonic_interface_port.mutate_state(
        {ifname: new_state}, interface=ifname, enabled=False)
    assert repeated_state == new_state
    assert not repeated_changed


@pytest.mark.parametrize('admin_status', (None, 'down', 'up'))
def test_enable_is_idempotent(admin_status):
    port_table = copy.deepcopy(PORT_TABLE)
    if admin_status is not None:
        port_table['Ethernet0']['admin_status'] = admin_status
    _, new_state, ifname, changed = sonic_interface_port.mutate_state(
        port_table, interface='qsfp1', enabled=True)
    assert changed == (admin_status != 'up')
    assert new_state['admin_status'] == 'up'
    _, repeated_state, _, repeated_changed = sonic_interface_port.mutate_state(
        {ifname: new_state}, interface=ifname, enabled=True)
    assert repeated_state == new_state
    assert not repeated_changed


@pytest.mark.parametrize('admin_status', (None, 'down', 'up'))
def test_omitted_enabled_leaves_admin_status(admin_status):
    port_table = copy.deepcopy(PORT_TABLE)
    if admin_status is not None:
        port_table['Ethernet0']['admin_status'] = admin_status
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        port_table, interface='qsfp1', description='uplink')
    assert changed
    assert new_state.get('admin_status') == admin_status


def test_description_without_configured_speed():
    port_table = {'Ethernet0': {'alias': 'qsfp1', 'fec': 'rs'}}
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        port_table, interface='qsfp1', description='uplink')
    assert changed
    assert new_state == {'alias': 'qsfp1', 'fec': 'rs', 'description': 'uplink'}
