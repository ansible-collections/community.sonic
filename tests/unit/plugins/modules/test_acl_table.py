# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import acl
from ansible_collections.community.sonic.plugins.modules import acl_table


PORTS = {
    'PORT': {
        'Ethernet0': {'alias': 'QSFP1', 'speed': '100000'},
        'Ethernet4': {'alias': 'QSFP2', 'speed': '100000'},
        'Ethernet8': {'alias': 'QSFP3', 'speed': '100000'},
    },
}
CAP_COMBINED = {'ACL_STAGE_CAPABILITY_TABLE': {'INGRESS': {'action_list': 'PACKET_ACTION', 'supported_L3V4V6': 'true'}}}
CAP_SPLIT = {'ACL_STAGE_CAPABILITY_TABLE': {'INGRESS': {'action_list': 'PACKET_ACTION', 'supported_L3V4V6': 'false'}}}
CAP_OLD = {'ACL_STAGE_CAPABILITY_TABLE': {'INGRESS': {'action_list': 'PACKET_ACTION'}}}

COMBINED = {'type': 'L3V4V6', 'stage': 'ingress', 'policy_desc': 'Drop BGP', 'ports': ['Ethernet0', 'Ethernet4']}
SPLIT_V4 = dict(COMBINED, type='L3')
SPLIT_V6 = dict(COMBINED, type='L3V6')


class Orchagent(object):
    """Stands in for orchagent: marks tables Active (or Inactive for L3V4V6 when unsupported) when the module sleeps."""

    def __init__(self, fake, monkeypatch, l3v4v6=True):
        self.fake = fake
        self.l3v4v6 = l3v4v6
        self.now = 0.0
        monkeypatch.setattr(acl, 'monotonic', lambda: self.now)
        monkeypatch.setattr(acl, 'sleep', self.sleep)

    def sleep(self, seconds):
        self.now += seconds
        tables = self.fake.get_table('ACL_TABLE')
        for name in list(self.fake.store.get('ACL_TABLE_TABLE', {})):
            if name not in tables:
                del self.fake.store['ACL_TABLE_TABLE'][name]
        for name, entry in tables.items():
            status = 'Inactive' if entry.get('type') == 'L3V4V6' and not self.l3v4v6 else 'Active'
            self.fake.seed({'ACL_TABLE_TABLE': {name: {'status': status}}})


@pytest.fixture
def no_wait(monkeypatch):
    """Make waits time out instantly without any orchagent."""
    clock = {'now': 0.0}
    monkeypatch.setattr(acl, 'monotonic', lambda: clock['now'])

    def sleep(seconds):
        clock['now'] += max(seconds, 1)
    monkeypatch.setattr(acl, 'sleep', sleep)


def params(**kwargs):
    base = dict(name='BGP_CULL', ports=['QSFP1', 'Ethernet4'], description='Drop BGP')
    base.update(kwargs)
    return base


# -- pure logic ------------------------------------------------------------------

def test_ordered_ports_keeps_stored_order():
    assert acl_table.ordered_ports(['Ethernet4', 'Ethernet0'], ['Ethernet0', 'Ethernet8', 'Ethernet4']) == \
        ['Ethernet4', 'Ethernet0', 'Ethernet8']
    assert acl_table.ordered_ports([], ['Ethernet4', 'Ethernet0']) == ['Ethernet4', 'Ethernet0']
    assert acl_table.ordered_ports(['Ethernet4', 'Ethernet0'], []) == []


def test_build_table_entry_merges_into_current():
    current = {'type': 'L3', 'stage': 'ingress', 'policy_desc': 'old', 'ports': ['Ethernet4', 'Ethernet0']}
    assert acl_table.build_table_entry('L3V4V6', 'ingress', current) == dict(current, type='L3V4V6')
    assert acl_table.build_table_entry('L3', 'egress', current, ports=['Ethernet0'], description='new') == {
        'type': 'L3', 'stage': 'egress', 'policy_desc': 'new', 'ports': ['Ethernet0']}
    assert acl_table.build_table_entry('CTRLPLANE', 'ingress', {}, services=['SSH']) == {
        'type': 'CTRLPLANE', 'stage': 'ingress', 'services': ['SSH']}
    assert acl_table.build_table_entry('L3', 'ingress', {'type': 'L3', 'stage': 'ingress', 'ports': ['']}) == {
        'type': 'L3', 'stage': 'ingress', 'ports': []}


