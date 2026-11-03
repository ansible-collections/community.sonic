#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: dns_nameserver
short_description: Configure SONiC DNS nameservers
version_added: "0.4.0"
description:
  - Manage the static DNS nameservers in the SONiC C(DNS_NAMESERVER) table, the
    equivalent of C(config dns nameserver add/del).
  - SONiC's C(hostcfgd) regenerates C(/etc/resolv.conf) in the host and the
    containers from this table, so edit the table rather than the file.
  - Either manage one nameserver with O(address) and O(state), or manage the
    list with O(servers), optionally making it the complete list with O(exclusive).
  - SONiC allows at most three nameservers; the module fails before writing
    anything when the resulting list would be longer.
  - CONFIG_DB keys are unordered and SONiC writes the resolver configuration
    in its own order, so the order of O(servers) is not preserved on the device.
  - Static nameservers are only supported from SONiC 202305 on. The module fails
    on older releases, which have no C(sonic-system-dns) YANG model, instead of
    silently writing a table that nothing reads.
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
          - A single nameserver IPv4 or IPv6 address to add or remove.
          - Mutually exclusive with O(servers).
        type: str
    servers:
        description:
          - Nameserver IPv4 or IPv6 addresses to add (O(state=present)) or remove (O(state=absent)).
          - With O(exclusive=true) the configured nameservers are made exactly this list.
          - Mutually exclusive with O(address).
        type: list
        elements: str
    exclusive:
        description:
          - When V(true), remove every configured nameserver that is not listed in O(servers).
          - Only valid together with O(servers) and O(state=present).
        type: bool
    state:
        description: Whether the nameserver(s) should be present or absent.
        default: present
        type: str
        choices: [present, absent]

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Add a nameserver
  community.sonic.dns_nameserver:
    address: 2001:db8::53

- name: Remove a nameserver
  community.sonic.dns_nameserver:
    address: 192.0.2.53
    state: absent

- name: Make sure these nameservers are configured, keeping any others
  community.sonic.dns_nameserver:
    servers:
      - 2001:db8::53
      - 192.0.2.53

- name: Configure exactly these nameservers
  community.sonic.dns_nameserver:
    servers:
      - 2001:db8::53
      - 192.0.2.53
    exclusive: true

- name: Remove all nameservers
  community.sonic.dns_nameserver:
    servers: []
    exclusive: true
'''

RETURN = r'''
servers:
    description: The nameserver addresses configured after the module ran (predicted in check mode).
    type: list
    elements: str
    returned: always
    sample: ['2001:db8::53', '192.0.2.53']
diff:
    description: The C(DNS_NAMESERVER) table before and after the change; each nameserver is a key with an empty value.
    type: dict
    returned: always
    sample: {'before': {}, 'after': {'2001:db8::53': {}, '192.0.2.53': {}}}
'''

import ipaddress
import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError, build_result

TABLE = 'DNS_NAMESERVER'

#: SONiC enforces this limit in the CLI and in the sonic-system-dns YANG model.
MAX_NAMESERVERS = 3

#: Where SONiC installs its YANG models; the DNS model only exists on releases that manage DNS_NAMESERVER.
YANG_MODEL_DIR = '/usr/local/yang-models'
DNS_YANG_MODEL = 'sonic-system-dns.yang'


def canonical_address(address):
    """Return the canonical text form of an IP address, or raise ValueError if it is not one."""
    return str(ipaddress.ip_address(str(address).strip()))


def validate_addresses(addresses):
    """Return the canonical forms of ``addresses``, without duplicates, preserving order.

    Raises ValueError naming the first address that is not an IP address.
    """
    result = []
    for address in addresses:
        try:
            canonical = canonical_address(address)
        except ValueError:
            raise ValueError('"%s" is not a valid IPv4 or IPv6 address' % address)
        if canonical not in result:
            result.append(canonical)
    return result


def _canonical_or_raw(key):
    try:
        return canonical_address(key)
    except ValueError:
        return key


def plan_nameservers(current_keys, addresses, state, exclusive):
    """Work out the DNS_NAMESERVER keys to add and remove.

    ``current_keys`` are the keys stored in the table, ``addresses`` the
    canonical addresses the caller wants present or absent. Stored keys are
    matched by their canonical form so ``2001:DB8::1`` and ``2001:db8::1`` are
    the same nameserver. Returns ``(to_add, to_remove, after)`` where ``after``
    is the list of keys the table holds afterwards.
    """
    by_canonical = dict((_canonical_or_raw(key), key) for key in current_keys)
    to_add = []
    to_remove = []
    if state == 'present':
        for address in addresses:
            if address not in by_canonical:
                to_add.append(address)
        if exclusive:
            to_remove = [key for canonical, key in by_canonical.items() if canonical not in addresses]
    else:
        to_remove = [by_canonical[address] for address in addresses if address in by_canonical]
    after = [key for key in current_keys if key not in to_remove] + to_add
    return to_add, to_remove, after


def release_supports_dns(yang_dir=None):
    """Return False when this SONiC release installs YANG models but not the DNS one.

    The ``DNS_NAMESERVER`` table and the ``hostcfgd`` code that consumes it
    arrived together with ``sonic-system-dns.yang`` in SONiC 202305. When the
    YANG directory is missing altogether nothing can be concluded and the
    release is assumed to support it.
    """
    if yang_dir is None:
        yang_dir = YANG_MODEL_DIR
    if not os.path.isdir(yang_dir):
        return True
    return os.path.exists(os.path.join(yang_dir, DNS_YANG_MODEL))


def run_module():
    module_args = dict(
        address=dict(type='str'),
        servers=dict(type='list', elements='str'),
        exclusive=dict(type='bool'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        mutually_exclusive=[('address', 'servers')],
        required_one_of=[('address', 'servers')],
        required_by={'exclusive': 'servers'},
    )

    state = module.params['state']
    exclusive = bool(module.params['exclusive'])
    if exclusive and state == 'absent':
        module.fail_json(msg='exclusive=true cannot be combined with state=absent; '
                             'list the nameservers to keep with state=present instead')

    if module.params['address'] is not None:
        addresses = [module.params['address']]
    else:
        addresses = module.params['servers']

    try:
        addresses = validate_addresses(addresses)
    except ValueError as e:
        module.fail_json(msg=str(e))

    if not release_supports_dns():
        module.fail_json(msg='this SONiC release does not support static DNS nameservers '
                             '(no %s in %s); the DNS_NAMESERVER table is only honoured from SONiC 202305 on'
                         % (DNS_YANG_MODEL, YANG_MODEL_DIR))

    db = ConfigDB(module).connect()
    try:
        before = db.get_table(TABLE)
        to_add, to_remove, after_keys = plan_nameservers(list(before.keys()), addresses, state, exclusive)
        if len(after_keys) > MAX_NAMESERVERS:
            module.fail_json(msg='SONiC allows at most %d DNS nameservers, but %d would be configured: %s'
                             % (MAX_NAMESERVERS, len(after_keys), ', '.join(after_keys)))
        for key in to_remove:
            db.ensure_absent(TABLE, key)
        for key in to_add:
            db.ensure_entry(TABLE, key, {}, exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    after = dict((key, before.get(key, {})) for key in after_keys)
    changed = bool(to_add or to_remove)
    module.exit_json(**build_result(changed, before, after, servers=after_keys))


def main():
    run_module()


if __name__ == '__main__':
    main()
