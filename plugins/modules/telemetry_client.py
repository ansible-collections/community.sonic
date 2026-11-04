#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: telemetry_client
short_description: Configure the SONiC gNMI dial-out (push) telemetry client
version_added: "0.4.0"
description:
  - Manage the C(TELEMETRY_CLIENT) table of the SONiC configuration database,
    which makes the switch open connections to collectors and stream the
    configured paths to them (gNMI dial-out). The dial-in server is managed
    with M(community.sonic.gnmi_server).
  - The table holds a C(Global) entry with the connection settings, one
    C(DestinationGroup_<name>) entry per group of collectors and one
    C(Subscription_<name>) entry per set of paths to stream. The dial-out
    client in the C(gnmi) (or C(telemetry)) container watches the table and
    applies changes immediately.
  - By default, with O(exclusive=true), the module owns the whole table and
    makes the C(Global) entry, the destination groups and the subscriptions
    exactly what the task describes, removing everything else. With
    O(exclusive=false) only the named groups and subscriptions are replaced
    and the given global settings are merged into C(Global).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  encoding:
    description:
      - Encoding of the streamed data.
      - Current SONiC releases always send V(JSON_IETF) whatever is configured.
    type: str
    choices: [JSON_IETF, ASCII, BYTES, PROTO]
  retry_interval:
    description: Seconds to wait before reconnecting to a collector after a failure.
    type: int
  src_ip:
    description:
      - Source address for the connections to the collectors.
      - Any address of the switch may be used, in the default or the management VRF.
    type: str
  unidirectional:
    description:
      - Whether the collector is not expected to answer the streamed updates.
      - SONiC currently supports unidirectional streaming only; the field is
        stored as given.
    type: bool
  destination_groups:
    description:
      - Collector groups, written as C(DestinationGroup_<name>) entries.
    type: list
    elements: dict
    default: []
    suboptions:
      name:
        description: Name of the group, referenced by O(subscriptions[].destination_group).
        type: str
        required: true
      collectors:
        description:
          - The collectors of the group as C(host:port) addresses
            (C([2001:db8::20]:8080) for IPv6).
          - Stored as the comma separated C(dst_addr) field.
        type: list
        elements: str
        required: true
  subscriptions:
    description:
      - Sets of paths to stream, written as C(Subscription_<name>) entries.
    type: list
    elements: dict
    default: []
    suboptions:
      name:
        description: Name of the subscription.
        type: str
        required: true
      destination_group:
        description:
          - Name of the destination group to stream to, stored as C(dst_group).
          - Must be listed in O(destination_groups) or, with O(exclusive=false),
            already exist on the device.
        type: str
        required: true
      path_target:
        description: The database the paths refer to, stored as C(path_target).
        type: str
        choices: [APPL_DB, CONFIG_DB, COUNTERS_DB, STATE_DB, OTHERS]
      paths:
        description:
          - The paths to stream, written as the comma separated C(paths) field.
          - Paths are passed through unchanged; the telemetry daemon does not
            expand port aliases, so use SONiC names such as C(COUNTERS/Ethernet*).
        type: list
        elements: str
        required: true
      report_type:
        description: V(periodic) sends every O(subscriptions[].report_interval), V(stream) on change and V(once) a single time.
        type: str
        choices: [periodic, stream, once]
      report_interval:
        description: Reporting interval in milliseconds for V(periodic) subscriptions; SONiC defaults to V(5000).
        type: int
  exclusive:
    description:
      - When V(true), the module makes the whole table exactly what the task
        describes, removing other destination groups, subscriptions and global
        fields. A task without groups and subscriptions therefore empties the
        table apart from the given global settings.
      - When V(false), the named destination groups and subscriptions are
        replaced, other entries are kept and the given global settings are
        merged into the C(Global) entry.
    type: bool
    default: true
  state:
    description:
      - V(present) applies the configuration.
      - V(absent) removes the whole C(TELEMETRY_CLIENT) table, stopping all dial-out streams.
    type: str
    choices: [present, absent]
    default: present
notes:
  - The entries are only honoured while the C(gnmi) (or C(telemetry))
    container is enabled in the C(FEATURE) table, see M(community.sonic.feature).
  - End-to-end delivery requires a reachable collector and cannot be verified
    by the module; it only writes the configuration database.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Stream port counters and transceiver sensors to two collectors
  community.sonic.telemetry_client:
    encoding: JSON_IETF
    retry_interval: 30
    unidirectional: true
    destination_groups:
      - name: collectors
        collectors:
          - "[2001:db8::20]:8080"
          - "[2001:db8::21]:8080"
    subscriptions:
      - name: port_counters
        destination_group: collectors
        path_target: COUNTERS_DB
        paths: ["COUNTERS/Ethernet*"]
        report_type: periodic
        report_interval: 10000
      - name: transceiver_dom
        destination_group: collectors
        path_target: STATE_DB
        paths: ["TRANSCEIVER_DOM_SENSOR"]
        report_type: periodic
        report_interval: 60000