# -- creating ----------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create_combined_from_capability(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(PORTS).seed(CAP_COMBINED)
    orch = Orchagent(fake_swsscommon, pytest.MonkeyPatch())
    result = run_module(acl_table, params(), check_mode=check_mode)
    assert result['changed'] is True
    assert result['family_mode'] == 'combined'
    assert result['tables'] == ['BGP_CULL']
    assert result['ports'] == ['Ethernet0', 'Ethernet4']
    assert result['diff'] == {'before': {}, 'after': {'BGP_CULL': COMBINED}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [('mod_entry', 'ACL_TABLE', 'BGP_CULL', COMBINED)]
        assert fake_swsscommon.get_entry('ACL_TABLE', 'BGP_CULL') == COMBINED
        assert orch.now > 0  # waited for the status


@pytest.mark.parametrize('check_mode', (True, False))
def test_create_split_from_capability(fake_swsscommon, run_module, monkeypatch, check_mode):
    fake_swsscommon.seed(PORTS).seed(CAP_SPLIT)
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params(), check_mode=check_mode)
    assert result['changed'] is True
    assert result['family_mode'] == 'split'
    assert result['tables'] == ['BGP_CULL', 'BGP_CULL_v6']
    assert result['diff'] == {'before': {}, 'after': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.get_entry('ACL_TABLE', 'BGP_CULL') == SPLIT_V4
        assert fake_swsscommon.get_entry('ACL_TABLE', 'BGP_CULL_v6') == SPLIT_V6


def test_create_probe_succeeds(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(CAP_OLD)
    Orchagent(fake_swsscommon, monkeypatch, l3v4v6=True)
    result = run_module(acl_table, params())
    assert result['family_mode'] == 'combined'
    assert result['tables'] == ['BGP_CULL']
    assert fake_swsscommon.writes == [('mod_entry', 'ACL_TABLE', 'BGP_CULL', COMBINED)]


def test_create_probe_falls_back_to_split(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS)  # no capability table at all
    Orchagent(fake_swsscommon, monkeypatch, l3v4v6=False)
    result = run_module(acl_table, params())
    assert result['changed'] is True
    assert result['family_mode'] == 'split'
    assert result['tables'] == ['BGP_CULL', 'BGP_CULL_v6']
    assert result['diff'] == {'before': {}, 'after': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}}
    assert fake_swsscommon.writes == [
        ('mod_entry', 'ACL_TABLE', 'BGP_CULL', COMBINED),
        ('set_entry', 'ACL_TABLE', 'BGP_CULL', None),
        ('mod_entry', 'ACL_TABLE', 'BGP_CULL', SPLIT_V4),
        ('mod_entry', 'ACL_TABLE', 'BGP_CULL_v6', SPLIT_V6),
    ]
    assert fake_swsscommon.get_table('ACL_TABLE') == {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}


def test_create_probe_falls_back_when_no_status(fake_swsscommon, run_module, no_wait):
    # No orchagent at all: the probe times out, the split tables are written and their status check fails too.
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, params(status_timeout=3), expect_failure=True)
    assert 'BGP_CULL: no status reported, BGP_CULL_v6: no status reported' in result['msg']
    assert fake_swsscommon.get_table('ACL_TABLE') == {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}


def test_create_probe_in_check_mode_assumes_combined(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, params(), check_mode=True)
    assert result['family_mode'] == 'combined'
    assert result['changed'] is True
    assert fake_swsscommon.writes == []


def test_create_without_status_check_uses_split(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, params(status_timeout=0))
    assert result['family_mode'] == 'split'
    assert fake_swsscommon.get_table('ACL_TABLE') == {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}


def test_create_explicit_mode_ignores_capability(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(CAP_COMBINED)
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params(family_mode='split'))
    assert result['family_mode'] == 'split'
    assert fake_swsscommon.get_table('ACL_TABLE') == {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}


def test_create_explicit_type(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS)
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, dict(name='SSH_ONLY', type='CTRLPLANE', services=['SSH'], description='ssh'))
    assert result['family_mode'] is None
    assert result['tables'] == ['SSH_ONLY']
    assert 'ports' not in result
    assert fake_swsscommon.get_entry('ACL_TABLE', 'SSH_ONLY') == {
        'type': 'CTRLPLANE', 'stage': 'ingress', 'policy_desc': 'ssh', 'services': ['SSH']}


