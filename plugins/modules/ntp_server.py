#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: ntp_server
short_description: Configure NTP servers on SONiC
version_added: "0.4.0"
description:
  - Manage the NTP servers and pools in the SONiC C(NTP_SERVER) table, the
    equivalent of C(config ntp add/del).
  - Either manage one server with O(address) and O(state), or manage the list
    with O(servers), optionally making it the complete list with O(exclusive).
    The per-server options (O(iburst), O(version), ...) apply to every server
    given.
  - Only the options that are given are written, so a server added with no
    options is stored with an empty value, as C(config ntp add) does, and the
    daemon uses its defaults (C(server) association, C(iburst) on, version 4).
    Re-applying a server without options never changes anything.
  - The C(resolve_as) field, which SONiC fills in with the resolved address
    of a server, is never written by this module.
  - SONiC's C(hostcfgd) restarts the time daemon (C(chrony) or C(ntpd),
    depending on the release) when the table changes and the daemon regenerates
    its configuration from CONFIG_DB on the way up.
  - The options other than O(address), O(servers), O(exclusive) and O(state) need
    SONiC 202305 or later, where the C(NTP_SERVER) entry carries fields. Older
    releases only know the key with an empty value, which the module writes
    when no option is given.
  - Global settings such as the source interface or the VRF are managed with
    M(community.sonic.ntp) and authentication keys with M(community.sonic.ntp_key).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  address:
    description:
      - A single NTP server to add or remove, as an IPv4 or IPv6 address or a
        host name (for pools usually a name such as V(pool.ntp.org)).
      - Mutually exclusive with O(servers).
    type: str
  servers:
    description:
      - NTP servers to add (O(state=present)) or remove (O(state=absent)), as
        IPv4 or IPv6 addresses or host names.
      - With O(exclusive=true) the configured servers are made exactly this list.
      - Mutually exclusive with O(address).
    type: list
    elements: str
  exclusive:
    description:
      - When V(true), remove every configured server that is not listed in O(servers).
      - Only valid together with O(servers) and O(state=present).
    type: bool
  association_type:
    description:
      - Whether the entry is a single V(server) or a V(pool) of servers behind
        one name (C(association_type)).
    type: str
    choices: [server, pool]
  iburst:
    description:
      - Whether to poll the server aggressively when it is unreachable (C(iburst)).
    type: bool
  enabled:
    description:
      - Whether the server is used (C(admin_state)). A disabled server stays in
        the table but is left out of the daemon configuration.
    type: bool
  version:
    description:
      - The NTP protocol version used with the server (C(version)).
    type: int
    choices: [3, 4]
  key:
    description:
      - The ID of the authentication key from M(community.sonic.ntp_key) used
        with this server (C(key)). Only used when authentication is enabled
        with M(community.sonic.ntp).
    type: int
  trusted:
    description:
      - Whether the server is trusted (C(trusted)); with authentication enabled
        the daemon then synchronises to this server only.
    type: bool
  state:
    description: Whether the server(s) should be present or absent.
    default: present
    type: str
    choices: [present, absent]
notes:
  - CONFIG_DB keys are unordered, so the order of O(servers) is not preserved on the device.
  - Changing the servers restarts the time daemon, which can take a few
    seconds to come back. The module returns as soon as the configuration
    database is updated.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Add an NTP server
  community.sonic.ntp_server:
    address: 2001:db8::123
    iburst: true

- name: Remove an NTP server
  community.sonic.ntp_server:
    address: 192.0.2.123
    state: absent

- name: Configure exactly these servers
  community.sonic.ntp_server:
    servers:
      - 2001:db8::123
      - 192.0.2.123
    iburst: true
    exclusive: true

- name: Use a pool
  community.sonic.ntp_server:
    address: pool.ntp.org
    association_type: pool

- name: Authenticate with key 42
  community.sonic.ntp_server:
    address: 192.0.2.123
    key: 42
    trusted: true

- name: Keep a server configured but do not use it
  community.sonic.ntp_server:
    address: 192.0.2.123
    enabled: false

- name: Remove all servers
  community.sonic.ntp_server:
    servers: []
    exclusive: true
'''

RETURN = r'''
servers:
  description: The NTP server keys configured after the module ran (predicted in check mode).
  type: list
  elements: str
  returned: always
  sample: ['2001:db8::123', '192.0.2.123']
diff:
  description: The C(NTP_SERVER) table before and after the change.
  type: dict
  returned: always
  sample: {'before': {}, 'after': {'2001:db8::123': {'iburst': 'on'}, '192.0.2.123': {'iburst': 'on'}}}
