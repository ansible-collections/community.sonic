# -*- coding: utf-8 -*-
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import vlan_member


def test_build_vlan_member_entry_present():
    key, val = vlan_member.build_vlan_member_entry(vlanid=3360, interface='Ethernet90', state='present', tagged=True)
    assert key == 'Vlan3360|Ethernet90'
    assert val['tagging_mode'] == 'tagged'

    key, val = vlan_member.build_vlan_member_entry(vlanid=3360, interface='Ethernet90', state='present', tagged=False)
    assert key == 'Vlan3360|Ethernet90'
    assert val['tagging_mode'] == 'untagged'


def test_build_vlan_member_entry_absent():
    key, val = vlan_member.build_vlan_member_entry(vlanid=3360, interface='Ethernet90', state='absent', tagged=None)
    assert key == 'Vlan3360|Ethernet90'
    assert val is None


PORT_TABLE = {'Ethernet0': {'alias': 'QSFP1'}, 'Ethernet4': {'alias': 'QSFP2'}}


@pytest.mark.parametrize('check_mode', (True, False))
def test_portchannel_member(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'PORTCHANNEL': {'PortChannel3': {'admin_status': 'up'}}})
    result = run_module(vlan_member, dict(vlanid=100, interface='PortChannel3', tagged=True), check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'PortChannel3'
    assert result['diff'] == {'before': {}, 'after': {'tagging_mode': 'tagged'}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('set_entry', 'VLAN_MEMBER', 'Vlan100|PortChannel3', {'tagging_mode': 'tagged'})]
        assert fake_swsscommon.get_entry('VLAN_MEMBER', 'Vlan100|PortChannel3') == {'tagging_mode': 'tagged'}


def test_portchannel_member_is_idempotent(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'VLAN_MEMBER': {'Vlan100|PortChannel3': {'tagging_mode': 'tagged'}}})
    result = run_module(vlan_member, dict(vlanid=100, interface='PortChannel3', tagged=True))
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


def test_portchannel_member_remove(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE, 'VLAN_MEMBER': {'Vlan100|PortChannel3': {'tagging_mode': 'tagged'}}})
    result = run_module(vlan_member, dict(vlanid=100, interface='PortChannel3', state='absent'))
    assert result['changed'] is True
    assert fake_swsscommon.writes == [('set_entry', 'VLAN_MEMBER', 'Vlan100|PortChannel3', None)]


def test_port_alias(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(vlan_member, dict(vlanid=100, interface='QSFP2', tagged=False))
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet4'
    assert fake_swsscommon.get_entry('VLAN_MEMBER', 'Vlan100|Ethernet4') == {'tagging_mode': 'untagged'}


def test_unknown_port(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(vlan_member, dict(vlanid=100, interface='Ethernet99', tagged=True), expect_failure=True)
    assert result['msg'] == 'could not find interface "Ethernet99"'
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('interface', ('Vlan200', 'Loopback0'))
def test_non_member_interface_kinds_are_rejected(fake_swsscommon, run_module, interface):
    fake_swsscommon.seed({'PORT': PORT_TABLE})
    result = run_module(vlan_member, dict(vlanid=100, interface=interface, tagged=True), expect_failure=True)
    assert result['msg'] == 'interface "%s" cannot be a VLAN member; expected a port or PortChannel' % interface
    assert fake_swsscommon.writes == []
