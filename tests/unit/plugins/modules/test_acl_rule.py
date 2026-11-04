# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import acl
from ansible_collections.community.sonic.plugins.modules import acl_rule


PORTS = {'PORT': {'Ethernet0': {'alias': 'QSFP1'}, 'Ethernet4': {'alias': 'QSFP2'}}}
COMBINED = {'ACL_TABLE': {'BGP_CULL': {'type': 'L3V4V6', 'stage': 'ingress', 'ports': ['Ethernet0']}}}
SPLIT = {'ACL_TABLE': {'BGP_CULL': {'type': 'L3', 'stage': 'ingress', 'ports': ['Ethernet0']},
                       'BGP_CULL_v6': {'type': 'L3V6', 'stage': 'ingress', 'ports': ['Ethernet0']}}}

BGP_RULES = [
    dict(name='DROP_BGP_DST', priority=9999, protocol='tcp', l4_dst_port=179, action='drop'),
    dict(name='DROP_BGP_SRC', priority=9998, protocol='tcp', l4_src_port='179', action='drop'),
    dict(name='PERMIT_ALL', priority=1, action='forward'),
]
BGP_ENTRIES = {
    'DROP_BGP_DST': {'PRIORITY': '9999', 'IP_PROTOCOL': '6', 'L4_DST_PORT': '179', 'PACKET_ACTION': 'DROP'},
    'DROP_BGP_SRC': {'PRIORITY': '9998', 'IP_PROTOCOL': '6', 'L4_SRC_PORT': '179', 'PACKET_ACTION': 'DROP'},
    'PERMIT_ALL': {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD'},
}


def rule(**kwargs):
    base = dict(name='R', priority=10, action='forward')
    base.update(kwargs)
    return base


class Orchagent(object):
    """Marks every rule Active, except rules with a field in ``reject``, when the module sleeps."""

    def __init__(self, fake, monkeypatch, reject=()):
        self.fake = fake
        self.reject = reject
        self.now = 0.0
        self.sleeps = []
        monkeypatch.setattr(acl, 'monotonic', lambda: self.now)
        monkeypatch.setattr(acl, 'sleep', self.sleep)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        for key, entry in self.fake.get_table('ACL_RULE').items():
            status = 'Inactive' if any(f in entry for f in self.reject) else 'Active'
            self.fake.seed({'ACL_RULE_TABLE': {key: {'status': status}}})


# -- pure logic: fields ----------------------------------------------------------------

@pytest.mark.parametrize('options,expected', (
    (dict(protocol='tcp', l4_dst_port='179', action='drop'),
     {'IP_PROTOCOL': '6', 'L4_DST_PORT': '179', 'PACKET_ACTION': 'DROP'}),
    (dict(protocol='17', l4_src_port='1024-65535'),
     {'IP_PROTOCOL': '17', 'L4_SRC_PORT_RANGE': '1024-65535', 'PACKET_ACTION': 'FORWARD'}),
    (dict(protocol='UDP', dscp=46, vlan_id=100),
     {'IP_PROTOCOL': '17', 'DSCP': '46', 'VLAN_ID': '100', 'PACKET_ACTION': 'FORWARD'}),
    (dict(tcp_flags=['syn', 'ACK']), {'TCP_FLAGS': '0x12/0x12', 'PACKET_ACTION': 'FORWARD'}),
    (dict(tcp_flags=['0x02/0x3f']), {'TCP_FLAGS': '0x02/0x3f', 'PACKET_ACTION': 'FORWARD'}),
    (dict(ether_type='arp'), {'ETHER_TYPE': '2054', 'PACKET_ACTION': 'FORWARD'}),
    (dict(ether_type='0x88CC'), {'ETHER_TYPE': '35020', 'PACKET_ACTION': 'FORWARD'}),
    (dict(ip_type='NON_IP'), {'IP_TYPE': 'NON_IP', 'PACKET_ACTION': 'FORWARD'}),
    (dict(action='redirect', redirect='10.0.0.1@Ethernet4'), {'REDIRECT_ACTION': '10.0.0.1@Ethernet4'}),
    (dict(action=None, fields={'MIRROR_INGRESS_ACTION': 'everflow', 'DSCP': 8}),
     {'MIRROR_INGRESS_ACTION': 'everflow', 'DSCP': '8'}),
    (dict(fields={'PACKET_ACTION': 'DROP', 'TC': '3'}), {'PACKET_ACTION': 'FORWARD', 'TC': '3'}),
    (dict(in_ports=['Ethernet4', 'Ethernet0', 'Ethernet4']),
     {'IN_PORTS': 'Ethernet4,Ethernet0', 'PACKET_ACTION': 'FORWARD'}),
))
def test_build_rule_entry_agnostic(options, expected):
    entry, family = acl_rule.build_rule_entry(rule(**options))
    expected = dict(expected, PRIORITY='10')
    assert entry == expected
    assert family is None


@pytest.mark.parametrize('options,expected,family', (
    (dict(src_ip='10.0.0.1'), {'SRC_IP': '10.0.0.1/32'}, 'v4'),
    (dict(dst_ip='192.0.2.0/24'), {'DST_IP': '192.0.2.0/24'}, 'v4'),
    (dict(src_ipv6='2001:DB8:0:0::1'), {'SRC_IPV6': '2001:db8::1/128'}, 'v6'),
    (dict(dst_ipv6='2001:db8::/32'), {'DST_IPV6': '2001:db8::/32'}, 'v6'),
    (dict(icmp_type=8, icmp_code=0), {'IP_PROTOCOL': '1', 'ICMP_TYPE': '8', 'ICMP_CODE': '0'}, 'v4'),
    (dict(protocol='icmp', icmp_type=8), {'IP_PROTOCOL': '1', 'ICMP_TYPE': '8'}, 'v4'),
    (dict(icmpv6_type=128), {'IP_PROTOCOL': '58', 'ICMPV6_TYPE': '128'}, 'v6'),
    (dict(protocol='icmp', icmpv6_type=135, icmpv6_code=0),
     {'IP_PROTOCOL': '58', 'ICMPV6_TYPE': '135', 'ICMPV6_CODE': '0'}, 'v6'),
    (dict(protocol='icmpv6'), {'IP_PROTOCOL': '58'}, 'v6'),
    (dict(protocol='icmp'), {'IP_PROTOCOL': '1'}, None),
    (dict(ether_type='ipv4'), {'ETHER_TYPE': '2048'}, 'v4'),
    (dict(ether_type='ipv6', protocol='tcp'), {'ETHER_TYPE': '34525', 'IP_PROTOCOL': '6'}, 'v6'),
    (dict(ip_type='IPV4ANY'), {'IP_TYPE': 'IPV4ANY'}, 'v4'),
    (dict(ip_type='ARP_REQUEST'), {'IP_TYPE': 'ARP_REQUEST'}, 'v4'),
    (dict(ip_type='IPV6ANY'), {'IP_TYPE': 'IPV6ANY'}, 'v6'),
    (dict(ip_type='IP'), {'IP_TYPE': 'IP'}, None),
))
def test_build_rule_entry_family(options, expected, family):
    entry, got = acl_rule.build_rule_entry(rule(**options))
    assert entry == dict(expected, PRIORITY='10', PACKET_ACTION='FORWARD')
    assert got == family


def test_build_rule_entry_resolves_in_ports():
    entry, _family = acl_rule.build_rule_entry(rule(in_ports=['QSFP1', 'Ethernet4']),
                                               resolve_port={'QSFP1': 'Ethernet0', 'Ethernet4': 'Ethernet4'}.get)
    assert entry['IN_PORTS'] == 'Ethernet0,Ethernet4'


@pytest.mark.parametrize('options,message', (
    (dict(priority=None), 'priority is required'),
    (dict(priority=1000000), 'priority must be between 0 and 999999'),
    (dict(action=None), 'an action is required'),
    (dict(action='redirect'), 'action=redirect needs a redirect target'),
    (dict(protocol='bgp'), 'unknown protocol "bgp"'),
    (dict(protocol='256'), 'unknown protocol "256"'),
    (dict(ether_type='0x10000'), 'invalid ether_type "0x10000"'),
    (dict(ether_type='ip'), 'invalid ether_type "ip"'),
    (dict(src_ip='2001:db8::1'), 'src_ip "2001:db8::1" is not an IPv4 address or prefix'),
    (dict(dst_ipv6='10.0.0.1'), 'dst_ipv6 "10.0.0.1" is not an IPv6 address or prefix'),
    (dict(src_ip='falafel'), 'src_ip "falafel" is not a valid IPv4 address or prefix'),
    (dict(l4_dst_port='70000'), 'l4_dst_port "70000" is not a port number or a low-high range'),
    (dict(l4_src_port='200-100'), 'l4_src_port "200-100" is not a port number or a low-high range'),
    (dict(tcp_flags=['syn', 'nope']), 'unknown TCP flag "nope"'),
    (dict(tcp_flags=['syn'], protocol='udp'), 'tcp_flags need protocol tcp'),
    (dict(dscp=64), 'dscp must be between 0 and 63'),
    (dict(vlan_id=0), 'vlan_id must be between 1 and 4094'),
    (dict(icmp_type=256), 'icmp_type must be between 0 and 255'),
    (dict(icmp_type=8, protocol='tcp'), 'icmp_type/icmp_code need protocol icmp'),
    (dict(icmpv6_type=128, protocol='udp'), 'icmpv6_type/icmpv6_code need protocol icmpv6'),
    (dict(src_ip='10.0.0.0/8', dst_ipv6='2001:db8::/32'), 'mixes IPv4 and IPv6 match fields'),
    (dict(icmp_type=8, icmpv6_type=128), 'mixes IPv4 and IPv6 match fields'),
    (dict(ether_type='ipv4', ip_type='IPV6ANY'), 'mixes IPv4 and IPv6 match fields'),
))
def test_build_rule_entry_errors(options, message):
    with pytest.raises(acl_rule.RuleError) as excinfo:
        acl_rule.build_rule_entry(rule(**options))
    assert str(excinfo.value).startswith('rule "R": ' + message)


# -- pure logic: routing -------------------------------------------------------------------

def combined_entries():
    expected = dict(('BGP_CULL|' + k, v) for k, v in BGP_ENTRIES.items())
    expected['BGP_CULL|PERMIT_ALL'] = dict(BGP_ENTRIES['PERMIT_ALL'], IP_TYPE='IP')
    return expected


def split_entries():
    expected = dict(('BGP_CULL|' + k, v) for k, v in BGP_ENTRIES.items())
    expected['BGP_CULL|PERMIT_ALL'] = dict(BGP_ENTRIES['PERMIT_ALL'], IP_TYPE='IPV4ANY')
    expected.update(('BGP_CULL_v6|' + k, dict(v, IP_TYPE='IPV6ANY')) for k, v in BGP_ENTRIES.items())
    return expected


def test_route_rules_combined():
    desired = acl_rule.route_rules(BGP_RULES, 'combined', {'BGP_CULL': 'L3V4V6'})
    assert desired == combined_entries()


@pytest.mark.parametrize('table_type,extra', (
    ('L3', {'IP_TYPE': 'IPV4ANY'}),
    ('L3V6', {'IP_TYPE': 'IPV6ANY'}),
    ('L3V4V6', {'IP_TYPE': 'IP'}),
    ('MIRROR', {}),
))
def test_rules_without_match_get_a_default_match(table_type, extra):
    # orchagent rejects rules without a match field; a bare permit/deny gets what acl-loader adds.
    desired = acl_rule.route_rules([rule(action='drop'), rule(name='V', vlan_id=5)], None, {'X': table_type})
    assert desired['X|R'] == dict({'PRIORITY': '10', 'PACKET_ACTION': 'DROP'}, **extra)
    # A rule with a match of its own is left alone (an L3V6 table still pins family-less rules to IPv6).
    assert desired['X|V'].get('IP_TYPE') == ('IPV6ANY' if table_type == 'L3V6' else None)
    desired = acl_rule.route_rules([rule(action='redirect', redirect='Ethernet0')], None, {'X': table_type})
    assert desired['X|R'] == dict({'PRIORITY': '10', 'REDIRECT_ACTION': 'Ethernet0'}, **extra)
    desired = acl_rule.route_rules([rule(ip_type='ANY')], None, {'X': table_type})
    assert desired['X|R'] == {'PRIORITY': '10', 'PACKET_ACTION': 'FORWARD', 'IP_TYPE': 'ANY'}


def test_route_rules_combined_icmp_stays_ipv4():
    desired = acl_rule.route_rules([rule(protocol='icmp')], 'combined', {'X': 'L3V4V6'})
    assert desired['X|R']['IP_PROTOCOL'] == '1'


def test_route_rules_split_duplicates_agnostic_rules():
    tables = {'BGP_CULL': 'L3', 'BGP_CULL_v6': 'L3V6'}
    rules = BGP_RULES + [
        rule(name='V4', src_ip='10.0.0.0/8', action='drop'),
        rule(name='V6', src_ipv6='2001:db8::/32', action='drop'),
        rule(name='PING', protocol='icmp', ip_type='IP'),
    ]
    desired = acl_rule.route_rules(rules, 'split', tables)
    expected = split_entries()
    expected['BGP_CULL|V4'] = {'PRIORITY': '10', 'SRC_IP': '10.0.0.0/8', 'PACKET_ACTION': 'DROP'}
    expected['BGP_CULL_v6|V6'] = {'PRIORITY': '10', 'SRC_IPV6': '2001:db8::/32', 'PACKET_ACTION': 'DROP'}
    # protocol=icmp becomes ICMPv6 in the IPv6 table; an explicit ip_type is kept.
    expected['BGP_CULL|PING'] = {'PRIORITY': '10', 'IP_PROTOCOL': '1', 'IP_TYPE': 'IP', 'PACKET_ACTION': 'FORWARD'}
    expected['BGP_CULL_v6|PING'] = {'PRIORITY': '10', 'IP_PROTOCOL': '58', 'IP_TYPE': 'IP', 'PACKET_ACTION': 'FORWARD'}
    assert desired == expected


def test_route_rules_split_missing_v6_table():
    with pytest.raises(acl_rule.RuleError) as excinfo:
        acl_rule.route_rules([rule(src_ipv6='2001:db8::1')], 'split', {'X': 'L3'})
    assert 'the IPv6 table of split policy "X" does not exist' in str(excinfo.value)


@pytest.mark.parametrize('table_type,options,message', (
    ('L3', dict(src_ipv6='2001:db8::1'), 'has IPv6 match fields but table "X" is of type L3'),
    ('L3V6', dict(dst_ip='10.0.0.1'), 'has IPv4 match fields but table "X" is of type L3V6'),
))
def test_route_rules_single_table_family_mismatch(table_type, options, message):
    with pytest.raises(acl_rule.RuleError) as excinfo:
        acl_rule.route_rules([rule(**options)], None, {'X': table_type})
    assert message in str(excinfo.value)


def test_route_rules_single_table_leaves_entries_alone():
    desired = acl_rule.route_rules([rule(protocol='icmp')], None, {'X': 'L3V6'})
    # A lone L3V6 table is still an IPv6 table: ICMP means ICMPv6 and family-less rules match IPv6 only.
    assert desired == {'X|R': {'PRIORITY': '10', 'IP_PROTOCOL': '58', 'IP_TYPE': 'IPV6ANY', 'PACKET_ACTION': 'FORWARD'}}
    desired = acl_rule.route_rules([rule(fields={'MIRROR_INGRESS_ACTION': 's'}, action=None)], None, {'X': 'MIRROR'})
    assert desired == {'X|R': {'PRIORITY': '10', 'MIRROR_INGRESS_ACTION': 's'}}


def test_route_rules_duplicate_name():
    with pytest.raises(acl_rule.RuleError) as excinfo:
        acl_rule.route_rules([rule(), rule()], 'combined', {'X': 'L3V4V6'})
    assert str(excinfo.value) == 'rule "R": listed more than once'


# -- module runs ------------------------------------------------------------------------------

@pytest.mark.parametrize('check_mode', (True, False))
def test_create_combined(fake_swsscommon, run_module, monkeypatch, check_mode):
    fake_swsscommon.seed(PORTS).seed(COMBINED)
    orch = Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=BGP_RULES, exclusive=True), check_mode=check_mode)
    expected = combined_entries()
    assert result['changed'] is True
    assert result['tables'] == ['BGP_CULL']
    assert result['family_mode'] == 'combined'
    assert result['rules'] == sorted(expected)
    assert result['removed'] == []
    assert result['diff'] == {'before': {}, 'after': expected}
    if check_mode:
        assert fake_swsscommon.writes == []
        assert orch.now == 0
    else:
        assert fake_swsscommon.get_table('ACL_RULE') == expected
        assert orch.now > 0


