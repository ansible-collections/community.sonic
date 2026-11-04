#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: ntp_key
short_description: Configure NTP authentication keys on SONiC
version_added: "0.4.0"
description:
  - Manage the NTP authentication keys in the SONiC C(NTP_KEY) table
    (SONiC 202305 and later).
  - SONiC stores the key value base64 encoded and decodes it when it writes
    the daemon's key file, so O(value) is the key as the daemon expects it and
    the module takes care of the encoding.
  - The key value is a secret. It is never logged and the C(diff) shows a
    placeholder instead of the stored value.
  - A server uses a key through the C(key) option of
    M(community.sonic.ntp_server), and authentication is switched on with
    M(community.sonic.ntp).
  - SONiC's C(hostcfgd) restarts the time daemon when the table changes and
    the daemon regenerates its key file from CONFIG_DB on the way up.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  id:
    description:
      - The key ID, between 1 and 65535.
    type: int
    required: true
  type:
    description:
      - The digest or MAC algorithm the key is used with (C(type)).
      - Defaults to V(md5) on the device when a key is created without it.
    type: str
    choices: [md5, sha1, sha256, sha384, sha512]
  value:
    description:
      - The key itself (C(value)), in the form the daemon reads from its key
        file, for example a plain ASCII string or V(HEX:...) for C(chrony).
      - Required when the key does not exist yet; leave it out to change
        O(type) or O(trusted) of an existing key without re-supplying the secret.
    type: str
  trusted:
    description:
      - Whether the key is trusted for authenticating servers (C(trusted)).
    type: bool
  state:
    description: Whether the key should be present or absent.
    default: present
    type: str
    choices: [present, absent]
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Add a trusted SHA-256 key
  community.sonic.ntp_key:
    id: 42
    type: sha256
    value: "{{ ntp_key_42 }}"
    trusted: true

- name: Stop trusting a key, keeping its value
  community.sonic.ntp_key:
    id: 42
    trusted: false

- name: Remove a key
  community.sonic.ntp_key:
    id: 42
    state: absent
'''

RETURN = r'''
id:
  description: The key ID.
  type: int
  returned: always
  sample: 42
diff:
  description: The C(NTP_KEY) entry before and after the change, with the key value replaced by a placeholder.
  type: dict
  returned: always
  sample: {'before': {}, 'after': {'type': 'sha256', 'value': 'VALUE_SPECIFIED_IN_NO_LOG_PARAMETER', 'trusted': 'yes'}}
'''

import base64

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    build_result,
)

TABLE = 'NTP_KEY'

#: Key IDs are 16 bit unsigned and 0 is reserved, see sonic-ntp.yang.
MIN_KEY_ID = 1
MAX_KEY_ID = 65535

#: What the diff shows instead of the stored key value.
VALUE_PLACEHOLDER = 'VALUE_SPECIFIED_IN_NO_LOG_PARAMETER'


def encode_value(value):
    """Return the base64 form of a key value, which is what SONiC stores in CONFIG_DB."""
    return base64.b64encode(value.encode('utf-8')).decode('ascii')


def build_key_entry(key_type=None, value=None, trusted=None):
    """Return the fields to merge into an ``NTP_KEY`` entry; options left at ``None`` are not written."""
    desired = {}
    if key_type is not None:
        desired['type'] = key_type
    if value is not None:
        desired['value'] = encode_value(value)
    if trusted is not None:
        desired['trusted'] = 'yes' if trusted else 'no'
    return desired


def mask_value(entry):
    """Return a copy of an entry with the key value replaced by :data:`VALUE_PLACEHOLDER`."""
    masked = dict(entry)
    if 'value' in masked:
        masked['value'] = VALUE_PLACEHOLDER
    return masked


def run_module():
    module_args = dict(
        id=dict(type='int', required=True),
        type=dict(type='str', choices=['md5', 'sha1', 'sha256', 'sha384', 'sha512']),
        value=dict(type='str', no_log=True),
        trusted=dict(type='bool'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )
    params = module.params

    key_id = params['id']
    if not MIN_KEY_ID <= key_id <= MAX_KEY_ID:
        module.fail_json(msg='id must be between %d and %d, got %d' % (MIN_KEY_ID, MAX_KEY_ID, key_id))
    if params['value'] == '':
        module.fail_json(msg='value must not be empty')

    db = ConfigDB(module).connect()
    try:
        if params['state'] == 'absent':
            change = db.ensure_absent(TABLE, key_id)
        else:
            if params['value'] is None and not db.has_entry(TABLE, key_id):
                module.fail_json(msg='NTP key %d does not exist yet, so value is required to create it' % key_id)
            desired = build_key_entry(key_type=params['type'], value=params['value'], trusted=params['trusted'])
            change = db.ensure_entry(TABLE, key_id, desired, exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**build_result(change.changed, mask_value(change.before), mask_value(change.after), id=key_id))


def main():
    run_module()


if __name__ == '__main__':
    main()