'''

import ipaddress
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    bool_to_enabled_disabled,
    build_result,
)

TABLE = 'NTP_SERVER'

#: Key IDs are 16 bit unsigned and 0 is reserved, see sonic-ntp.yang.
MIN_KEY_ID = 1
MAX_KEY_ID = 65535

_HOSTNAME_LABEL = r'[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?'
_HOSTNAME_RE = re.compile(r'^%s(\.%s)*\.?$' % (_HOSTNAME_LABEL, _HOSTNAME_LABEL))
#: A host name made of digits and dots only is a malformed IPv4 address, not a name.
_NUMERIC_RE = re.compile(r'^[0-9.]+$')


def bool_to_on_off(value):
    """Map a boolean to the ``on``/``off`` strings used by ``iburst``. ``None`` passes through."""
    if value is None:
        return None
    return 'on' if value else 'off'


def bool_to_yes_no(value):
    """Map a boolean to the ``yes``/``no`` strings used by ``trusted``. ``None`` passes through."""
    if value is None:
        return None
    return 'yes' if value else 'no'


def canonical_server(address):
    """Return the canonical text form of an IP address, or a host name unchanged.

    Raises ValueError when the value is neither an IP address nor a host name.
    """
    text = str(address).strip()
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    if text and _HOSTNAME_RE.match(text) and not _NUMERIC_RE.match(text):
        return text
    raise ValueError('"%s" is not a valid IPv4 or IPv6 address or host name' % address)


def validate_servers(addresses):
    """Return the canonical forms of ``addresses``, without duplicates, preserving order."""
    result = []
    for address in addresses:
        canonical = canonical_server(address)
        if canonical not in result:
            result.append(canonical)
    return result


def _canonical_or_raw(key):
    try:
        return canonical_server(key)
    except ValueError:
        return key


def plan_servers(current_keys, addresses, state, exclusive):
    """Work out which NTP_SERVER keys to write and which to remove.

    ``current_keys`` are the keys stored in the table, ``addresses`` the
    canonical servers the caller wants present or absent. Stored keys are
    matched by their canonical form so ``2001:DB8::1`` and ``2001:db8::1``
    are the same server. Returns ``(targets, to_remove, after)``: ``targets``
    are the keys to write (existing keys are reused as stored), ``to_remove``
    the keys to delete and ``after`` the keys the table holds afterwards.
    """
    by_canonical = dict((_canonical_or_raw(key), key) for key in current_keys)
    targets = []
    to_remove = []
    if state == 'present':
        targets = [by_canonical.get(address, address) for address in addresses]
        if exclusive:
            to_remove = [key for canonical, key in by_canonical.items() if canonical not in addresses]
    else:
        to_remove = [by_canonical[address] for address in addresses if address in by_canonical]
    after = [key for key in current_keys if key not in to_remove]
    after += [key for key in targets if key not in after]
    return targets, to_remove, after


def build_server_entry(association_type=None, iburst=None, enabled=None, version=None, key=None, trusted=None):
    """Return the fields to merge into an ``NTP_SERVER`` entry; options left at ``None`` are not written."""
    desired = {}
    if association_type is not None:
        desired['association_type'] = association_type
    if iburst is not None:
        desired['iburst'] = bool_to_on_off(iburst)
    if enabled is not None:
        desired['admin_state'] = bool_to_enabled_disabled(enabled)
    if version is not None:
        desired['version'] = version
    if key is not None:
        desired['key'] = key
    if trusted is not None:
        desired['trusted'] = bool_to_yes_no(trusted)
    return desired


def run_module():
    module_args = dict(
        address=dict(type='str'),
        servers=dict(type='list', elements='str'),
        exclusive=dict(type='bool'),
        association_type=dict(type='str', choices=['server', 'pool']),
        iburst=dict(type='bool'),
        enabled=dict(type='bool'),
        version=dict(type='int', choices=[3, 4]),
        key=dict(type='int', no_log=False),
        trusted=dict(type='bool'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        mutually_exclusive=[('address', 'servers')],
        required_one_of=[('address', 'servers')],
        required_by={'exclusive': 'servers'},
    )
    params = module.params

    state = params['state']
    exclusive = bool(params['exclusive'])
    if exclusive and state == 'absent':
        module.fail_json(msg='exclusive=true cannot be combined with state=absent; '
                             'list the servers to keep with state=present instead')

    key_id = params['key']
    if key_id is not None and not MIN_KEY_ID <= key_id <= MAX_KEY_ID:
        module.fail_json(msg='key must be between %d and %d, got %d' % (MIN_KEY_ID, MAX_KEY_ID, key_id))

    if params['address'] is not None:
        addresses = [params['address']]
    else:
        addresses = params['servers']

    try:
        addresses = validate_servers(addresses)
    except ValueError as e:
        module.fail_json(msg=str(e))

    fields = build_server_entry(association_type=params['association_type'], iburst=params['iburst'],
                                enabled=params['enabled'], version=params['version'], key=key_id,
                                trusted=params['trusted'])

    db = ConfigDB(module).connect()
    changed = False
    try:
        before = db.get_table(TABLE)
        targets, to_remove, after_keys = plan_servers(list(before.keys()), addresses, state, exclusive)
        after = dict((key, before[key]) for key in after_keys if key in before)
        for key in to_remove:
            changed = db.ensure_absent(TABLE, key).changed or changed
        for key in targets:
            change = db.ensure_entry(TABLE, key, fields, exclusive=False)
            changed = change.changed or changed
            after[key] = change.after
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    after = dict((key, after[key]) for key in after_keys)
    module.exit_json(**build_result(changed, before, after, servers=after_keys))


def main():
    run_module()


if __name__ == '__main__':
    main()
