#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: acl_rule
short_description: Configure SONiC ACL rules
version_added: "0.4.0"
description:
  - Manage the rules of an ACL table in the C(ACL_RULE) table of the SONiC
    configuration database, the declarative and idempotent equivalent of
    C(acl-loader update full).
  - The table must exist, see M(community.sonic.acl_table). The module reads
    its layout from the configuration database. For a split policy (an
    V(L3) table next to its V(L3V6) twin) each rule is written to the table
    of its address family; rules that do not name a family, such as "drop
    TCP port 179", are written to both.
  - In an V(L3V6) table a rule that names no family gets C(IP_TYPE=IPV6ANY)
    unless O(rules[].ip_type) is given, and O(rules[].protocol=icmp) means ICMPv6.
  - orchagent rejects a rule without any match field, so a bare permit-all or
    deny-all rule gets an implicit C(IP_TYPE) match, V(IPV4ANY) in an V(L3) table,
    V(IPV6ANY) in an V(L3V6) table and V(IP) (IPv4 and IPv6) in an V(L3V4V6) table.
    Set O(rules[].ip_type) to choose something else, for example V(ANY) to also
    match non-IP frames.
  - After writing, the module waits for orchagent to report every rule as
    C(Active) in C(STATE_DB) (C(ACL_RULE_TABLE)) and fails with the rejected
    rules otherwise. Which match fields an ASIC supports varies, so only
    portable checks are done up front and the rest is left to orchagent.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  table:
    description:
      - Name of the ACL table (policy) as given to M(community.sonic.acl_table).
        For a split policy this is the IPv4 table; the IPv6 table C(<table><v6_suffix>) is found automatically.
    required: true
    type: str
  v6_suffix:
    description: Suffix of the IPv6 table of a split policy, as used by M(community.sonic.acl_table).
    type: str
    default: _v6
  state:
    description: Whether the listed rules should exist (V(present)) or be removed (V(absent)).
    type: str
    choices: [present, absent]
    default: present
  exclusive:
    description:
      - Remove rules of the table(s) that are not listed in O(rules).
      - With V(true) and an empty O(rules) list every rule of the table is removed.
    type: bool
    default: false
  status_timeout:
    description:
      - Seconds to wait for orchagent to report every written rule as C(Active) in C(STATE_DB).
      - V(0) skips the check.
    type: int
    default: 30
  rules:
    description: The rules. With O(state=absent) only O(rules[].name) is used.
    type: list
    elements: dict
    default: []
    suboptions:
      name:
        description: The rule name, the second part of the C(ACL_RULE) key.
        required: true
        type: str
      priority:
        description: Rule priority (C(PRIORITY)); higher values match first. Required with O(state=present).
        type: int
      action:
        description:
          - What to do with matching packets. V(forward) and V(drop) set C(PACKET_ACTION);
            V(redirect) sets C(REDIRECT_ACTION) to O(rules[].redirect).
          - Required unless O(rules[].fields) provides an action.
        type: str
        choices: [forward, drop, redirect]
      redirect:
        description:
          - Target of O(rules[].action=redirect), for example a port (V(Ethernet4)),
            a next hop (V(10.0.0.1@Ethernet4)) or a next hop group.
        type: str
      ip_type:
        description: Packet type to match (C(IP_TYPE)).
        type: str
        choices: [ANY, IP, NON_IP, IPV4ANY, NON_IPV4, IPV6ANY, NON_IPV6, ARP, ARP_REQUEST, ARP_REPLY]
      protocol:
        description:
          - IP protocol to match (C(IP_PROTOCOL)), as a number or one of
            V(tcp), V(udp), V(icmp), V(icmpv6), V(igmp), V(gre), V(esp), V(ah),
            V(ospf), V(pim), V(sctp), V(vrrp), V(rsvp) or V(l2tp).
          - V(icmp) means protocol 1 in an IPv4 table or combined table and
            protocol 58 (ICMPv6) in the IPv6 copy of a split policy. Use
            V(icmpv6) for an IPv6-only rule.
        type: str
      src_ip:
        description: IPv4 source address or prefix (C(SRC_IP)). A bare address becomes a /32. Makes the rule IPv4.
        type: str
      dst_ip:
        description: IPv4 destination address or prefix (C(DST_IP)). A bare address becomes a /32. Makes the rule IPv4.
        type: str
      src_ipv6:
        description: IPv6 source address or prefix (C(SRC_IPV6)). A bare address becomes a /128. Makes the rule IPv6.
        type: str
      dst_ipv6:
        description: IPv6 destination address or prefix (C(DST_IPV6)). A bare address becomes a /128. Makes the rule IPv6.
        type: str
      l4_src_port:
        description: TCP or UDP source port (C(L4_SRC_PORT)) or range V(low-high) (C(L4_SRC_PORT_RANGE)).
        type: str
      l4_dst_port:
        description: TCP or UDP destination port (C(L4_DST_PORT)) or range V(low-high) (C(L4_DST_PORT_RANGE)).
        type: str
      tcp_flags:
        description:
          - TCP flags that must be set (C(TCP_FLAGS)), as flag names (V(fin), V(syn), V(rst),
            V(psh), V(ack), V(urg), V(ece), V(cwr)) or a single V(0xVALUE/0xMASK) string.
          - Flag names are written as V(0xVV/0xVV), matching only when all of them are set.
        type: list
        elements: str
      ether_type:
        description:
          - Ethernet type to match (C(ETHER_TYPE)), as a number (V(2048), V(0x86DD)) or one of
            V(ipv4), V(ipv6), V(arp), V(lldp), V(vlan), V(mpls), V(roce). V(ipv4) and V(ipv6)
            make the rule IPv4 or IPv6.
        type: str
      dscp:
        description: DSCP value to match (C(DSCP)).
        type: int
      vlan_id:
        description: VLAN ID to match (C(VLAN_ID)).
        type: int
      in_ports:
        description: Ingress physical ports to match (C(IN_PORTS)), by name or alias.
        type: list
        elements: str
      icmp_type:
        description: ICMPv4 type (C(ICMP_TYPE)). Makes the rule IPv4 and implies O(rules[].protocol=icmp).
        type: int
      icmp_code:
        description: ICMPv4 code (C(ICMP_CODE)). Makes the rule IPv4 and implies O(rules[].protocol=icmp).
        type: int
      icmpv6_type:
        description: ICMPv6 type (C(ICMPV6_TYPE)). Makes the rule IPv6 and implies O(rules[].protocol=icmpv6).
        type: int
      icmpv6_code:
        description: ICMPv6 code (C(ICMPV6_CODE)). Makes the rule IPv6 and implies O(rules[].protocol=icmpv6).
        type: int
      fields:
        description:
          - Additional C(ACL_RULE) fields written as given, for anything the options above do not
            cover (C(MIRROR_INGRESS_ACTION), C(OUT_PORTS), C(INNER_*), ...). Values are stored as strings.
          - Options take precedence over fields of the same name.
        type: dict
