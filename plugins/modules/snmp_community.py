#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: snmp_community
short_description: Configure SONiC SNMP community strings
version_added: "0.4.0"
description:
  - Manage SNMPv1/v2c community strings in the C(SNMP_COMMUNITY) table of the
    SONiC configuration database, the equivalent of
    C(config snmp community add/replace/del).
  - The community string is a secret. The O(name) option is C(no_log) and the
    string is kept out of the result, the diff and the failure messages.
  - The same rules as the SONiC CLI apply. A community string is 1 to 32
    characters long and must not contain C(@) or C(:).
  - SONiC renders C(snmpd.conf) from this table when the C(snmp) container
    starts, and the CLI restarts C(snmp.service) after every change. This
    module only writes the configuration database, so restart the service
    (for example with M(ansible.builtin.systemd_service) from a handler) when
    the result reports a change.
  - The SNMP agent only runs when the C(snmp) feature is enabled in the
    C(FEATURE) table (C(config feature state snmp enabled)). Communities can
    be written while it is disabled.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description:
      - The community string. It is not logged and does not appear in the module result.
    type: str
    required: true
  type:
    description:
      - The access the community grants, read-only or read-write; stored as C(TYPE).
      - Ignored with O(state=absent).
    type: str
    default: RO
    choices: [RO, RW]
  state:
    description: Whether the community should be present or absent.
    default: present
    type: str
    choices: [present, absent]
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Read-only community
  community.sonic.snmp_community:
    name: "{{ snmp_ro_community }}"
    type: RO
  notify: Restart snmp

- name: Read-write community
  community.sonic.snmp_community:
    name: "{{ snmp_rw_community }}"
    type: RW
  notify: Restart snmp

- name: Remove the default community
  community.sonic.snmp_community:
    name: public
    state: absent
  notify: Restart snmp

# The CLI restarts the SNMP service after every change; do the same from a handler.
- name: Restart snmp
  ansible.builtin.systemd_service:
    name: snmp
    state: restarted
  become: true
'''

RETURN = r'''
type:
  description: The access type stored for the community after the change (predicted in check mode).
  type: str
  returned: when O(state=present)
  sample: RO
diff:
  description:
    - The C(SNMP_COMMUNITY) entry before and after the change; C({}) when absent.
    - The community string itself is the entry key and is not part of the diff.
  type: dict
  returned: always
  sample: {"before": {}, "after": {"TYPE": "RO"}}
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError

TABLE = 'SNMP_COMMUNITY'

#: Limits enforced by ``config snmp community`` and the sonic-snmp YANG model.
MAX_COMMUNITY_LENGTH = 32
FORBIDDEN_CHARACTERS = ('@', ':')


def validate_community(name):
    """Raise ``ValueError`` unless ``name`` is a community string SONiC accepts.

    The messages never contain the community string itself.
    """
    if not name or len(name) > MAX_COMMUNITY_LENGTH:
        raise ValueError('the community string must be 1 to %d characters long' % MAX_COMMUNITY_LENGTH)
    if any(c in name for c in FORBIDDEN_CHARACTERS):
        raise ValueError('the community string must not contain %s'
                         % ' or '.join('"%s"' % c for c in FORBIDDEN_CHARACTERS))


def build_community_entry(community_type, state):
    """Return the ``SNMP_COMMUNITY`` entry for the given type, ``None`` for ``state=absent``."""
    if state == 'absent':
        return None
    return {'TYPE': community_type}


def run_module():
    module_args = dict(
        name=dict(type='str', required=True, no_log=True),
        type=dict(type='str', default='RO', choices=['RO', 'RW']),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    name = module.params['name']
    state = module.params['state']

    try:
        validate_community(name)
    except ValueError as e:
        module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()
    try:
        change = db.ensure_entry(TABLE, name, build_community_entry(module.params['type'], state), exclusive=True)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    extra = {}
    if state == 'present':
        extra['type'] = change.after.get('TYPE')
    module.exit_json(**change.result(**extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
