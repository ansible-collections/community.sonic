#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: mgmt_vrf
short_description: Enable or disable the SONiC management VRF
version_added: "0.4.0"
description:
  - Enable or disable the management VRF (C(mgmt)) that isolates out-of-band
    management traffic from the front panel routing table.
  - Writes C(mgmtVrfEnabled) in the C(MGMT_VRF_CONFIG|vrf_global) entry of
    CONFIG_DB. Other fields of the entry are left alone. A missing entry is
    treated as disabled, so O(enabled=false) on a switch that never had the
    management VRF does not report a change.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  enabled:
    description: Whether the management VRF should be enabled.
    type: bool
    required: true
notes:
  - SONiC's C(hostcfgd) applies the change immediately by restarting the
    C(interfaces-config) service, which moves C(eth0) into or out of the
    C(mgmt) VRF. B(If Ansible connects through the management interface, the
    SSH connection drops.) Run the task with C(ignore_unreachable) and
    reconnect with M(ansible.builtin.wait_for_connection).
  - With the management VRF enabled, management services such as NTP, DNS,
    syslog and sFlow collectors need their C(vrf) set to C(mgmt).
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Keep management traffic in its own VRF, then reconnect
  block:
    - name: Enable the management VRF (drops the SSH connection when it changes)
      community.sonic.mgmt_vrf:
        enabled: true
      register: mgmt_vrf
      ignore_unreachable: true

    - name: Reconnect after the management interface moved into the VRF
      when: mgmt_vrf is changed or mgmt_vrf is unreachable
      block:
        - name: Drop the old SSH connection
          ansible.builtin.meta: reset_connection

        - name: Wait for the switch to come back
          ansible.builtin.wait_for_connection:
            delay: 5
            timeout: 120

- name: Disable the management VRF
  community.sonic.mgmt_vrf:
    enabled: false
'''

RETURN = r'''
enabled:
  description: Whether the management VRF is enabled after the run.
  type: bool
  returned: always
  sample: true
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    EntryChange,
    bool_to_true_false,
    str_to_bool,
)

MGMT_VRF_TABLE = 'MGMT_VRF_CONFIG'
MGMT_VRF_KEY = 'vrf_global'
MGMT_VRF_FIELD = 'mgmtVrfEnabled'


def is_mgmt_vrf_enabled(entry):
    """Interpret a ``MGMT_VRF_CONFIG|vrf_global`` entry; a missing field or entry means disabled."""
    return str_to_bool(entry.get(MGMT_VRF_FIELD), default=False)


def ensure_mgmt_vrf(db, enabled):
    """Make the management VRF state match ``enabled`` and return an :class:`EntryChange`.

    Nothing is written when the current state already matches, including when
    the entry is missing and ``enabled`` is false.
    """
    before = db.get_entry(MGMT_VRF_TABLE, MGMT_VRF_KEY)
    if is_mgmt_vrf_enabled(before) == enabled:
        return EntryChange(False, before, before)
    return db.ensure_entry(MGMT_VRF_TABLE, MGMT_VRF_KEY, {MGMT_VRF_FIELD: bool_to_true_false(enabled)}, exclusive=False)


def run_module():
    module_args = dict(
        enabled=dict(type='bool', required=True),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )
    enabled = module.params['enabled']

    db = ConfigDB(module).connect()
    try:
        change = ensure_mgmt_vrf(db, enabled)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(enabled=enabled))


def main():
    run_module()


if __name__ == '__main__':
    main()