- name: Add one more subscription without touching the rest of the table
  community.sonic.telemetry_client:
    exclusive: false
    subscriptions:
      - name: lldp
        destination_group: collectors
        path_target: APPL_DB
        paths: [LLDP_ENTRY_TABLE]
        report_type: stream

- name: Stop all dial-out telemetry
  community.sonic.telemetry_client:
    state: absent
'''

RETURN = r'''
destination_groups:
  description: Names of the destination groups in the table after the change (predicted in check mode).
  type: list
  elements: str
  returned: always
  sample: [collectors]
subscriptions:
  description: Names of the subscriptions in the table after the change (predicted in check mode).
  type: list
  elements: str
  returned: always
  sample: [port_counters, transceiver_dom]
diff:
  description: The whole C(TELEMETRY_CLIENT) table before and after the change.
  type: dict
  returned: always
  sample:
    before: {}
    after:
      Global: {encoding: JSON_IETF, retry_interval: '30'}
      DestinationGroup_collectors: {dst_addr: '[2001:db8::20]:8080,[2001:db8::21]:8080'}
      Subscription_port_counters:
        dst_group: collectors
        path_target: COUNTERS_DB
        paths: COUNTERS/Ethernet*
        report_type: periodic
        report_interval: '10000'
'''

import ipaddress
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, build_result, normalize_entry)

TABLE = 'TELEMETRY_CLIENT'
GLOBAL_KEY = 'Global'
GROUP_PREFIX = 'DestinationGroup_'
SUBSCRIPTION_PREFIX = 'Subscription_'

ENCODINGS = ('JSON_IETF', 'ASCII', 'BYTES', 'PROTO')
PATH_TARGETS = ('APPL_DB', 'CONFIG_DB', 'COUNTERS_DB', 'STATE_DB', 'OTHERS')
REPORT_TYPES = ('periodic', 'stream', 'once')

_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
_HOST_PORT_RE = re.compile(r'^(\[[0-9A-Fa-f:.]+\]|[^\s:,\[\]]+):([0-9]{1,5})$')


class TelemetryClientError(ValueError):
    """Raised for invalid dial-out client options."""


def validate_name(kind, name):
    """Check that an object name is usable as part of a CONFIG_DB key (no ``|``, ``,`` or whitespace)."""
    if not _NAME_RE.match(str(name)):
        raise TelemetryClientError(
            '%s name "%s" is invalid; use letters, digits, "_", "-" and "." only' % (kind, name))
    return name


def validate_collector(group, address):
    """Check that a collector address is ``host:port`` (``[v6]:port`` for IPv6) with a valid port."""
    text = str(address).strip()
    m = _HOST_PORT_RE.match(text)
    if m is None or not (1 <= int(m.group(2)) <= 65535):
        raise TelemetryClientError(
            'destination group "%s": collector "%s" must be host:port or [ipv6]:port' % (group, address))
    return text


def build_group_entry(name, collectors):
    """Return the ``DestinationGroup_<name>`` entry for a list of collector addresses."""
    addresses = []
    for collector in collectors or ():
        address = validate_collector(name, collector)
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise TelemetryClientError('destination group "%s" needs at least one collector' % name)
    return {'dst_addr': ','.join(addresses)}


def build_subscription_entry(name, destination_group, paths, path_target=None, report_type=None,
                             report_interval=None, known_groups=()):
    """Return the ``Subscription_<name>`` entry; ``known_groups`` are the destination group names that exist."""
    if destination_group not in known_groups:
        raise TelemetryClientError(
            'subscription "%s" refers to destination group "%s", which is not configured' % (name, destination_group))
    cleaned = []
    for path in paths or ():
        path = str(path).strip()
        if not path or ',' in path:
            raise TelemetryClientError('subscription "%s": path "%s" is invalid' % (name, path))
        if path not in cleaned:
            cleaned.append(path)
    if not cleaned:
        raise TelemetryClientError('subscription "%s" needs at least one path' % name)
    if report_interval is not None and report_interval <= 0:
        raise TelemetryClientError('subscription "%s": report_interval must be positive, got %d' % (name, report_interval))

    entry = {'dst_group': destination_group, 'paths': ','.join(cleaned)}
    if path_target is not None:
        entry['path_target'] = path_target
    if report_type is not None:
        entry['report_type'] = report_type
    if report_interval is not None:
        entry['report_interval'] = report_interval
    return entry


def build_global_entry(encoding=None, retry_interval=None, src_ip=None, unidirectional=None):
    """Return the ``Global`` fields for the given options (only those that are set)."""
    desired = {}
    for field, value in (('encoding', encoding), ('retry_interval', retry_interval),
                         ('src_ip', src_ip), ('unidirectional', unidirectional)):
        if value is not None:
            desired[field] = value
    return desired


def plan_table(current, global_fields, destination_groups, subscriptions, exclusive):
    """Return the ``{key: entry}`` the table should hold afterwards.

    ``current`` is the stored table, ``destination_groups`` and
    ``subscriptions`` the validated option lists. With ``exclusive`` the result
    is exactly the described objects; otherwise it is ``current`` with the
    described objects replaced and ``global_fields`` merged into ``Global``.
    Entries are normalised to CONFIG_DB strings so they compare with ``current``.
    """
    after = {} if exclusive else dict((k, dict(v)) for k, v in current.items())

    if exclusive:
        global_entry = dict(global_fields)
    else:
        global_entry = dict(current.get(GLOBAL_KEY, {}))
        global_entry.update(global_fields)
    if global_entry:
        after[GLOBAL_KEY] = normalize_entry(global_entry)
    else:
        after.pop(GLOBAL_KEY, None)

    seen = set()
    for group in destination_groups:
        name = validate_name('destination group', group['name'])
        if name in seen:
            raise TelemetryClientError('destination group "%s" is listed twice' % name)
        seen.add(name)
        after[GROUP_PREFIX + name] = normalize_entry(build_group_entry(name, group['collectors']))

    known_groups = set(seen)
    if not exclusive:
        known_groups.update(k[len(GROUP_PREFIX):] for k in current if k.startswith(GROUP_PREFIX))
    seen = set()
    for sub in subscriptions:
        name = validate_name('subscription', sub['name'])
        if name in seen:
            raise TelemetryClientError('subscription "%s" is listed twice' % name)
        seen.add(name)
        after[SUBSCRIPTION_PREFIX + name] = normalize_entry(build_subscription_entry(
            name, sub['destination_group'], sub['paths'], sub.get('path_target'), sub.get('report_type'),
            sub.get('report_interval'), known_groups))

    return after


def names_with_prefix(table, prefix):
    """Return the sorted object names of the keys in ``table`` that start with ``prefix``."""
    return sorted(k[len(prefix):] for k in table if k.startswith(prefix))


def run_module():
    module_args = dict(
        encoding=dict(type='str', choices=list(ENCODINGS)),
        retry_interval=dict(type='int'),
        src_ip=dict(type='str'),
        unidirectional=dict(type='bool'),
        destination_groups=dict(type='list', elements='dict', default=[], options=dict(
            name=dict(type='str', required=True),
            collectors=dict(type='list', elements='str', required=True),
        )),
        subscriptions=dict(type='list', elements='dict', default=[], options=dict(
            name=dict(type='str', required=True),
            destination_group=dict(type='str', required=True),
            path_target=dict(type='str', choices=list(PATH_TARGETS)),
            paths=dict(type='list', elements='str', required=True),
            report_type=dict(type='str', choices=list(REPORT_TYPES)),
            report_interval=dict(type='int'),
        )),
        exclusive=dict(type='bool', default=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )
    params = module.params

    retry_interval = params['retry_interval']
    if retry_interval is not None and retry_interval < 0:
        module.fail_json(msg='retry_interval must not be negative, got %d' % retry_interval)
    src_ip = params['src_ip']
    if src_ip is not None:
        try:
            src_ip = str(ipaddress.ip_address(src_ip.strip()))
        except ValueError:
            module.fail_json(msg='src_ip "%s" is not a valid IPv4 or IPv6 address' % src_ip)

    db = ConfigDB(module).connect()
    try:
        before = db.get_table(TABLE)
        if params['state'] == 'absent':
            after = {}
        else:
            global_fields = build_global_entry(params['encoding'], retry_interval, src_ip, params['unidirectional'])
            try:
                after = plan_table(before, global_fields, params['destination_groups'], params['subscriptions'],
                                   params['exclusive'])
            except TelemetryClientError as e:
                module.fail_json(msg=str(e))

        changed = False
        for key in sorted(set(before) - set(after)):
            changed = db.ensure_absent(TABLE, key).changed or changed
        for key in sorted(after):
            changed = db.ensure_entry(TABLE, key, after[key], exclusive=True).changed or changed
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**build_result(changed, before, after,
                                    destination_groups=names_with_prefix(after, GROUP_PREFIX),
                                    subscriptions=names_with_prefix(after, SUBSCRIPTION_PREFIX)))


def main():
    run_module()


if __name__ == '__main__':
    main()
