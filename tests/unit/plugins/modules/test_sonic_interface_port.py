# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

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
    port_table = PORT_TABLE
    port_table['Ethernet0']['description'] = 'foobar'
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', description=value)
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
    try:
        sonic_interface_port.mutate_state(PORT_TABLE, interface='qsfp1', speed='foobar')
    except sonic_interface_port.InvalidSpeedError:
        pass


def test_set_enable_then_disable():
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', enabled=True)
    assert changed, 'state was expected to change'
    assert new_state['admin_status'] == 'up', f"got admin_status {new_state['admin_status']}"
    new_port_table = {'Ethernet0': new_state}
    _, new_state, _, changed = sonic_interface_port.mutate_state(
        new_port_table, interface='qsfp1', enabled=False)
    assert changed, 'state was expected to change'
    assert 'admin_status' not in new_state