@pytest.mark.parametrize('check_mode', (True, False))
def test_create_split(fake_swsscommon, run_module, monkeypatch, check_mode):
    fake_swsscommon.seed(PORTS).seed(SPLIT)
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=BGP_RULES), check_mode=check_mode)
    expected = split_entries()
    assert result['changed'] is True
    assert result['tables'] == ['BGP_CULL', 'BGP_CULL_v6']
    assert result['family_mode'] == 'split'
    assert result['diff'] == {'before': {}, 'after': expected}
    if not check_mode:
        assert fake_swsscommon.get_table('ACL_RULE') == expected


def test_idempotent_and_exclusive(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(SPLIT)
    orch = Orchagent(fake_swsscommon, monkeypatch)
    run_module(acl_rule, dict(table='BGP_CULL', rules=BGP_RULES))
    fake_swsscommon.connectors[:] = []
    stray = {'BGP_CULL|OLD': {'PRIORITY': '5', 'PACKET_ACTION': 'DROP'}, 'OTHER|X': {'PRIORITY': '5', 'PACKET_ACTION': 'DROP'}}
    fake_swsscommon.seed({'ACL_RULE': stray})
    orch.sleeps[:] = []

    result = run_module(acl_rule, dict(table='BGP_CULL', rules=BGP_RULES))
    assert result['changed'] is False
    assert result['diff']['before'] == result['diff']['after']
    assert fake_swsscommon.writes == []
    # Unchanged rules keep their Active status, so there is nothing to wait for.
    assert orch.sleeps == []

    result = run_module(acl_rule, dict(table='BGP_CULL', rules=BGP_RULES, exclusive=True), check_mode=True)
    assert result['changed'] is True
    assert result['removed'] == ['BGP_CULL|OLD']
    assert result['diff']['before']['BGP_CULL|OLD'] == stray['BGP_CULL|OLD']
    assert 'BGP_CULL|OLD' not in result['diff']['after']
    assert fake_swsscommon.writes == []

    result = run_module(acl_rule, dict(table='BGP_CULL', rules=BGP_RULES, exclusive=True))
    assert result['changed'] is True
    assert fake_swsscommon.writes == [('set_entry', 'ACL_RULE', 'BGP_CULL|OLD', None)]
    assert 'OTHER|X' in fake_swsscommon.get_table('ACL_RULE')


def test_modify_rule(fake_swsscommon, run_module, monkeypatch):
    before = dict(BGP_ENTRIES['PERMIT_ALL'], IP_TYPE='IP')
    fake_swsscommon.seed(PORTS).seed(COMBINED).seed({'ACL_RULE': {'BGP_CULL|PERMIT_ALL': before}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[dict(name='PERMIT_ALL', priority=2, action='drop')]))
    after = {'PRIORITY': '2', 'PACKET_ACTION': 'DROP', 'IP_TYPE': 'IP'}
    assert result['changed'] is True
    assert result['diff'] == {'before': {'BGP_CULL|PERMIT_ALL': before}, 'after': {'BGP_CULL|PERMIT_ALL': after}}
    assert fake_swsscommon.writes == [('set_entry', 'ACL_RULE', 'BGP_CULL|PERMIT_ALL', after)]


def test_update_waits_for_a_fresh_status(fake_swsscommon, run_module, monkeypatch):
    """Changing an Active rule into one orchagent rejects fails, instead of passing on the previous Active."""
    before = dict(BGP_ENTRIES['PERMIT_ALL'], IP_TYPE='IP')
    fake_swsscommon.seed(PORTS).seed(COMBINED).seed({
        'ACL_RULE': {'BGP_CULL|PERMIT_ALL': before}, 'ACL_RULE_TABLE': {'BGP_CULL|PERMIT_ALL': {'status': 'Active'}}})
    orch = Orchagent(fake_swsscommon, monkeypatch, reject=('DSCP',))
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[dict(name='PERMIT_ALL', priority=1, action='forward', dscp=46)]),
                        expect_failure=True)
    assert result['msg'].startswith('orchagent did not accept ACL rule in BGP_CULL (BGP_CULL|PERMIT_ALL: Inactive)')
    assert orch.sleeps  # the old status was discarded and orchagent's answer awaited
    assert fake_swsscommon.writes == [
        ('set_entry', 'ACL_RULE', 'BGP_CULL|PERMIT_ALL', {'PRIORITY': '1', 'PACKET_ACTION': 'FORWARD', 'DSCP': '46'}),
        ('set_entry', 'ACL_RULE_TABLE', 'BGP_CULL|PERMIT_ALL', None),
    ]


