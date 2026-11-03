#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: package
short_description: Install and remove SONiC application extensions with sonic-package-manager
version_added: "0.4.0"
description:
  - Installs, upgrades, downgrades and uninstalls SONiC application extension
    packages with the SONiC Package Manager (SPM), C(sonic-package-manager).
  - Packages are installed from a repository registered with
    M(community.sonic.package_repository), directly from a registry
    reference, or from an image tarball copied to the switch (air-gapped or
    proxy-only management networks).
  - The installed state is read from the package database
    C(/var/lib/sonic-package-manager/packages.json) (or from
    C(sonic-package-manager list) when the file is not readable), not from
    SPM exit codes. A second run with the same version reports no change, and
    a different version maps to an upgrade (or, with O(allow_downgrade), a downgrade).
  - C(-y) is always passed so SPM never prompts.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
requirements:
  - The C(sonic-package-manager) utility on the SONiC host.
  - "Root privileges (for example C(become: true)) to install or uninstall.
    Reading the current state, in check mode or when nothing has to change,
    works as any user."
options:
  name:
    description:
      - Name of the package as shown by C(sonic-package-manager list), which
        is the C(package.name) of its manifest.
      - Without O(source) this must be a package registered with
        M(community.sonic.package_repository).
    type: str
    required: true
  version:
    description:
      - The version to install, passed to SPM as C(name==version) (or
        C(name@reference) for a tag or digest that is not a SemVer version).
      - "The module compares it with the installed version recorded by SPM,
        which is the C(package.version) of the manifest: use the manifest
        version (the tag of a SONiC package conventionally equals it), not a
        digest, or every run tries to reinstall."
      - When omitted with O(state=present), an installed package is left as it
        is and a missing one is installed from the repository's default
        reference (or from O(source)).
      - Ignored with O(state=latest) and O(state=absent).
      - With a registry O(source) that has no tag or digest, the version is
        appended as the tag.
    type: str
  source:
    description:
      - Install from somewhere other than a registered repository.
      - An absolute path, a path starting with C(./) or C(../), or the name
        of an existing file is an image tarball (C(docker save) output) and
        is passed with C(--from-tarball).
      - Anything else is a registry reference such as
        C(registry.example.net/sonic/my-exporter:1.4.2) and is passed with
        C(--from-repository).
      - SPM records the package under its manifest name, so O(name) must
        match the C(package.name) in the image manifest.
    type: str
  state:
    description:
      - V(present) installs the package when it is missing, and upgrades or
        downgrades it when O(version) is given and differs from the installed one.
      - V(latest) upgrades to the repository's default reference (see
        O(community.sonic.package_repository#module:default_reference)), or, when
        none is set, to the highest SemVer release tag the registry offers
        (pre-releases are skipped). With
        O(source) the manifest version of the source is used.
      - V(absent) uninstalls the package. The repository entry stays in the
        database; remove it with M(community.sonic.package_repository).
    type: str
    choices: [present, absent, latest]
    default: present
  enabled:
    description:
      - Enable the feature right after installation (C(--enable)), so the
        container starts and the FEATURE table entry is created with
        C(state=enabled). The default of SPM is a disabled feature.
      - Only used when the package is first installed; SPM does not accept
        it on an upgrade, and the module does not change the FEATURE state of
        an installed package. Use the feature module for that.
    type: bool
  owner:
    description:
      - Default owner of the feature (C(--set-owner)). Like O(enabled), only
        used when the package is first installed.
    type: str
    choices: [local, kube]
  allow_downgrade:
    description:
      - Allow installing an older version than the installed one
        (C(--allow-downgrade)). Without it SPM refuses a downgrade.
    type: bool
    default: false
  skip_host_plugins:
    description:
      - Do not install the host OS plugins (CLI, ...) the package provides
        (C(--skip-host-plugins)).
    type: bool
    default: false
  keep_config:
    description:
      - Keep the feature configuration in CONFIG_DB when uninstalling
        (C(uninstall --keep-config)).
    type: bool
    default: false
  force:
    description:
      - Pass C(--force) to SPM, which ignores dependency and manifest
        validation failures and, on uninstall, an enabled feature.
    type: bool
    default: false
  custom_name:
    description:
      - Install the package under a custom name (C(--name)). Required with O(manifest).
    type: str
  manifest:
    description:
      - Use the local manifest created with C(sonic-package-manager manifests
        create <custom_name>) instead of the one in the image
        (C(--use-local-manifest)). Requires O(custom_name).
    type: bool
notes:
  - SPM pulls images through dockerd, so a registry install needs the switch's
    HTTP proxy settings. Pass them with the C(environment) keyword of the
    task; on images where SPM does not handle the management VRF itself, run
    the module through C(ip vrf exec mgmt).
  - Installing a package creates a C(FEATURE) entry; its state and C(config save)
    are not managed here beyond the initial O(enabled).
  - Uninstalling fails while the feature is enabled unless O(force) is set.
  - C(sonic-package-manager migrate) is out of scope.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Install the exporter and run it
  community.sonic.package:
    name: my-exporter
    version: "1.4.2"
    enabled: true
  become: true

- name: Upgrade to the repository default reference
  community.sonic.package:
    name: my-exporter
    state: latest
  become: true

- name: Air-gapped install from a tarball
  community.sonic.package:
    name: my-exporter
    source: /tmp/my-exporter-1.4.2.tar
    version: "1.4.2"
  become: true

- name: Install directly from a registry through the management proxy
  community.sonic.package:
    name: my-exporter
    source: registry.example.net/sonic/my-exporter:1.4.2
    owner: local
  become: true
  environment:
    https_proxy: http://proxy.example.net:3128

- name: Downgrade
  community.sonic.package:
    name: my-exporter
    version: "1.4.1"
    allow_downgrade: true
  become: true

- name: Remove the package but keep its configuration
  community.sonic.package:
    name: my-exporter
    state: absent
    keep_config: true
  become: true
'''

RETURN = r'''
name:
  description: Name of the package.
  type: str
  returned: always
  sample: my-exporter
installed:
  description: Whether the package is installed after the module ran.
  type: bool
  returned: always
version:
  description: The installed version after the module ran. In check mode, the version that would be installed.
  type: str
  returned: always
  sample: "1.4.2"
repository:
  description: The repository the package is pulled from, as recorded in the package database.
  type: str
  returned: always
  sample: registry.example.net/sonic/my-exporter
status:
  description: Installation status as shown by C(sonic-package-manager list).
  type: str
  returned: always
  sample: Installed
commands:
  description: The C(sonic-package-manager) commands that were run. Empty when nothing changed or in check mode.
  type: list
  elements: str
  returned: always
  sample: ['/usr/local/bin/sonic-package-manager install -y my-exporter==1.4.2']
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.package_manager import (
    STATUS_NOT_INSTALLED, PackageManager, PackageManagerError, is_tarball_source, normalize_version,
    package_expression, package_status)


def state_view(entry):
    """The fields of a database entry the module reports and diffs; a not-installed view when missing."""
    if entry is None:
        return dict(installed=False, version=None, repository=None)
    return dict(installed=entry['installed'], version=entry['version'], repository=entry['repository'])


def source_arguments(source, version):
    """Return the ``--from-tarball``/``--from-repository`` arguments for ``source``."""
    if is_tarball_source(source):
        return ['--from-tarball', source]
    reference = source
    if version is not None and '@' not in source and ':' not in source.rsplit('/', 1)[-1]:
        reference = '%s:%s' % (source, version)
    return ['--from-repository', reference]


def install_arguments(params, version, upgrade=False):
    """Build the ``sonic-package-manager install`` arguments.

    SPM rejects options that do not apply to the operation it performs:
    ``--enable`` and ``--set-owner`` are only accepted when the package is
    not installed yet, ``--allow-downgrade`` only when it is.
    """
    args = ['install', '-y']
    if params['force']:
        args.append('--force')
    if params['skip_host_plugins']:
        args.append('--skip-host-plugins')
    if not upgrade:
        if params['enabled']:
            args.append('--enable')
        if params['owner'] is not None:
            args += ['--set-owner', params['owner']]
    elif params['allow_downgrade']:
        args.append('--allow-downgrade')
    if params['custom_name'] is not None:
        args += ['--name', params['custom_name']]
    if params['manifest']:
        args.append('--use-local-manifest')
    if params['source'] is not None:
        args += source_arguments(params['source'], version)
    else:
        args.append(package_expression(params['name'], version))
    return args


def uninstall_arguments(params):
    args = ['uninstall', '-y']
    if params['force']:
        args.append('--force')
    if params['keep_config']:
        args.append('--keep-config')
    args.append(params['name'])
    return args


def highest_version(versions):
    """Return the highest SemVer release in ``versions``; pre-releases and non-SemVer tags are ignored."""
    def key(version):
        return tuple(int(p) for p in version.split('+', 1)[0].split('.'))

    candidates = []
    for version in versions:
        version = version.strip()
        if not version or '-' in version:
            continue
        try:
            key(version)
        except ValueError:
            continue
        candidates.append(version)
    if not candidates:
        return None
    return max(candidates, key=key)


def resolve_latest(spm, name, entry, params):
    """Return the version ``state=latest`` should install."""
    source = params['source']
    if source is not None:
        manifest = spm.show_manifest(source_arguments(source, None))
        version = (manifest.get('package') or {}).get('version')
        if not version:
            raise PackageManagerError('the manifest of %s does not contain a package version' % source)
        return str(version)
    if entry is None:
        raise PackageManagerError('no repository named %s is registered; add one with '
                                  'community.sonic.package_repository or set source' % name)
    if entry.get('default_reference'):
        return entry['default_reference']
    out = spm.run(['show', 'package', 'versions', name, '--plain'],
                  'sonic-package-manager show package versions %s' % name, record=False)
    version = highest_version(out.splitlines())
    if version is None:
        raise PackageManagerError('cannot determine the latest version of %s: the repository has no default '
                                  'reference and the registry offers no SemVer tags; set version or '
                                  'default_reference' % name)
    return version


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        version=dict(type='str'),
        source=dict(type='str'),
        state=dict(type='str', default='present', choices=['present', 'absent', 'latest']),
        enabled=dict(type='bool'),
        owner=dict(type='str', choices=['local', 'kube']),
        allow_downgrade=dict(type='bool', default=False),
        skip_host_plugins=dict(type='bool', default=False),
        keep_config=dict(type='bool', default=False),
        force=dict(type='bool', default=False),
        custom_name=dict(type='str'),
        manifest=dict(type='bool'),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    params = module.params
    name = params['name']
    state = params['state']
    if params['manifest'] and params['custom_name'] is None:
        module.fail_json(msg='manifest=true requires custom_name')
    spm = PackageManager(module)

    try:
        entry = spm.read_database().get(name)
        before = state_view(entry)
        after = dict(before)
        installed = entry is not None and entry['installed']

        if state == 'absent':
            if installed:
                if entry['built_in']:
                    module.fail_json(msg='package %s is built-in and cannot be uninstalled' % name)
                after = dict(installed=False, version=None, repository=entry['repository'])
                if not module.check_mode:
                    spm.run_privileged(uninstall_arguments(params), 'sonic-package-manager uninstall %s' % name)
        else:
            if state == 'latest':
                target = resolve_latest(spm, name, entry, params)
            else:
                target = params['version']
            if not installed:
                if params['source'] is None and entry is None:
                    module.fail_json(msg='no repository named %s is registered; add one with '
                                         'community.sonic.package_repository or set source' % name)
                if params['source'] is None and target is None:
                    if not entry.get('default_reference'):
                        module.fail_json(msg='repository %s has no default reference; set version' % name)
                    target = entry['default_reference']
                after = dict(installed=True, version=target, repository=before['repository'])
            elif target is not None and normalize_version(target) != normalize_version(entry['version']):
                if entry['built_in']:
                    module.fail_json(msg='package %s is built-in and cannot be upgraded' % name)
                after = dict(installed=True, version=target, repository=before['repository'])
            if after != before and not module.check_mode:
                spm.run_privileged(install_arguments(params, target, upgrade=installed),
                                   'sonic-package-manager install %s' % name)

        changed = after != before
        if changed and not module.check_mode:
            entry = spm.read_database().get(name)
            after = state_view(entry)
    except PackageManagerError as e:
        msg = str(e)
        if 'Disable the feature first' in msg:
            msg += ' (disable the feature or set force=true)'
        module.fail_json(msg=msg, commands=spm.commands, **e.details)

    if changed and module.check_mode:
        status = package_status(dict(installed=after['installed']))
    else:
        status = entry['status'] if entry is not None else STATUS_NOT_INSTALLED

    module.exit_json(
        changed=changed,
        name=name,
        installed=after['installed'],
        version=after['version'],
        repository=after['repository'],
        status=status,
        commands=spm.commands,
        diff=dict(before=before, after=after),
    )


def main():
    run_module()


if __name__ == '__main__':
    main()
