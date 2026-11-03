#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: config_save
short_description: Persist the running SONiC configuration to the startup configuration file
version_added: "0.4.0"
description:
  - Saves the running configuration database (CONFIG_DB) to the startup
    configuration file, by default C(/etc/sonic/config_db.json), the same
    way C(config save -y) does.
  - Unlike running C(config save) through M(ansible.builtin.command), the
    module compares the running configuration with the saved file first and
    only writes, and reports C(changed), when they differ. This makes it
    safe to use as a handler or at the end of every play.
  - The running configuration is read with C(sonic-cfggen -d --print-data)
    and the file is written with C(config save -y), so the result is
    byte-for-byte what SONiC itself would have written.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
    details:
      - The diff contains only the tables that differ between the saved file
        (I(before)) and the running configuration (I(after)).
requirements:
  - The C(sonic-cfggen) and C(config) utilities on the SONiC host.
  - "Root privileges (for example C(become: true)) to write the file. Comparing
    the running configuration with the file, in check mode or when nothing
    has changed, works as any user that can read the file."
options:
  path:
    description:
      - The startup configuration file to write.
      - The default is what SONiC loads at boot; only change it to save a copy
        of the running configuration elsewhere.
    type: path
    default: /etc/sonic/config_db.json
  backup:
    description:
      - Keep a timestamped copy of the previous file before overwriting it.
      - The copy is created next to I(path) and its name is returned in
        RV(backup_file). No copy is made when nothing changes, in check mode
        or when the file does not exist yet.
    type: bool
    default: false
  return_config:
    description:
      - Return the saved configuration in RV(config).
      - Useful to inspect what the switch will boot with, for example the
        C(DEVICE_METADATA) table, without an extra task.
    type: bool
    default: false
notes:
  - The module reads the whole running CONFIG_DB. Field order and whitespace
    in the file are ignored for the comparison; only the content counts.
  - A file that does not exist or cannot be parsed as JSON is treated as empty
    and overwritten.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Persist the running configuration
  community.sonic.config_save:
  become: true

- name: Persist the running configuration and keep a copy of the previous file
  community.sonic.config_save:
    backup: true
  become: true
  register: saved

- name: Show which tables were saved
  ansible.builtin.debug:
    var: saved.changed_tables

- name: Check what the switch will boot with without changing anything
  community.sonic.config_save:
    return_config: true
  check_mode: true
  register: startup

- name: Show the HWSKU and platform of the startup configuration
  ansible.builtin.debug:
    msg: >-
      {{ startup.config.DEVICE_METADATA.localhost.hwsku }} on
      {{ startup.config.DEVICE_METADATA.localhost.platform }}

# The handler pattern: every configuration module notifies the handler and
# the configuration is saved once, at the end of the play, only if something
# actually changed.
- name: Configure a switch and persist the result
  hosts: sonic
  gather_facts: false
  tasks:
    - name: Configure the uplink
      community.sonic.interface_port:
        interface: QSFP5
        speed: 100G
      notify: save sonic config

    - name: Add the server VLAN
      community.sonic.vlan:
        vlanid: 100
      notify: save sonic config

  handlers:
    - name: save sonic config
      community.sonic.config_save:
      become: true
'''

RETURN = r'''
path:
  description: The startup configuration file that was compared and written.
  type: str
  returned: always
  sample: /etc/sonic/config_db.json
changed_tables:
  description:
    - The CONFIG_DB tables that differ between the file and the running
      configuration, sorted by name. Empty when nothing changed.
  type: list
  elements: str
  returned: always
  sample: ['VLAN', 'VLAN_MEMBER']
backup_file:
  description: Name of the timestamped copy of the previous file.
  type: str
  returned: when O(backup=true), the file changed and not in check mode
  sample: "/etc/sonic/config_db.json.2026-11-03@14:05:11~"
config:
  description:
    - "The saved configuration as C({table: {key: entry}}). In check mode this
      is the running configuration that would have been saved."
  type: dict
  returned: when O(return_config=true)
  sample: {'DEVICE_METADATA': {'localhost': {'hostname': 'sonic', 'hwsku': 'Force10-S6000'}}}
