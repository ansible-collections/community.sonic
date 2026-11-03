# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy

import pytest

from ansible_collections.community.sonic.plugins.modules import interface_port


PORT_TABLE = {
    'Ethernet0': {
        'alias': 'qsfp1',
        'speed': '10000',
    }
}


def test_set_description_by_alias():
    _, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', description='foobar')
    assert changed, 'state was expected to change'
    assert new_state['description'] == 'foobar'


# Test clearing both by unsetting the field and by setting an empty string
@pytest.mark.parametrize('value', (None, ''))
def test_clear_description_by_alias(value):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0']['description'] = 'foobar'
    _, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', description=value)
    assert changed, 'state was expected to change'
    assert 'description' not in new_state


@pytest.mark.parametrize('value,expected', (
    ('1G', '1000'),
    ('100M', '100'),
    ('400G', '400000')))
def test_set_speed(value, expected):
    _, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', speed=value)
    assert changed, 'state was expected to change'
    assert new_state['speed'] == expected, f"got speed {new_state['speed']}"


def test_set_invalid_speed():
    with pytest.raises(interface_port.InvalidSpeedError):
        interface_port.mutate_state(PORT_TABLE, interface='qsfp1', speed='foobar')


def test_set_enable_then_disable():
    _, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', enabled=True)
    assert changed, 'state was expected to change'
    assert new_state['admin_status'] == 'up', f"got admin_status {new_state['admin_status']}"
    new_port_table = {'Ethernet0': new_state}
    _, new_state, _, changed = interface_port.mutate_state(
        new_port_table, interface='qsfp1', enabled=False)
    assert changed, 'state was expected to change'
    assert new_state['admin_status'] == 'down', f"got admin_status {new_state['admin_status']}"


def test_set_fec():
    _, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', fec='rs')
    assert changed, 'state was expected to change'
    assert new_state['fec'] == 'rs', f"got fec {new_state['fec']}"