notes:
  - A rule in a combined V(L3V4V6) table cannot mix IPv4 and IPv6 match fields; the module fails before writing.
  - Rules of a split policy are written with the same name to both tables.
seealso:
  - module: community.sonic.acl_table
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Cull BGP on the maintenance ports
  community.sonic.acl_rule:
    table: BGP_CULL
    rules:
      - name: DROP_BGP_DST
        priority: 9999
        protocol: tcp
        l4_dst_port: 179
        action: drop
      - name: DROP_BGP_SRC
        priority: 9998
        protocol: tcp
        l4_src_port: 179
        action: drop
      - name: PERMIT_ALL
        priority: 1
        action: forward
    exclusive: true

- name: Address family specific rules go to the matching table of a split policy
  community.sonic.acl_rule:
    table: EDGE_IN
    rules:
      - name: NO_SPOOF_V4
        priority: 100
        src_ip: 10.0.0.0/8
        action: drop
      - name: NO_SPOOF_V6
        priority: 100
        src_ipv6: 2001:db8::/32
        action: drop
      - name: SYN_RATE
        priority: 50
        protocol: tcp
        tcp_flags: [syn]
        l4_dst_port: 1024-65535
        action: forward

- name: Remove two rules
  community.sonic.acl_rule:
    table: BGP_CULL
    rules:
      - name: DROP_BGP_DST
      - name: DROP_BGP_SRC
    state: absent

- name: Remove every rule of a table
  community.sonic.acl_rule:
    table: BGP_CULL
    rules: []
    exclusive: true
'''

RETURN = r'''
tables:
  description: The tables the rules were written to, IPv4 table first.
  type: list
  elements: str
  returned: always
  sample: [BGP_CULL, BGP_CULL_v6]