def test_update_discards_a_stale_inactive_status(fake_swsscommon, run_module, monkeypatch):
    """Fixing a rejected rule succeeds, instead of failing on the previous Inactive; other rules are left alone."""
    bad = {'PRIORITY': '5', 'PACKET_ACTION': 'DROP', 'DSCP': '46'}
    permit = dict(BGP_ENTRIES['PERMIT_ALL'], IP_TYPE='IP')
    fake_swsscommon.seed(PORTS).seed(COMBINED).seed({
        'ACL_RULE': {'BGP_CULL|BAD': bad, 'BGP_CULL|PERMIT_ALL': permit},
        'ACL_RULE_TABLE': {'BGP_CULL|BAD': {'status': 'Inactive'}, 'BGP_CULL|PERMIT_ALL': {'status': 'Active'}}})
    orch = Orchagent(fake_swsscommon, monkeypatch, reject=('DSCP',))
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[
        dict(name='BAD', priority=5, protocol='udp', action='drop'), dict(name='PERMIT_ALL', priority=1, action='forward')]))
    fixed = {'PRIORITY': '5', 'PACKET_ACTION': 'DROP', 'IP_PROTOCOL': '17'}
    assert result['changed'] is True
    assert result['diff']['after']['BGP_CULL|BAD'] == fixed
    assert orch.sleeps
    # Only the changed rule is written and only its status is cleared.
    assert fake_swsscommon.writes == [('set_entry', 'ACL_RULE', 'BGP_CULL|BAD', fixed),
                                      ('set_entry', 'ACL_RULE_TABLE', 'BGP_CULL|BAD', None)]
    assert fake_swsscommon.get_entry('ACL_RULE_TABLE', 'BGP_CULL|BAD') == {'status': 'Active'}