def test_set_fec_implicit_downgrade():
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0']['speed'] = '100000'
    port_table['Ethernet0']['fec'] = 'rs'
    _, new_state, _, changed = interface_port.mutate_state(
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
    old_state, new_state, ifname, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', enabled=False)
    assert old_state == port_table['Ethernet0']
    if admin_status == 'up':
        assert changed, 'state was expected to change'
        assert new_state['admin_status'] == 'down'
    else:
        # Absent admin_status means down in SONiC, so nothing changes.
        assert not changed, 'state was not expected to change'
        assert new_state == old_state
    _, repeated_state, _, repeated_changed = interface_port.mutate_state(
        {ifname: new_state}, interface=ifname, enabled=False)
    assert repeated_state == new_state
    assert not repeated_changed


@pytest.mark.parametrize('admin_status', (None, 'down', 'up'))
def test_enable_is_idempotent(admin_status):
    port_table = copy.deepcopy(PORT_TABLE)
    if admin_status is not None:
        port_table['Ethernet0']['admin_status'] = admin_status
    _, new_state, ifname, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', enabled=True)
    assert changed == (admin_status != 'up')
    assert new_state['admin_status'] == 'up'
    _, repeated_state, _, repeated_changed = interface_port.mutate_state(
        {ifname: new_state}, interface=ifname, enabled=True)
    assert repeated_state == new_state
    assert not repeated_changed


@pytest.mark.parametrize('admin_status', (None, 'down', 'up'))
def test_omitted_enabled_leaves_admin_status(admin_status):
    port_table = copy.deepcopy(PORT_TABLE)
    if admin_status is not None:
        port_table['Ethernet0']['admin_status'] = admin_status
    _, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', description='uplink')
    assert changed
    assert new_state.get('admin_status') == admin_status


def test_description_without_configured_speed():
    port_table = {'Ethernet0': {'alias': 'qsfp1', 'fec': 'rs'}}
    _, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', description='uplink')
    assert changed
    assert new_state == {'alias': 'qsfp1', 'fec': 'rs', 'description': 'uplink'}


# Transceiver settings (https://github.com/ansible-collections/community.sonic/issues/21)

TRANSCEIVER_CASES = (
    # option, CONFIG_DB field, value, stored value, other value, other stored value
    ('laser_frequency', 'laser_freq', 194900, '194900', 193100, '193100'),
    ('tx_power', 'tx_power', -10, '-10.0', -8.5, '-8.5'),
    ('dom_polling', 'dom_polling', 'enabled', 'enabled', 'disabled', 'disabled'),
)

TRANSCEIVER_CLEAR = {
    'laser_frequency': 0,
    'tx_power': 0,
    'dom_polling': 'default',
}


@pytest.mark.parametrize('option,field,value,stored,other,other_stored', TRANSCEIVER_CASES)
def test_transceiver_set(option, field, value, stored, other, other_stored):
    _, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', **{option: value})
    assert changed, 'state was expected to change'
    assert new_state[field] == stored
    # Other fields are left alone
    assert new_state['speed'] == '10000'
    assert new_state['alias'] == 'qsfp1'


@pytest.mark.parametrize('option,field,value,stored,other,other_stored', TRANSCEIVER_CASES)
def test_transceiver_change(option, field, value, stored, other, other_stored):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0'][field] = stored
    _, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', **{option: other})
    assert changed, 'state was expected to change'
    assert new_state[field] == other_stored


@pytest.mark.parametrize('option,field,value,stored,other,other_stored', TRANSCEIVER_CASES)
def test_transceiver_unchanged(option, field, value, stored, other, other_stored):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0'][field] = stored
    old_state, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', **{option: value})
    assert not changed, 'state was not expected to change'
    assert new_state == old_state


@pytest.mark.parametrize('option,field,value,stored,other,other_stored', TRANSCEIVER_CASES)
def test_transceiver_omitted_leaves_field(option, field, value, stored, other, other_stored):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0'][field] = stored
    _, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', description='uplink')
    assert changed
    assert new_state[field] == stored


@pytest.mark.parametrize('option,field,value,stored,other,other_stored', TRANSCEIVER_CASES)
def test_transceiver_clear(option, field, value, stored, other, other_stored):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0'][field] = stored
    _, new_state, ifname, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', **{option: TRANSCEIVER_CLEAR[option]})
    assert changed, 'state was expected to change'
    assert field not in new_state
    # Clearing an already absent field is idempotent
    old_state, repeated_state, _, repeated_changed = interface_port.mutate_state(
        {ifname: new_state}, interface=ifname, **{option: TRANSCEIVER_CLEAR[option]})
    assert not repeated_changed, 'state was not expected to change'
    assert repeated_state == old_state


def test_transceiver_clear_absent_field_is_noop():
    old_state, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', laser_frequency=0, tx_power=0, dom_polling='default')
    assert not changed, 'state was not expected to change'
    assert new_state == old_state


def test_transceiver_set_all_then_idempotent():
    _, new_state, ifname, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', laser_frequency=194900, tx_power=-10, dom_polling='disabled')
    assert changed
    assert new_state['laser_freq'] == '194900'
    assert new_state['tx_power'] == '-10.0'
    assert new_state['dom_polling'] == 'disabled'
    _, repeated_state, _, repeated_changed = interface_port.mutate_state(
        {ifname: new_state}, interface=ifname, laser_frequency=194900, tx_power=-10, dom_polling='disabled')
    assert not repeated_changed
    assert repeated_state == new_state


# A TX power written by hand or by the CLI as "-10" rather than "-10.0" must
# compare equal numerically and must not be rewritten.
@pytest.mark.parametrize('stored', ('-10', '-10.0', '-10.00'))
def test_tx_power_numeric_comparison(stored):
    port_table = copy.deepcopy(PORT_TABLE)
    port_table['Ethernet0']['tx_power'] = stored
    old_state, new_state, _, changed = interface_port.mutate_state(
        port_table, interface='qsfp1', tx_power=-10.0)
    assert not changed
    assert new_state == old_state


def test_tx_power_fractional():
    _, new_state, _, changed = interface_port.mutate_state(
        PORT_TABLE, interface='qsfp1', tx_power=-7.5)
    assert changed
    assert new_state['tx_power'] == '-7.5'


def test_negative_laser_frequency_is_rejected():
    with pytest.raises(interface_port.InvalidValueError):
        interface_port.mutate_state(PORT_TABLE, interface='qsfp1', laser_frequency=-1)


# End-to-end through run_module with the fake CONFIG_DB: writes, idempotency,
# clearing and check mode.
SEED = {'PORT': {'Ethernet28': {'alias': 'etp8', 'speed': '100000', 'admin_status': 'up'}}}


def test_module_sets_transceiver_fields(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    params = dict(interface='etp8', laser_frequency=194900, tx_power=-10, dom_polling='enabled')
    result = run_module(interface_port, params)
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet28'
    entry = fake_swsscommon.get_entry('PORT', 'Ethernet28')
    assert entry['laser_freq'] == '194900'
    assert entry['tx_power'] == '-10.0'
    assert entry['dom_polling'] == 'enabled'
    assert entry['speed'] == '100000'
    assert entry['admin_status'] == 'up'
    assert result['diff']['after'] == entry

    repeated = run_module(interface_port, params)
    assert repeated['changed'] is False
    assert fake_swsscommon.get_entry('PORT', 'Ethernet28') == entry


def test_module_clears_transceiver_fields(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': {'Ethernet28': {
        'alias': 'etp8', 'speed': '100000', 'laser_freq': '194900', 'tx_power': '-10.0', 'dom_polling': 'disabled'}}})
    params = dict(interface='Ethernet28', laser_frequency=0, tx_power=0, dom_polling='default')
    result = run_module(interface_port, params)
    assert result['changed'] is True
    entry = fake_swsscommon.get_entry('PORT', 'Ethernet28')
    assert entry == {'alias': 'etp8', 'speed': '100000'}
    assert result['diff']['before']['laser_freq'] == '194900'
    assert result['diff']['after'] == entry

    repeated = run_module(interface_port, params)
    assert repeated['changed'] is False


def test_module_check_mode_does_not_write(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    result = run_module(interface_port, dict(interface='Ethernet28', laser_frequency=194900, dom_polling='disabled'),
                        check_mode=True)
    assert result['changed'] is True
    assert result['diff']['after']['laser_freq'] == '194900'
    assert result['diff']['after']['dom_polling'] == 'disabled'
    assert fake_swsscommon.writes == []
    assert fake_swsscommon.get_entry('PORT', 'Ethernet28') == SEED['PORT']['Ethernet28']


def test_module_rejects_invalid_dom_polling(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    result = run_module(interface_port, dict(interface='Ethernet28', dom_polling='maybe'), expect_failure=True)
    assert result['failed'] is True
    assert 'dom_polling' in result['msg']


def test_module_rejects_negative_laser_frequency(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    result = run_module(interface_port, dict(interface='Ethernet28', laser_frequency=-5), expect_failure=True)
    assert result['failed'] is True
    assert 'laser_frequency' in result['msg']
    assert fake_swsscommon.writes == []