family_mode:
  description: V(combined) or V(split) for a dual-stack policy, V(null) for a single table of another type.
  type: str
  returned: always
  sample: split
rules:
  description: The C(ACL_RULE) keys that exist after the change (what a real run would leave in check mode).
  type: list
  elements: str
  returned: always
  sample: ['BGP_CULL|DROP_BGP_DST', 'BGP_CULL_v6|DROP_BGP_DST']
removed:
  description: The C(ACL_RULE) keys that were removed.
  type: list
  elements: str
  returned: always
  sample: ['BGP_CULL|OLD_RULE']
diff:
  description: The managed C(ACL_RULE) entries before and after the change, keyed by C(table|rule); removed rules are only in C(before).
  type: dict
  returned: always
  sample: {"before": {}, "after": {"BGP_CULL|PERMIT_ALL": {"PRIORITY": "1", "PACKET_ACTION": "FORWARD", "IP_TYPE": "IP"}}}
'''

import ipaddress
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    build_result,
    join_key,
    split_key,
)
from ansible_collections.community.sonic.plugins.module_utils import acl


IP_PROTOCOLS = {
    'icmp': 1, 'igmp': 2, 'tcp': 6, 'udp': 17, 'rsvp': 46, 'gre': 47, 'esp': 50, 'ah': 51,
    'icmpv6': 58, 'ospf': 89, 'pim': 103, 'vrrp': 112, 'l2tp': 115, 'sctp': 132,
}
PROTO_ICMP = 1
PROTO_ICMPV6 = 58
PROTO_TCP = 6

ETHER_TYPES = {
    'ipv4': 0x0800, 'ipv6': 0x86DD, 'arp': 0x0806, 'lldp': 0x88CC, 'vlan': 0x8100, 'mpls': 0x8847, 'roce': 0x8915,
}
ETHER_TYPE_IPV4 = 0x0800
ETHER_TYPE_IPV6 = 0x86DD

TCP_FLAG_BITS = {'fin': 0x01, 'syn': 0x02, 'rst': 0x04, 'psh': 0x08, 'ack': 0x10, 'urg': 0x20, 'ece': 0x40, 'cwr': 0x80}

IP_TYPES = ['ANY', 'IP', 'NON_IP', 'IPV4ANY', 'NON_IPV4', 'IPV6ANY', 'NON_IPV6', 'ARP', 'ARP_REQUEST', 'ARP_REPLY']
IP_TYPES_V4 = ('IPV4ANY', 'ARP', 'ARP_REQUEST', 'ARP_REPLY')
IP_TYPES_V6 = ('IPV6ANY',)

FAMILY_V4 = 'v4'
FAMILY_V6 = 'v6'

_PORT_RE = re.compile(r'^\d+$')
_PORT_RANGE_RE = re.compile(r'^(\d+)-(\d+)$')
_TCP_FLAGS_RE = re.compile(r'^0[xX][0-9a-fA-F]{1,2}(/0[xX][0-9a-fA-F]{1,2})?$')


class RuleError(acl.AclError):
    """Raised for a rule that cannot be expressed in CONFIG_DB."""


def _error(rule, message):
    return RuleError('rule "%s": %s' % (rule['name'], message))


def parse_protocol(rule, value):
    """Return the IP protocol number for a name or number, ``None`` for ``None``."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in IP_PROTOCOLS:
        return IP_PROTOCOLS[text]
    if _PORT_RE.match(text) and 0 <= int(text) <= 255:
        return int(text)
    raise _error(rule, 'unknown protocol "%s"; use a number or one of %s' % (value, ', '.join(sorted(IP_PROTOCOLS))))


def parse_ether_type(rule, value):
    """Return the Ethernet type as an integer for a name, decimal or hex string, ``None`` for ``None``."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ETHER_TYPES:
        return ETHER_TYPES[text]
    try:
        number = int(text, 0)
    except ValueError:
        number = -1
    if not 0 <= number <= 0xFFFF:
        raise _error(rule, 'invalid ether_type "%s"; use a number or one of %s' % (value, ', '.join(sorted(ETHER_TYPES))))
    return number


def parse_prefix(rule, option, value, version):
    """Normalise an IP address or prefix, adding a host prefix length when missing, and check its version."""
    if value is None:
        return None
    try:
        iface = ipaddress.ip_interface(str(value).strip())
    except ValueError:
        raise _error(rule, '%s "%s" is not a valid IPv%d address or prefix' % (option, value, version))
    if iface.version != version:
        raise _error(rule, '%s "%s" is not an IPv%d address or prefix' % (option, value, version))
    return str(iface)


def parse_l4_port(rule, option, value):
    """Return ``(field_suffix, value)`` for a port (``''``, ``'179'``) or a range (``'_RANGE'``, ``'1024-65535'``)."""
    if value is None:
        return None, None
    text = str(value).strip()
    if _PORT_RE.match(text) and 0 <= int(text) <= 65535:
        return '', text
    m = _PORT_RANGE_RE.match(text)
    if m and 0 <= int(m.group(1)) <= int(m.group(2)) <= 65535:
        return '_RANGE', '%d-%d' % (int(m.group(1)), int(m.group(2)))
    raise _error(rule, '%s "%s" is not a port number or a low-high range' % (option, value))


def parse_tcp_flags(rule, value):
    """Return the ``TCP_FLAGS`` string for a list of flag names or a single ``0xVV/0xMM`` string."""
    if not value:
        return None
    if len(value) == 1 and _TCP_FLAGS_RE.match(str(value[0]).strip()):
        return str(value[0]).strip()
    bits = 0
    for flag in value:
        name = str(flag).strip().lower()
        if name not in TCP_FLAG_BITS:
            raise _error(rule, 'unknown TCP flag "%s"; use %s or a 0xVALUE/0xMASK string'
                         % (flag, ', '.join(sorted(TCP_FLAG_BITS))))
        bits |= TCP_FLAG_BITS[name]
    return '0x%02x/0x%02x' % (bits, bits)


def _check_range(rule, option, value, low, high):
    if value is not None and not low <= value <= high:
        raise _error(rule, '%s must be between %d and %d' % (option, low, high))
    return value


def rule_family(rule, protocol, ether_type):
    """Return ``'v4'``, ``'v6'`` or ``None`` depending on which address family the rule's match fields imply.

    Raises :class:`RuleError` when the rule mixes IPv4 and IPv6 fields.
    """
    v4 = any(rule.get(o) is not None for o in ('src_ip', 'dst_ip', 'icmp_type', 'icmp_code'))
    v6 = any(rule.get(o) is not None for o in ('src_ipv6', 'dst_ipv6', 'icmpv6_type', 'icmpv6_code'))
    if rule.get('ip_type') in IP_TYPES_V4 or ether_type == ETHER_TYPE_IPV4:
        v4 = True
    if rule.get('ip_type') in IP_TYPES_V6 or ether_type == ETHER_TYPE_IPV6 or protocol == PROTO_ICMPV6:
        v6 = True
    if v4 and v6:
        raise _error(rule, 'mixes IPv4 and IPv6 match fields')
    if v4:
        return FAMILY_V4
    if v6:
        return FAMILY_V6
    return None


def build_rule_entry(rule, resolve_port=None):
    """Convert a rule's options to an ``ACL_RULE`` entry; returns ``(entry, family)``.

    ``family`` is ``'v4'``, ``'v6'`` or ``None`` for a rule that applies to both.
    The entry is family neutral: ``protocol=icmp`` is left as protocol 1 and
    :func:`entry_for_table` adapts it to the table it is written to.
    """
    entry = {}
    for key, value in (rule.get('fields') or {}).items():
        if value is not None:
            entry[str(key)] = str(value)

    protocol = parse_protocol(rule, rule.get('protocol'))
    ether_type = parse_ether_type(rule, rule.get('ether_type'))
    family = rule_family(rule, protocol, ether_type)

    if rule.get('priority') is None:
        raise _error(rule, 'priority is required')
    entry['PRIORITY'] = str(_check_range(rule, 'priority', rule['priority'], 0, 999999))

    action = rule.get('action')
    if action in ('forward', 'drop'):
        entry['PACKET_ACTION'] = action.upper()
    elif action == 'redirect':
        if not rule.get('redirect'):
            raise _error(rule, 'action=redirect needs a redirect target')
        entry['REDIRECT_ACTION'] = rule['redirect']
    elif not any(k.endswith('_ACTION') or k == 'PACKET_ACTION' for k in entry):
        raise _error(rule, 'an action is required')

    icmp4 = rule.get('icmp_type') is not None or rule.get('icmp_code') is not None
    icmp6 = rule.get('icmpv6_type') is not None or rule.get('icmpv6_code') is not None
    if icmp4:
        if protocol is None:
            protocol = PROTO_ICMP
        elif protocol != PROTO_ICMP:
            raise _error(rule, 'icmp_type/icmp_code need protocol icmp')
    if icmp6:
        if protocol in (None, PROTO_ICMP):
            protocol = PROTO_ICMPV6
        elif protocol != PROTO_ICMPV6:
            raise _error(rule, 'icmpv6_type/icmpv6_code need protocol icmpv6')
    if protocol is not None:
        entry['IP_PROTOCOL'] = str(protocol)
    if ether_type is not None:
        entry['ETHER_TYPE'] = str(ether_type)
    if rule.get('ip_type') is not None:
        entry['IP_TYPE'] = rule['ip_type']

    for option, field, version in (('src_ip', 'SRC_IP', 4), ('dst_ip', 'DST_IP', 4),
                                   ('src_ipv6', 'SRC_IPV6', 6), ('dst_ipv6', 'DST_IPV6', 6)):
        value = parse_prefix(rule, option, rule.get(option), version)
        if value is not None:
            entry[field] = value

    for option, field in (('l4_src_port', 'L4_SRC_PORT'), ('l4_dst_port', 'L4_DST_PORT')):
        suffix, value = parse_l4_port(rule, option, rule.get(option))
        if value is not None:
            entry[field + suffix] = value

    tcp_flags = parse_tcp_flags(rule, rule.get('tcp_flags'))
    if tcp_flags is not None:
        if protocol not in (None, PROTO_TCP):
            raise _error(rule, 'tcp_flags need protocol tcp')
        entry['TCP_FLAGS'] = tcp_flags

    for option, field, low, high in (('dscp', 'DSCP', 0, 63), ('vlan_id', 'VLAN_ID', 1, 4094),
                                     ('icmp_type', 'ICMP_TYPE', 0, 255), ('icmp_code', 'ICMP_CODE', 0, 255),
                                     ('icmpv6_type', 'ICMPV6_TYPE', 0, 255), ('icmpv6_code', 'ICMPV6_CODE', 0, 255)):
        value = _check_range(rule, option, rule.get(option), low, high)
        if value is not None:
            entry[field] = str(value)

    if rule.get('in_ports'):
        ports = []
        for port in rule['in_ports']:
            name = resolve_port(port) if resolve_port else port
            if name not in ports:
                ports.append(name)
        entry['IN_PORTS'] = ','.join(ports)

    return entry, family


#: Match orchagent needs for a rule that has no match fields of its own, per table type.
DEFAULT_MATCH = {
    acl.TYPE_L3: ('IP_TYPE', 'IPV4ANY'),
    acl.TYPE_L3V6: ('IP_TYPE', 'IPV6ANY'),
    acl.TYPE_L3V4V6: ('IP_TYPE', 'IP'),
}


def has_match(entry):
    """Return ``True`` if the entry has at least one match field (anything but the priority and actions)."""
    return any(k != 'PRIORITY' and not k.endswith('_ACTION') for k in entry)


def entry_for_table(entry, family, table_type):
    """Adapt a family neutral entry to the table it is written to.

    In an ``L3V6`` table ``protocol=icmp`` becomes ICMPv6 and a rule that
    names no family gets ``IP_TYPE=IPV6ANY`` so it only matches IPv6, the
    way ``acl-loader`` does it (ether type matching is not available in
    IPv6 tables). orchagent rejects a rule without any match field, so a
    bare permit-all or deny-all gets the :data:`DEFAULT_MATCH` of its table type.
    """
    entry = dict(entry)
    if table_type == acl.TYPE_L3V6:
        if entry.get('IP_PROTOCOL') == str(PROTO_ICMP):
            entry['IP_PROTOCOL'] = str(PROTO_ICMPV6)
        if family is None and 'IP_TYPE' not in entry:
            entry['IP_TYPE'] = 'IPV6ANY'
    if not has_match(entry) and table_type in DEFAULT_MATCH:
        field, value = DEFAULT_MATCH[table_type]
        entry[field] = value
    return entry


def route_rules(rules, family_mode, tables, resolve_port=None):
    """Return ``{'table|rule': entry}`` for all rules, placed according to the table layout.

    ``tables`` is ``{name: type}`` as returned by ``acl.layout_from_config``,
    IPv4 table first. Raises :class:`RuleError` for a rule that cannot go
    into any of the tables.
    """
    desired = {}
    names = list(tables)
    for rule in rules:
        entry, family = build_rule_entry(rule, resolve_port)
        if family_mode == acl.FAMILY_SPLIT:
            targets = [n for n in names if (family is None
                                            or (family == FAMILY_V4 and tables[n] == acl.TYPE_L3)
                                            or (family == FAMILY_V6 and tables[n] == acl.TYPE_L3V6))]
            if not targets:
                raise _error(rule, 'the %s table of split policy "%s" does not exist'
                             % ('IPv6' if family == FAMILY_V6 else 'IPv4', names[0]))
        else:
            table_type = tables[names[0]]
            if family == FAMILY_V6 and table_type == acl.TYPE_L3:
                raise _error(rule, 'has IPv6 match fields but table "%s" is of type L3' % names[0])
            if family == FAMILY_V4 and table_type == acl.TYPE_L3V6:
                raise _error(rule, 'has IPv4 match fields but table "%s" is of type L3V6' % names[0])
            targets = names
        for table_name in targets:
            key = join_key(table_name, rule['name'])
            if key in desired:
                raise _error(rule, 'listed more than once')
            desired[key] = entry_for_table(entry, family, tables[table_name])
    return desired


def run_module():
    rule_spec = dict(
        name=dict(type='str', required=True),
        priority=dict(type='int'),
        action=dict(type='str', choices=['forward', 'drop', 'redirect']),
        redirect=dict(type='str'),
        ip_type=dict(type='str', choices=IP_TYPES),
        protocol=dict(type='str'),
        src_ip=dict(type='str'),
        dst_ip=dict(type='str'),
        src_ipv6=dict(type='str'),
        dst_ipv6=dict(type='str'),
        l4_src_port=dict(type='str'),
        l4_dst_port=dict(type='str'),
        tcp_flags=dict(type='list', elements='str'),
        ether_type=dict(type='str'),
        dscp=dict(type='int'),
        vlan_id=dict(type='int'),
        in_ports=dict(type='list', elements='str'),
        icmp_type=dict(type='int'),
        icmp_code=dict(type='int'),
        icmpv6_type=dict(type='int'),
        icmpv6_code=dict(type='int'),
        fields=dict(type='dict'),
    )
    module_args = dict(
        table=dict(type='str', required=True),
        v6_suffix=dict(type='str', default=acl.DEFAULT_V6_SUFFIX),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        exclusive=dict(type='bool', default=False),
        status_timeout=dict(type='int', default=30),
        rules=dict(type='list', elements='dict', default=[], options=rule_spec),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )
    params = module.params
    table = params['table']

    db = ConfigDB(module).connect()
    state_db = ConfigDB(module, db_name='STATE_DB').connect()
    try:
        acl_tables = db.get_table(acl.ACL_TABLE)
        family_mode, tables = acl.layout_from_config(table, acl_tables, params['v6_suffix'])
        if table not in tables:
            raise acl.AclError('ACL table "%s" does not exist; create it with community.sonic.acl_table first' % table)
        if family_mode == acl.FAMILY_SPLIT and len(tables) == 1:
            # A lone L3 table is just an IPv4 table.
            family_mode = None

        current = dict((k, v) for k, v in db.get_table(acl.ACL_RULE).items() if split_key(k)[0] in tables)
        if params['state'] == 'absent':
            names = set(r['name'] for r in params['rules'])
            desired = {}
            remove = [k for k in current if split_key(k)[1] in names]
        else:
            desired = route_rules(params['rules'], family_mode, tables, db.resolve_port)
            remove = [k for k in current if k not in desired] if params['exclusive'] else []

        before, after = {}, {}
        changed = False
        for key in sorted(remove):
            before[key] = current[key]
            db.delete_entry(acl.ACL_RULE, key)
            changed = True
        for key, entry in sorted(desired.items()):
            change = db.ensure_entry(acl.ACL_RULE, key, entry, exclusive=True)
            before[key] = change.before
            after[key] = change.after
            changed = changed or change.changed

        if desired and not module.check_mode:
            acl.check_status(state_db, acl.STATE_ACL_RULE_TABLE, sorted(desired), params['status_timeout'],
                             'ACL rule%s in %s' % ('s' if len(desired) > 1 else '', ', '.join(tables)))
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    before = dict((k, v) for k, v in before.items() if v)
    module.exit_json(**build_result(changed, before, after, tables=list(tables), family_mode=family_mode,
                                    rules=sorted(desired), removed=sorted(remove)))


def main():
    run_module()


if __name__ == '__main__':
    main()