def test_update_in_check_mode_keeps_the_status(fake_swsscommon, run_module, monkeypatch):
    before = dict(BGP_ENTRIES['PERMIT_ALL'], IP_TYPE='IP')
    fake_swsscommon.seed(PORTS).seed(COMBINED).seed({
        'ACL_RULE': {'BGP_CULL|PERMIT_ALL': before}, 'ACL_RULE_TABLE': {'BGP_CULL|PERMIT_ALL': {'status': 'Active'}}})
    orch = Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[dict(name='PERMIT_ALL', priority=2, action='drop')]),
                        check_mode=True)
    assert result['changed'] is True
    assert fake_swsscommon.writes == []
    assert orch.sleeps == []


def test_exclusive_with_no_rules_empties_the_tables(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS).seed(SPLIT).seed({'ACL_RULE': {
        'BGP_CULL|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'},
        'BGP_CULL_v6|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'},
        'OTHER|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'}}})
    result = run_module(acl_rule, dict(table='BGP_CULL', exclusive=True))
    assert result['changed'] is True
    assert result['removed'] == ['BGP_CULL_v6|A', 'BGP_CULL|A']
    assert result['rules'] == []
    assert list(fake_swsscommon.get_table('ACL_RULE')) == ['OTHER|A']


@pytest.mark.parametrize('check_mode', (True, False))
def test_remove_rules(fake_swsscommon, run_module, check_mode):
    fake_swsscommon.seed(PORTS).seed(SPLIT).seed({'ACL_RULE': {
        'BGP_CULL|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'},
        'BGP_CULL_v6|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'},
        'BGP_CULL|B': {'PRIORITY': '2', 'PACKET_ACTION': 'DROP'}}})
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[dict(name='A'), dict(name='NOPE')], state='absent'),
                        check_mode=check_mode)
    assert result['changed'] is True
    assert result['removed'] == ['BGP_CULL_v6|A', 'BGP_CULL|A']
    assert result['diff'] == {'before': {'BGP_CULL|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'},
                                         'BGP_CULL_v6|A': {'PRIORITY': '1', 'PACKET_ACTION': 'DROP'}}, 'after': {}}
    if check_mode:
        assert fake_swsscommon.writes == []
    else:
        assert list(fake_swsscommon.get_table('ACL_RULE')) == ['BGP_CULL|B']
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[dict(name='NOPE')], state='absent'))
    assert result['changed'] is False


