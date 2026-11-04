#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: ntp
short_description: Configure global NTP settings on SONiC
version_added: "0.4.0"
description:
  - Manage the global NTP client settings in the C(NTP|global) entry of the
    SONiC configuration database, that is the daemon state, authentication,
    whether servers handed out by DHCP are used, the server role, the source
    interface and the VRF the daemon runs in.
  - Only the options that are given are written; the other fields of the
    entry are left alone. There is no C(config ntp) command for these settings,
    so the module is the declarative equivalent of editing C(config_db.json).
  - SONiC's C(hostcfgd) restarts the time daemon (C(chrony) or C(ntpd),
    depending on the release) when the entry changes and the daemon regenerates
    its configuration from CONFIG_DB on the way up.
  - The servers themselves are managed with M(community.sonic.ntp_server) and
    the authentication keys with M(community.sonic.ntp_key).
  - Global NTP settings exist from SONiC 202305 on, where the C(NTP|global)
    entry is seeded with its defaults by C(init_cfg.json). The module fails
    when the entry does not exist, which is the case on older releases that
    only know the C(NTP_SERVER) table.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  enabled:
    description:
      - Whether the NTP client is enabled (C(admin_state)).
    type: bool
  authentication:
    description:
      - Whether NTP authentication is enabled (C(authentication)). With
        authentication enabled the daemon only uses servers that have a
        C(key) from M(community.sonic.ntp_key).
    type: bool
  dhcp:
    description:
      - Whether NTP servers received through DHCP are used in addition to the
        configured servers (C(dhcp)). Disable it when the management network
        hands out NTP servers that should not be used.
    type: bool
  server_role:
    description:
      - Whether the switch also serves time to NTP clients (C(server_role)).
    type: bool
  source_interface:
    description:
      - The interface whose address is used as the source of NTP requests
        (C(src_intf)), for example V(eth0) or V(Loopback0).
      - Physical ports may be given by alias; the canonical name is stored.
      - An empty string removes the source interface so the daemon lets the
        kernel pick the source address.
    type: str
  vrf:
    description:
      - The VRF the NTP daemon runs in (C(vrf)). V(mgmt) is only honoured when
        the management VRF is enabled.
    type: str
    choices: [default, mgmt]
notes:
  - At least one option must be given.
  - Changing the settings restarts the time daemon, which can take a few
    seconds to come back. The module returns as soon as the configuration
    database is updated.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: NTP over the management VRF, static servers only
  community.sonic.ntp:
    enabled: true
    dhcp: false
    source_interface: eth0
    vrf: mgmt

- name: Use Loopback0 as the NTP source and require authentication
  community.sonic.ntp:
    source_interface: Loopback0
    authentication: true

- name: Let the kernel pick the source address again
  community.sonic.ntp:
    source_interface: ''

- name: Turn the NTP client off
  community.sonic.ntp:
    enabled: false
'''

RETURN = r'''
source_interface:
  description: The source interface name as stored in CONFIG_DB, when O(source_interface) was given.
  type: str
  returned: when O(source_interface) is set
  sample: Ethernet0
diff:
  description: The C(NTP|global) entry before and after the change.
  type: dict
  returned: always
  sample: {'before': {'admin_state': 'enabled', 'dhcp': 'enabled', 'src_intf': 'eth0', 'vrf': 'default'},
           'after': {'admin_state': 'enabled', 'dhcp': 'disabled', 'src_intf': 'eth0', 'vrf': 'mgmt'}}
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    UnknownInterfaceError,
    bool_to_enabled_disabled,
    resolve_interface_name,
)

TABLE = 'NTP'
KEY = 'global'

_MGMT_PORT_RE = re.compile(r'^eth\d+$')

#: Module option -> CONFIG_DB field for the boolean settings.
BOOL_FIELDS = (
    ('enabled', 'admin_state'),
    ('authentication', 'authentication'),
    ('dhcp', 'dhcp'),
    ('server_role', 'server_role'),
)

OPTIONS = tuple(option for option, dummy in BOOL_FIELDS) + ('source_interface', 'vrf')


class NtpNotSupportedError(ConfigDBError):
    """Raised when the release has no ``NTP|global`` entry to manage."""


def resolve_source_interface(port_table, mgmt_port_table, name):
    """Return the CONFIG_DB name of the NTP source interface.

    Physical ports may be given by alias. PortChannel, Vlan and Loopback names
    pass through and so do management ports (``eth0``), which are not in the
    ``PORT`` table.
    """
    try:
        return resolve_interface_name(port_table, name)
    except UnknownInterfaceError:
        if name in mgmt_port_table or _MGMT_PORT_RE.match(str(name)):
            return name
        raise UnknownInterfaceError('could not find interface "%s" to use as the NTP source interface' % name)


def build_ntp_entry(enabled=None, authentication=None, dhcp=None, server_role=None,
                    source_interface=None, vrf=None):
    """Return the fields to merge into ``NTP|global`` for the given options.

    ``source_interface`` is expected to be resolved already; an empty string
    maps to ``None`` which removes the field.
    """
    requested = dict(enabled=enabled, authentication=authentication, dhcp=dhcp, server_role=server_role)
    desired = {}
    for option, field in BOOL_FIELDS:
        if requested[option] is not None:
            desired[field] = bool_to_enabled_disabled(requested[option])
    if source_interface is not None:
        desired['src_intf'] = source_interface or None
    if vrf is not None:
        desired['vrf'] = vrf
    return desired


def run_module():
    module_args = dict(
        enabled=dict(type='bool'),
        authentication=dict(type='bool'),
        dhcp=dict(type='bool'),
        server_role=dict(type='bool'),
        source_interface=dict(type='str'),
        vrf=dict(type='str', choices=['default', 'mgmt']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_one_of=[OPTIONS],
    )
    params = module.params

    db = ConfigDB(module).connect()

    source_interface = params['source_interface']
    extra = {}
    try:
        if not db.has_entry(TABLE, KEY):
            raise NtpNotSupportedError(
                'the %s|%s entry does not exist in CONFIG_DB; SONiC seeds it from init_cfg.json on '
                'releases from 202305 on, so this image probably predates global NTP settings. '
                'Only NTP servers (community.sonic.ntp_server) can be configured on it.' % (TABLE, KEY))
        if source_interface:
            source_interface = resolve_source_interface(db.port_table(), db.get_table('MGMT_PORT'), source_interface)
            extra['source_interface'] = source_interface
        desired = build_ntp_entry(enabled=params['enabled'], authentication=params['authentication'],
                                  dhcp=params['dhcp'], server_role=params['server_role'],
                                  source_interface=source_interface, vrf=params['vrf'])
        change = db.ensure_entry(TABLE, KEY, desired, exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(**extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
