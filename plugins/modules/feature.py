#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: feature
short_description: Enable or disable SONiC features (containers)
version_added: "0.4.0"
description:
  - Manage the C(FEATURE) table of the SONiC configuration database, which
    switches optional containers such as C(sflow), C(snmp), C(lldp),
    C(dhcp_relay), C(telemetry), C(gnmi), C(macsec) or C(nat) on and off.
  - This is the declarative equivalent of C(config feature state),
    C(config feature autorestart) and C(config feature high_mem_alert).
    C(hostcfgd) reacts to the change by starting or stopping the feature's
    systemd unit, so writing the configuration database is enough.
  - Only the fields that are given are written; the many informational fields
    of a feature entry (C(has_global_scope), C(delayed), ...) are left alone.
  - Features whose state or auto restart is C(always_enabled) or
    C(always_disabled) cannot be changed and the module fails when asked to.
    Requesting the value such a feature already has is not a change.
  - The module fails for feature names that do not exist on the device.
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
      - The feature name as listed by C(show feature status), for example
        V(sflow), V(snmp), V(dhcp_relay), V(lldp), V(telemetry), V(gnmi),
        V(macsec) or V(nat).
    required: true
    type: str
  enabled:
    description:
      - Whether the feature (and its container) is enabled.
      - V(true) sets C(state=enabled) and V(false) sets C(state=disabled).
      - Omitting this option leaves the state untouched.
    type: bool
  auto_restart:
    description:
      - Whether the feature's container is restarted automatically when it crashes.
      - V(true) sets C(auto_restart=enabled) and V(false) sets C(auto_restart=disabled).
      - Omitting this option leaves the setting untouched.
    type: bool
  high_mem_alert:
    description:
      - Whether a high memory usage alert is raised for the feature's container.
      - V(true) sets C(high_mem_alert=enabled) and V(false) sets C(high_mem_alert=disabled).
      - Omitting this option leaves the setting untouched.
    type: bool
notes:
  - Enabling a feature starts its container, which can take a while. The
    module returns as soon as the configuration database is updated; check
    C(show feature status) or the systemd unit if you need to wait for it.
  - At least one of O(enabled), O(auto_restart) or O(high_mem_alert) must be given.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Enable sFlow
  community.sonic.feature:
    name: sflow
    enabled: true

- name: Run only the containers we need
  community.sonic.feature:
    name: "{{ item.name }}"
    enabled: "{{ item.enabled }}"
  loop:
    - { name: sflow, enabled: true }
    - { name: snmp, enabled: false }
    - { name: dhcp_relay, enabled: false }
    - { name: macsec, enabled: false }

- name: Do not restart the SNMP container automatically, alert on high memory use
  community.sonic.feature:
    name: snmp
    auto_restart: false
    high_mem_alert: true
'''

RETURN = r'''
name:
  description: The feature name.
  type: str
  returned: always
  sample: sflow
state:
  description: The feature state after the change (what a real run would store in check mode).
  type: str
  returned: always
  sample: enabled
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    bool_to_enabled_disabled,
)


#: Field values that lock a feature; ``config feature`` refuses to change them as well.
LOCKED_VALUES = {
    'always_enabled': 'enabled',
    'always_disabled': 'disabled',
}

#: Module option -> CONFIG_DB field.
FIELDS = (
    ('enabled', 'state'),
    ('auto_restart', 'auto_restart'),
    ('high_mem_alert', 'high_mem_alert'),
)


class FeatureError(ConfigDBError):
    """Raised for an unknown feature or an attempt to change a locked field."""


def build_feature_entry(name, current, enabled=None, auto_restart=None, high_mem_alert=None):
    """Return the fields to merge into ``FEATURE|<name>`` for the given options.

    ``current`` is the stored entry; an empty entry means the feature does not
    exist and raises :class:`FeatureError`. A field whose stored value is
    ``always_enabled``/``always_disabled`` is dropped from the result when the
    requested value matches and raises :class:`FeatureError` otherwise, so
    the caller never writes to a locked field.
    """
    if not current:
        raise FeatureError('feature "%s" does not exist on this device; see "show feature status"' % name)

    requested = dict(enabled=enabled, auto_restart=auto_restart, high_mem_alert=high_mem_alert)
    desired = {}
    for option, field in FIELDS:
        value = requested[option]
        if value is None:
            continue
        wanted = bool_to_enabled_disabled(value)
        stored = current.get(field)
        if stored in LOCKED_VALUES:
            if LOCKED_VALUES[stored] != wanted:
                raise FeatureError(
                    'feature "%s" has %s=%s, which cannot be changed to %s' % (name, field, stored, wanted))
            continue
        desired[field] = wanted
    return desired


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        enabled=dict(type='bool'),
        auto_restart=dict(type='bool'),
        high_mem_alert=dict(type='bool'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_one_of=[['enabled', 'auto_restart', 'high_mem_alert']],
        supports_check_mode=True,
    )

    name = module.params['name']
    db = ConfigDB(module).connect()
    try:
        current = db.get_entry('FEATURE', name)
        desired = build_feature_entry(name, current,
                                      enabled=module.params['enabled'],
                                      auto_restart=module.params['auto_restart'],
                                      high_mem_alert=module.params['high_mem_alert'])
        change = db.ensure_entry('FEATURE', name, desired, exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(name=name, state=change.after.get('state')))


def main():
    run_module()


if __name__ == '__main__':
    main()