def test_create_with_empty_ports(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(CAP_COMBINED)
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params(ports=[]))
    assert result['ports'] == []
    assert result['diff']['after']['BGP_CULL']['ports'] == []
    # Reads back as [''] like on a real device and is still idempotent.
    assert fake_swsscommon.get_entry('ACL_TABLE', 'BGP_CULL')['ports'] == ['']
    result = run_module(acl_table, params(ports=[]))
    assert result['changed'] is False


def test_status_inactive_fails(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS)
    Orchagent(fake_swsscommon, monkeypatch, l3v4v6=False)
    result = run_module(acl_table, params(family_mode='combined'), expect_failure=True)
    assert result['msg'].startswith('orchagent did not accept ACL table BGP_CULL (BGP_CULL: Inactive)')
    assert fake_swsscommon.get_entry('ACL_TABLE', 'BGP_CULL') == COMBINED


def test_status_missing_fails(fake_swsscommon, run_module, no_wait):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, params(family_mode='split', status_timeout=2), expect_failure=True)
    assert 'BGP_CULL: no status reported, BGP_CULL_v6: no status reported' in result['msg']


# -- updating -----------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_idempotent(fake_swsscommon, run_module, monkeypatch, check_mode):
    fake_swsscommon.seed(PORTS).seed(CAP_SPLIT)
    fake_swsscommon.seed({'ACL_TABLE': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6},
                          'ACL_TABLE_TABLE': {'BGP_CULL': {'status': 'Active'}, 'BGP_CULL_v6': {'status': 'Active'}}})
    Orchagent(fake_swsscommon, monkeypatch)
    # Ports in another order, an alias and a duplicate are the same set.
    result = run_module(acl_table, params(ports=['Ethernet4', 'QSFP1', 'Ethernet0']), check_mode=check_mode)
    assert result['changed'] is False
    assert result['family_mode'] == 'split'
    assert result['diff']['before'] == result['diff']['after'] == {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}
    assert fake_swsscommon.writes == []