def test_lone_l3_table_is_single(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed({'ACL_TABLE': {'DATAACL': {'type': 'L3', 'stage': 'ingress'}}})
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_rule, dict(table='DATAACL', rules=[rule()]))
    assert result['family_mode'] is None
    assert result['tables'] == ['DATAACL']
    assert fake_swsscommon.get_table('ACL_RULE') == {'DATAACL|R': {'PRIORITY': '10', 'PACKET_ACTION': 'FORWARD', 'IP_TYPE': 'IPV4ANY'}}


def test_in_ports_alias(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(COMBINED)
    Orchagent(fake_swsscommon, monkeypatch)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[rule(in_ports=['QSFP2'])]))
    assert result['diff']['after']['BGP_CULL|R']['IN_PORTS'] == 'Ethernet4'
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[rule(in_ports=['QSFP9'])]), expect_failure=True)
    assert result['msg'] == 'could not find interface "QSFP9"'


def test_status_inactive_fails(fake_swsscommon, run_module, monkeypatch):
    fake_swsscommon.seed(PORTS).seed(SPLIT)
    Orchagent(fake_swsscommon, monkeypatch, reject=('TCP_FLAGS',))
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[rule(name='SYN', tcp_flags=['syn']), rule(name='OK')]),
                        expect_failure=True)
    assert result['msg'] == ('orchagent did not accept ACL rules in BGP_CULL, BGP_CULL_v6 (BGP_CULL_v6|SYN: Inactive, '
                             'BGP_CULL|SYN: Inactive); see "show logging" for the reason and STATE_DB ACL_RULE_TABLE for the status')


def test_status_check_can_be_disabled(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS).seed(COMBINED)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[rule()], status_timeout=0))
    assert result['changed'] is True


def test_missing_table(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[rule()]), expect_failure=True)
    assert result['msg'] == 'ACL table "BGP_CULL" does not exist; create it with community.sonic.acl_table first'
    assert fake_swsscommon.writes == []


def test_invalid_rule_fails_before_writing(fake_swsscommon, run_module):
    fake_swsscommon.seed(PORTS).seed(COMBINED)
    result = run_module(acl_rule, dict(table='BGP_CULL', rules=[rule(), rule(name='BAD', src_ip='10.0.0.1', src_ipv6='::1')]),
                        expect_failure=True)
    assert result['msg'] == 'rule "BAD": mixes IPv4 and IPv6 match fields'
    assert fake_swsscommon.writes == []
