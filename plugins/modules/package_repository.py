#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: package_repository
short_description: Manage SONiC package manager repositories
version_added: "0.4.0"
description:
  - Adds and removes entries in the SONiC Package Manager (SPM) package
    database, the same way C(sonic-package-manager repository add) and
    C(sonic-package-manager repository remove) do.
  - A repository entry tells SPM where to pull a SONiC application extension
    from. Install the package itself with M(community.sonic.package).
  - The current state is read from the package database
    C(/var/lib/sonic-package-manager/packages.json) (or from
    C(sonic-package-manager list) when the file is not readable), so the
    module is idempotent and does not depend on SPM exit codes.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
requirements:
  - The C(sonic-package-manager) utility on the SONiC host.
  - "Root privileges (for example C(become: true)) to add or remove a
    repository. Reading the current state, in check mode or when nothing has
    to change, works as any user."
options:
  name:
    description:
      - Name of the package entry, as shown by C(sonic-package-manager list).
    type: str
    required: true
  repository:
    description:
      - The Docker repository to pull the package from, for example
        C(registry.example.net/sonic/my-exporter).
      - Required when O(state=present).
    type: str
  default_reference:
    description:
      - The tag or C(sha256:...) digest installed when no version is given
        to M(community.sonic.package) (or with O(community.sonic.package#module:state=latest)).
      - When omitted, an existing default reference is left untouched.
    type: str
  description:
    description:
      - Description shown by C(sonic-package-manager list).
      - When omitted, an existing description is left untouched.
    type: str
  state:
    description:
      - Whether the repository entry should exist.
      - SPM has no command to modify an entry. When O(repository),
        O(default_reference) or O(description) differ from the stored entry,
        the module removes and re-adds it, which SPM only allows while the
        package is not installed.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Built-in packages (C(database), C(swss), ...) cannot be modified or removed.
  - Removing the entry of an installed package fails; uninstall it first with
    M(community.sonic.package).
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Register the exporter repository
  community.sonic.package_repository:
    name: my-exporter
    repository: registry.example.net/sonic/my-exporter
    default_reference: "1.4.2"
    description: Prometheus exporter for platform sensors
  become: true

- name: Remove the repository entry
  community.sonic.package_repository:
    name: my-exporter
    state: absent
  become: true
'''

RETURN = r'''
name:
  description: Name of the package entry.
  type: str
  returned: always
  sample: my-exporter
repository:
  description: The repository stored in the package database after the module ran, if the entry exists.
  type: str
  returned: always
  sample: registry.example.net/sonic/my-exporter
default_reference:
  description: The default reference stored in the package database after the module ran.
  type: str
  returned: always
  sample: "1.4.2"
description:
  description: The description stored in the package database after the module ran.
  type: str
  returned: always
  sample: Prometheus exporter for platform sensors
status:
  description: Installation status as shown by C(sonic-package-manager list), or V(Absent) when there is no entry.
  type: str
  returned: always
  sample: Not Installed
commands:
  description: The C(sonic-package-manager) commands that were run. Empty when nothing changed or in check mode.
  type: list
  elements: str
  returned: always
  sample: ['/usr/local/bin/sonic-package-manager repository add my-exporter registry.example.net/sonic/my-exporter']
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.package_manager import (
    PackageManager, PackageManagerError)


FIELDS = ('repository', 'default_reference', 'description')


def entry_view(entry):
    """The part of a database entry the module manages; ``{}`` for a missing entry."""
    if entry is None:
        return {}
    return dict((field, entry.get(field)) for field in FIELDS)


def desired_view(params, current):
    """Build the entry the module wants from the parameters.

    Options that are not given keep the value already stored, so a play that
    only names the repository does not clear the description.
    """
    desired = {}
    for field in FIELDS:
        if params.get(field) is not None:
            desired[field] = params[field]
        else:
            desired[field] = current.get(field)
    return desired


def add_arguments(name, desired):
    args = ['repository', 'add', name, desired['repository']]
    if desired.get('default_reference') is not None:
        args += ['--default-reference', desired['default_reference']]
    if desired.get('description') is not None:
        args += ['--description', desired['description']]
    return args


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        repository=dict(type='str'),
        default_reference=dict(type='str'),
        description=dict(type='str'),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=[('state', 'present', ('repository',))],
    )

    name = module.params['name']
    state = module.params['state']
    spm = PackageManager(module)

    try:
        database = spm.read_database()
        entry = database.get(name)
        before = entry_view(entry)

        if state == 'absent':
            after = {}
            if entry is not None:
                if entry['built_in']:
                    module.fail_json(msg='package %s is built-in and cannot be removed' % name)
                if entry['installed']:
                    module.fail_json(msg='package %s is installed (version %s); uninstall it with '
                                         'community.sonic.package state=absent before removing its repository'
                                         % (name, entry['version']))
                if not module.check_mode:
                    spm.run_privileged(['repository', 'remove', name],
                                       'sonic-package-manager repository remove %s' % name)
        else:
            after = desired_view(module.params, before)
            if after != before:
                if entry is not None:
                    if entry['built_in']:
                        module.fail_json(msg='package %s is built-in and cannot be modified' % name)
                    if entry['installed']:
                        module.fail_json(msg='package %s is installed (version %s); its repository entry can only '
                                             'be changed while the package is not installed' % (name, entry['version']))
                if not module.check_mode:
                    if entry is not None:
                        spm.run_privileged(['repository', 'remove', name],
                                           'sonic-package-manager repository remove %s' % name)
                    spm.run_privileged(add_arguments(name, after),
                                       'sonic-package-manager repository add %s' % name)

        changed = after != before
        if changed and not module.check_mode:
            entry = spm.read_database().get(name)
            after = entry_view(entry)
    except PackageManagerError as e:
        module.fail_json(msg=str(e), commands=spm.commands, **e.details)

    result = dict(
        changed=changed,
        name=name,
        repository=after.get('repository'),
        default_reference=after.get('default_reference'),
        description=after.get('description'),
        status='Absent' if not after else (entry['status'] if entry is not None else 'Not Installed'),
        commands=spm.commands,
        diff=dict(before=before, after=after),
    )
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