def test_existing_layout_wins_over_capability(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(CAP_COMBINED)
    fake_swsscommon.seed({'ACL_TABLE': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params())
    assert result['changed'] is False
    assert result['family_mode'] == 'split'


def test_repairs_missing_v6_table(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(CAP_COMBINED)
    fake_swsscommon.seed({'ACL_TABLE': {'BGP_CULL': SPLIT_V4}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params())
    assert result['changed'] is True
    assert result['family_mode'] == 'split'
    assert result['diff'] == {'before': {'BGP_CULL': SPLIT_V4}, 'after': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}}
    assert fake_swsscommon.writes == [('mod_entry', 'ACL_TABLE', 'BGP_CULL_v6', SPLIT_V6)]


@pytest.mark.parametrize('check_mode', (True, False))
def test_port_set_add_and_remove(fake_swsscommon, run_module, monkeypatch, check_mode):
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'BGP_CULL': COMBINED}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params(ports=['QSFP3', 'Ethernet4']), check_mode=check_mode)
    after = dict(COMBINED, ports=['Ethernet4', 'Ethernet8'])
    assert result['changed'] is True
    assert result['ports'] == ['Ethernet8', 'Ethernet4']
    assert result['diff'] == {'before': {'BGP_CULL': COMBINED}, 'after': {'BGP_CULL': after}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        # mod_entry, so orchagent updates the bindings instead of recreating the table.
        assert fake_swsscommon.writes == [('mod_entry', 'ACL_TABLE', 'BGP_CULL', after)]


def test_omitted_options_are_left_alone(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'BGP_CULL': COMBINED}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, dict(name='BGP_CULL'))
    assert result['changed'] is False
    assert 'ports' not in result
    result = run_module(acl_table, dict(name='BGP_CULL', description='new'))
    assert result['changed'] is True
    assert fake_swsscommon.get_entry('ACL_TABLE', 'BGP_CULL') == dict(COMBINED, policy_desc='new')


def test_switch_combined_to_split_and_back(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'BGP_CULL': COMBINED},
                                      'ACL_RULE': {'BGP_CULL|PERMIT': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD'}}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_table, params(family_mode='split'))
    assert result['changed'] is True
    assert result['diff'] == {'before': {'BGP_CULL': COMBINED}, 'after': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}}
    assert 'rules_removed' not in result
    # The rules of the IPv4 table survive the type change (orchagent recreates it).
    assert fake_swsscommon.has_entry('ACL_RULE', 'BGP_CULL|PERMIT')

    fake_swsscommon.seed({'ACL_RULE': {'BGP_CULL_v6|PERMIT': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD'}}})
    result = run_module(acl_table, params(family_mode='combined'))
    assert result['changed'] is True
    assert result['rules_removed'] == ['BGP_CULL_v6|PERMIT']
    assert result['diff'] == {'before': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}, 'after': {'BGP_CULL': COMBINED}}
    assert fake_swsscommon.get_table('ACL_TABLE') == {'BGP_CULL': COMBINED}
    assert fake_swsscommon.get_table('ACL_RULE') == {'BGP_CULL|PERMIT': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD'}}


def test_existing_other_type_needs_explicit_type(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'BGP_CULL': {'type': 'MIRROR', 'stage': 'ingress'}}})
    result = run_module(acl_table, params(), expect_failure=True)
    assert result['msg'] == ('ACL table "BGP_CULL" exists with type MIRROR, which is not a dual-stack policy; '
                             'pass type=MIRROR to manage it')


# -- removing ------------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_split_policy_with_rules(fake_swsscommon, run_module, check_mode):
    rules = {
        'BGP_CULL|PERMIT': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD'},
        'BGP_CULL_v6|PERMIT': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD', 'IP_TYPE': 'IPV6ANY'},
        'OTHER|PERMIT': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD'},
    }
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6,
                                                    'OTHER': {'type': 'L3', 'stage': 'ingress'}},
                                      'ACL_RULE': rules})
    result = run_module(acl_table, dict(name='BGP_CULL', state='absent'), check_mode=check_mode)
    assert result['changed'] is True
    assert result['tables'] == ['BGP_CULL', 'BGP_CULL_v6']
    assert result['family_mode'] == 'split'
    assert result['rules_removed'] == ['BGP_CULL_v6|PERMIT', 'BGP_CULL|PERMIT']
    assert result['diff'] == {'before': {'BGP_CULL': SPLIT_V4, 'BGP_CULL_v6': SPLIT_V6}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert fake_swsscommon.writes == [
            ('set_entry', 'ACL_RULE', 'BGP_CULL_v6|PERMIT', None),
            ('set_entry', 'ACL_RULE', 'BGP_CULL|PERMIT', None),
            ('set_entry', 'ACL_TABLE', 'BGP_CULL', None),
            ('set_entry', 'ACL_TABLE', 'BGP_CULL_v6', None),
        ]
        assert fake_swsscommon.get_table('ACL_TABLE') == {'OTHER': {'type': 'L3', 'stage': 'ingress'}}
        assert fake_swsscommon.get_table('ACL_RULE') == {'OTHER|PERMIT': rules['OTHER|PERMIT']}


def test_remove_absent_is_noop(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, dict(name='BGP_CULL', state='absent'))
    assert result['changed'] is False
    assert result['tables'] == []
    assert result['diff'] == {'before': {}, 'after': {}}
    assert fake_swsscommon.writes == []


def test_remove_explicit_type(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'SSH_ONLY': {'type': 'CTRLPLANE', 'stage': 'ingress'}}})
    result = run_module(acl_table, dict(name='SSH_ONLY', type='CTRLPLANE', state='absent'))
    assert result['changed'] is True
    assert fake_swsscommon.get_table('ACL_TABLE') == {}


# -- failures -----------------------------------------------------------------------------

def test_unknown_port(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, params(ports=['QSFP9']), expect_failure=True)
    assert result['msg'] == 'could not find interface "QSFP9"'
    assert fake_swsscommon.writes == []


def test_vlan_cannot_be_bound(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_table, params(ports=['Vlan100']), expect_failure=True)
    assert result['msg'] == 'ACL tables can only be bound to Ethernet ports and PortChannels, not "Vlan100"'


def test_type_and_family_mode_are_exclusive(fake_swsscommon, run_module):
    result = run_module(acl_table, params(type='L3', family_mode='split'), expect_failure=True)
    assert 'mutually exclusive' in result['msg']
