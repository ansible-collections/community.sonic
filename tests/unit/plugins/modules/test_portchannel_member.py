# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=disallowed-name

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.modules import portchannel_member


PORTCHANNEL = {'admin_status': 'up', 'mtu': '9100', 'min_links': '1', 'lacp_key': 'auto'}
SEED = {
    'PORT': {
        'Ethernet0': {'alias': 'QSFP1', 'speed': '100000'},
        'Ethernet4': {'alias': 'QSFP2', 'speed': '100000'},
        'Ethernet8': {'alias': 'QSFP3', 'speed': '100000'},
    },
    'PORTCHANNEL': {'PortChannel3': PORTCHANNEL},
}


def test_build_entry():
    assert portchannel_member.build_portchannel_member_entry('PortChannel3', 'Ethernet0', 'present') == \
        ('PortChannel3|Ethernet0', {})
    assert portchannel_member.build_portchannel_member_entry('PortChannel3', 'Ethernet0', 'absent') == \
        ('PortChannel3|Ethernet0', None)


def test_membership_blockers():
    blockers = portchannel_member.membership_blockers
    assert blockers('PortChannel3', 'Ethernet0', ['PortChannel3'], [], [], []) is None
    assert blockers('PortChannel3', 'Ethernet0', ['PortChannel3'], ['PortChannel3|Ethernet0', 'PortChannel4|Ethernet4'],
                    ['Vlan10|Ethernet4'], ['Ethernet4', 'Ethernet4|10.0.0.1/31']) is None
    assert 'does not exist' in blockers('PortChannel3', 'Ethernet0', ['PortChannel4'], [], [], [])
    assert blockers('PortChannel3', 'Ethernet0', ['PortChannel3'], ['PortChannel4|Ethernet0'], [], []) == \
        'Ethernet0 is already a member of PortChannel4'
    assert blockers('PortChannel3', 'Ethernet0', ['PortChannel3'], [], ['Vlan10|Ethernet0', 'Vlan20|Ethernet0'], []) == \
        'Ethernet0 is a member of Vlan10, Vlan20; remove the VLAN membership first'
    assert 'IP address' in blockers('PortChannel3', 'Ethernet0', ['PortChannel3'], [], [], ['Ethernet0'])
    assert 'IP address' in blockers('PortChannel3', 'Ethernet0', ['PortChannel3'], [], [], ['Ethernet0|10.0.0.1/31'])


# -- end-to-end through the fake CONFIG_DB ----------------------------------------

@pytest.mark.parametrize('interface', ('Ethernet0', 'QSFP1'))
@pytest.mark.parametrize('check_mode', (True, False))
def test_add(fake_swsscommon, run_module, interface, check_mode):
    fake_swsscommon.seed(SEED)
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface=interface), check_mode=check_mode)
    assert result['changed'] is True
    assert result['portchannel'] == 'PortChannel3'
    assert result['interface'] == 'Ethernet0'
    assert result['diff'] == {'before': {}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert not fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')
    else:
        assert fake_swsscommon.writes == [('set_entry', 'PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0', {})]
        assert fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')
        assert fake_swsscommon.get_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0') == {}


@pytest.mark.parametrize('interface', ('Ethernet0', 'QSFP1'))
@pytest.mark.parametrize('check_mode', (True, False))
def test_add_is_idempotent(fake_swsscommon, run_module, interface, check_mode):
    fake_swsscommon.seed(SEED)
    fake_swsscommon.seed({'PORTCHANNEL_MEMBER': {'PortChannel3|Ethernet0': {}}})
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface=interface), check_mode=check_mode)
    assert result['changed'] is False
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(SEED)
    fake_swsscommon.seed({'PORTCHANNEL_MEMBER': {'PortChannel3|Ethernet0': {}, 'PortChannel3|Ethernet4': {}}})
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='QSFP1', state='absent'),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['interface'] == 'Ethernet0'
    assert result['diff'] == {'before': {}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')
    else:
        assert fake_swsscommon.writes == [('set_entry', 'PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0', None)]
        assert not fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet0')
    assert fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel3|Ethernet4')


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_absent_is_idempotent(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(SEED)
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='Ethernet0', state='absent'),
                        check_mode=check_mode)
    assert result['changed'] is False
    assert fake_swsscommon.writes == []


def test_remove_does_not_need_the_portchannel(fake_swsscommon, run_module):
    fake_swsscommon.seed({'PORT': SEED['PORT'], 'PORTCHANNEL_MEMBER': {'PortChannel9|Ethernet0': {}}})
    result = run_module(portchannel_member, dict(portchannel='PortChannel9', interface='Ethernet0', state='absent'))
    assert result['changed'] is True
    assert not fake_swsscommon.has_entry('PORTCHANNEL_MEMBER', 'PortChannel9|Ethernet0')


def test_unknown_port(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='QSFP9'), expect_failure=True)
    assert result['msg'] == 'could not find interface "QSFP9"'
    assert fake_swsscommon.writes == []


def test_portchannel_as_member_is_rejected(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='PortChannel4'), expect_failure=True)
    assert result['msg'] == 'could not find interface "PortChannel4"'


@pytest.mark.parametrize('check_mode', (True, False))
def test_missing_portchannel(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed({'PORT': SEED['PORT']})
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='Ethernet0'),
                        check_mode=check_mode, expect_failure=True)
    assert result['msg'] == 'PortChannel "PortChannel3" does not exist; create it with community.sonic.portchannel first'
    assert fake_swsscommon.writes == []


def test_member_of_other_portchannel(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    fake_swsscommon.seed({'PORTCHANNEL_MEMBER': {'PortChannel4|Ethernet0': {}}})
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='Ethernet0'), expect_failure=True)
    assert result['msg'] == 'Ethernet0 is already a member of PortChannel4'
    assert fake_swsscommon.writes == []


def test_vlan_member_is_rejected(fake_swsscommon, run_module):
    fake_swsscommon.seed(SEED)
    fake_swsscommon.seed({'VLAN_MEMBER': {'Vlan100|Ethernet0': {'tagging_mode': 'untagged'}}})
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='QSFP1'), expect_failure=True)
    assert result['msg'] == 'Ethernet0 is a member of Vlan100; remove the VLAN membership first'
    assert fake_swsscommon.writes == []


@pytest.mark.parametrize('l3_key', ('Ethernet0', 'Ethernet0|10.0.0.1/31'))
def test_port_with_ip_is_rejected(fake_swsscommon, run_module, l3_key):
    fake_swsscommon.seed(SEED)
    fake_swsscommon.seed({'INTERFACE': {l3_key: {}}})
    result = run_module(portchannel_member, dict(portchannel='PortChannel3', interface='Ethernet0'), expect_failure=True)
    assert result['msg'] == 'Ethernet0 has an IP address or VRF binding in INTERFACE; remove it first'
    assert fake_swsscommon.writes == []
