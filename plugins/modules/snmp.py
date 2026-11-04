#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: snmp
short_description: Configure the SONiC SNMP agent location and contact
version_added: "0.4.0"
description:
  - Manage the system location (C(sysLocation)) and contact (C(sysContact))
    reported by the SONiC SNMP agent. They are stored in the C(SNMP|LOCATION)
    and C(SNMP|CONTACT) entries of the configuration database, the equivalent
    of C(config snmp location add/modify/del) and
    C(config snmp contact add/modify/del).
  - Only the options that are given are managed. Setting O(location) leaves the
    contact alone and vice versa; O(state=absent) removes only the entries
    whose option is given.
  - SONiC renders C(snmpd.conf) from these entries when the C(snmp) container
    starts, and the CLI restarts C(snmp.service) after every change. This
    module only writes the configuration database, so restart the service
    (for example with M(ansible.builtin.systemd_service) from a handler) when
    the result reports a change.
  - The SNMP agent only runs when the C(snmp) feature is enabled in the
    C(FEATURE) table (C(config feature state snmp enabled)). The entries can
    be written while it is disabled.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  location:
    description:
      - The system location, stored as C(SNMP|LOCATION) C(Location).
      - With O(state=absent) the location entry is removed whatever its current value is.
    type: str
  contact:
    description:
      - The system contact, stored as C(SNMP|CONTACT) with the contact name as
        the field and the e-mail address as the value.
      - With O(state=absent) the contact entry is removed whatever its current value is.
    type: dict
    suboptions:
      name:
        description: The contact name, for example a team or a person.
        type: str
        required: true
      email:
        description:
          - The contact e-mail address.
          - Required with O(state=present), ignored with O(state=absent).
        type: str
  state:
    description:
      - V(present) sets the given location and contact.
      - V(absent) removes the location entry when O(location) is given and
        the contact entry when O(contact) is given.
    default: present
    type: str
    choices: [present, absent]
notes:
  - At least one of O(location) or O(contact) must be given.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: SNMP agent identity
  community.sonic.snmp:
    location: "Rack 12, Example DC"
    contact:
      name: noc
      email: noc@example.net
  notify: Restart snmp

- name: Change only the location
  community.sonic.snmp:
    location: "Rack 13, Example DC"

- name: Remove the contact, keep the location
  community.sonic.snmp:
    contact:
      name: noc
    state: absent

- name: Remove both
  community.sonic.snmp:
    location: "Rack 13, Example DC"
    contact:
      name: noc
    state: absent

# The CLI restarts the SNMP service after every change; do the same from a handler.
- name: Restart snmp
  ansible.builtin.systemd_service:
    name: snmp
    state: restarted
  become: true
'''

RETURN = r'''
location:
  description: The system location after the change (predicted in check mode), V(null) when none is configured.
  type: str
  returned: always
  sample: "Rack 12, Example DC"
contact:
  description: The system contact after the change (predicted in check mode), V(null) when none is configured.
  type: dict
  returned: always
  contains:
    name:
      description: The contact name.
      type: str
    email:
      description: The contact e-mail address.
      type: str
  sample: {"name": "noc", "email": "noc@example.net"}
diff:
  description: The managed C(SNMP) entries before and after the change, keyed by C(LOCATION) and C(CONTACT); absent entries are left out.
  type: dict
  returned: always
  sample: {"before": {}, "after": {"LOCATION": {"Location": "Rack 12, Example DC"}, "CONTACT": {"noc": "noc@example.net"}}}
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError, build_result

TABLE = 'SNMP'
LOCATION_KEY = 'LOCATION'
CONTACT_KEY = 'CONTACT'

#: Deliberately looser than the SONiC CLI, which rejects top-level domains longer than three letters.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def build_location_entry(location):
    """Return the ``SNMP|LOCATION`` entry for a location string."""
    return {'Location': location}


def build_contact_entry(name, email):
    """Return the ``SNMP|CONTACT`` entry: SONiC stores the name as the field and the e-mail as the value."""
    return {name: email}


def parse_location_entry(entry):
    """Return the location stored in an ``SNMP|LOCATION`` entry, ``None`` when there is none."""
    if not entry:
        return None
    return entry.get('Location')


def parse_contact_entry(entry):
    """Return ``{'name': ..., 'email': ...}`` for an ``SNMP|CONTACT`` entry, ``None`` when there is none.

    Like the SONiC CLI, only the first field is considered should the entry
    ever hold more than one.
    """
    if not entry:
        return None
    name = sorted(entry)[0]
    return {'name': name, 'email': entry[name]}


def validate_location(location):
    """Raise ``ValueError`` unless ``location`` is a usable location string."""
    if not str(location).strip():
        raise ValueError('location must not be empty; use state=absent to remove it')


def validate_contact(name, email):
    """Raise ``ValueError`` unless ``name`` and ``email`` form a usable contact."""
    if not str(name).strip():
        raise ValueError('contact name must not be empty')
    if email is None:
        raise ValueError('contact email is required when state=present')
    if not _EMAIL_RE.match(str(email)):
        raise ValueError('"%s" is not a valid e-mail address' % email)


def run_module():
    module_args = dict(
        location=dict(type='str'),
        contact=dict(type='dict', options=dict(
            name=dict(type='str', required=True),
            email=dict(type='str'),
        )),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_one_of=[('location', 'contact')],
        supports_check_mode=True,
    )

    state = module.params['state']
    location = module.params['location']
    contact = module.params['contact']

    desired = {}
    try:
        if location is not None:
            if state == 'present':
                validate_location(location)
                desired[LOCATION_KEY] = build_location_entry(location)
            else:
                desired[LOCATION_KEY] = None
        if contact is not None:
            if state == 'present':
                validate_contact(contact['name'], contact['email'])
                desired[CONTACT_KEY] = build_contact_entry(contact['name'], contact['email'])
            else:
                desired[CONTACT_KEY] = None
    except ValueError as e:
        module.fail_json(msg=str(e))

    db = ConfigDB(module).connect()
    try:
        before = {}
        for key in (LOCATION_KEY, CONTACT_KEY):
            entry = db.get_entry(TABLE, key)
            if entry:
                before[key] = entry
        after = dict(before)
        changed = False
        for key, entry in desired.items():
            change = db.ensure_entry(TABLE, key, entry, exclusive=True)
            changed = changed or change.changed
            if change.after:
                after[key] = change.after
            else:
                after.pop(key, None)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**build_result(
        changed, before, after,
        location=parse_location_entry(after.get(LOCATION_KEY)),
        contact=parse_contact_entry(after.get(CONTACT_KEY))))


def main():
    run_module()


if __name__ == '__main__':
    main()
