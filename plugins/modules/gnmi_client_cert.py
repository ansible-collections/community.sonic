#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: gnmi_client_cert
short_description: Authorise gNMI clients by certificate common name on SONiC
version_added: "0.4.0"
description:
  - Manage the C(GNMI_CLIENT_CERT) table of the SONiC configuration database,
    which maps the common name of a client certificate to the roles it is
    granted when the gNMI server authenticates by certificate
    (O(community.sonic.gnmi_server#module:user_auth) includes V(cert)).
  - This is the declarative equivalent of C(config gnmi client-cert add/del)
    (C(config telemetry client-cert) on older images). The gNMI daemon reads
    the table on every connection, so no restart is needed.
  - The module owns the whole entry; the stored role list is made exactly
    O(role).
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  common_name:
    description: The common name (CN) of the client certificate, as presented by the collector.
    type: str
    required: true
    aliases: [cn]
  role:
    description:
      - The roles granted to the client, stored in the C(role@) field.
      - SONiC defines V(gnmi_readonly), V(gnmi_readwrite) and V(gnmi_config_db_readwrite),
        plus V(gnmi_config_db_readwrite_ipv6) on some images. Other values are
        passed through for images with further roles.
      - Required when O(state=present).
    type: list
    elements: str
    aliases: [roles]
  state:
    description: Whether the mapping should be present or absent.
    type: str
    choices: [present, absent]
    default: present
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Let the collector read everything over gNMI
  community.sonic.gnmi_client_cert:
    common_name: collector.example.net
    role: gnmi_readonly

- name: Grant an automation host write access as well
  community.sonic.gnmi_client_cert:
    common_name: automation.example.net
    role:
      - gnmi_readonly
      - gnmi_readwrite

- name: Revoke a mapping
  community.sonic.gnmi_client_cert:
    common_name: old-collector.example.net
    state: absent
'''

RETURN = r'''
common_name:
  description: The certificate common name the mapping is stored under.
  type: str
  returned: always
  sample: collector.example.net
role:
  description: The roles after the change (what a real run would store in check mode); empty when absent.
  type: list
  elements: str
  returned: always
  sample: [gnmi_readonly]
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError

TABLE = 'GNMI_CLIENT_CERT'


def build_client_cert_entry(state, role=None):
    """Return the ``GNMI_CLIENT_CERT`` entry for the given options, or ``None`` for ``state=absent``.

    Duplicate roles are dropped while keeping the order given. Raises
    ``ValueError`` when no role is left.
    """
    if state == 'absent':
        return None
    roles = []
    for item in role or ():
        item = str(item).strip()
        if item and item not in roles:
            roles.append(item)
    if not roles:
        raise ValueError('at least one role is required')
    return {'role': roles}


def run_module():
    module_args = dict(
        common_name=dict(type='str', required=True, aliases=['cn']),
        role=dict(type='list', elements='str', aliases=['roles']),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=(('state', 'present', ('role',)),),
    )
    params = module.params
    common_name = params['common_name'].strip()
    if not common_name:
        module.fail_json(msg='common_name must not be empty')

    try:
        desired = build_client_cert_entry(params['state'], params['role'])
    except ValueError as e:
        module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()
    try:
        change = db.ensure_entry(TABLE, common_name, desired, exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(common_name=common_name, role=list(change.after.get('role', []))))


def main():
    run_module()


if __name__ == '__main__':
    main()