'''

import errno
import json
import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.community.sonic.plugins.module_utils.config_db import normalize_entry


DEFAULT_PATH = '/etc/sonic/config_db.json'


def normalize_config(config):
    """Normalise a ``{table: {key: entry}}`` configuration for comparison.

    Entry values are converted to the strings (and lists of strings) that
    CONFIG_DB stores, and empty tables are dropped, so a hand-edited file and
    the output of ``sonic-cfggen -d --print-data`` compare equal when they
    describe the same configuration.
    """
    result = {}
    for table, entries in (config or {}).items():
        if not isinstance(entries, dict) or not entries:
            continue
        normalized = {}
        for key, entry in entries.items():
            if isinstance(entry, dict):
                normalized[key] = normalize_entry(entry)
            else:
                normalized[key] = entry
        result[table] = normalized
    return result


def config_diff(before, after):
    """Return ``(changed_tables, before_diff, after_diff)`` for two normalised configurations.

    Only the tables that differ are included in the diff dictionaries, which
    keeps the diff output readable even for a large configuration.
    """
    changed_tables = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
    before_diff = dict((t, before[t]) for t in changed_tables if t in before)
    after_diff = dict((t, after[t]) for t in changed_tables if t in after)
    return changed_tables, before_diff, after_diff


def _not_root_message(path):
    return ('writing %s requires root privileges; run the task with "become: true" '
            '(or as root)' % path)


def read_saved_config(module, path):
    """Read and parse the saved configuration file; ``{}`` if it does not exist or is not valid JSON."""
    try:
        with open(path, 'rb') as f:
            content = f.read()
    except (IOError, OSError) as e:
        if e.errno == errno.ENOENT:
            return {}
        if e.errno in (errno.EACCES, errno.EPERM):
            module.fail_json(msg='cannot read %s: %s; %s' % (path, to_native(e), _not_root_message(path)),
                             path=path)
        module.fail_json(msg='cannot read %s: %s' % (path, to_native(e)), path=path)
    try:
        config = json.loads(content.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        module.warn('%s is not valid JSON (%s); it will be overwritten' % (path, to_native(e)))
        return {}
    if not isinstance(config, dict):
        module.warn('%s does not contain a JSON object; it will be overwritten' % path)
        return {}
    return config


def read_running_config(module):
    """Return the running CONFIG_DB as parsed ``sonic-cfggen -d --print-data`` output."""
    cfggen = module.get_bin_path('sonic-cfggen', required=True)
    rc, out, err = module.run_command([cfggen, '-d', '--print-data'])
    if rc != 0:
        module.fail_json(msg='sonic-cfggen -d --print-data failed with rc %d: %s' % (rc, err.strip() or out.strip()),
                         rc=rc, stdout=out, stderr=err)
    try:
        config = json.loads(out)
    except ValueError as e:
        module.fail_json(msg='could not parse the output of sonic-cfggen -d --print-data: %s' % to_native(e),
                         stdout=out, stderr=err)
    if not isinstance(config, dict):
        module.fail_json(msg='unexpected output from sonic-cfggen -d --print-data: not a JSON object',
                         stdout=out, stderr=err)
    return config


def write_config(module, path):
    """Write the running configuration to ``path`` with ``config save -y``."""
    config_cmd = module.get_bin_path('config', required=True)
    rc, out, err = module.run_command([config_cmd, 'save', '-y', path])
    if rc != 0:
        module.fail_json(msg='config save -y %s failed with rc %d: %s' % (path, rc, err.strip() or out.strip()),
                         rc=rc, stdout=out, stderr=err, path=path)


def run_module():
    module_args = dict(
        path=dict(type='path', default=DEFAULT_PATH),
        backup=dict(type='bool', default=False),
        return_config=dict(type='bool', default=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    path = module.params['path']
    running = read_running_config(module)
    saved = read_saved_config(module, path)

    before = normalize_config(saved)
    after = normalize_config(running)
    changed_tables, before_diff, after_diff = config_diff(before, after)
    changed = bool(changed_tables)

    result = dict(
        changed=changed,
        path=path,
        changed_tables=changed_tables,
        diff=dict(before=before_diff, after=after_diff,
                  before_header=path, after_header='running CONFIG_DB'),
    )
    if module.params['return_config']:
        result['config'] = running

    if changed and not module.check_mode:
        if os.geteuid() != 0:
            module.fail_json(msg=_not_root_message(path), path=path, changed_tables=changed_tables)
        if module.params['backup'] and os.path.exists(path):
            result['backup_file'] = module.backup_local(path)
        write_config(module, path)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
