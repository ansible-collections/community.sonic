#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: sonic_facts
short_description: Gather facts about a SONiC device
version_added: "0.4.0"
description:
  - Collect SONiC specific facts (platform, HWSKU, ASIC type, software version,
    management VRF state, feature states) and optionally the complete running
    or saved configuration database, and return them under
    RV(ansible_facts.sonic).
  - The module reads the C(DEVICE_METADATA), C(MGMT_VRF_CONFIG) and C(FEATURE)
    tables of the configuration database together with
    C(/etc/sonic/sonic_version.yml) and C(/etc/sonic/sonic-environment).
    It never writes anything and always reports C(changed=false).
  - Facts whose source cannot be read are left empty and reported as a
    warning instead of failing the task, so a play can still use the facts
    that are available.
  - This module is intended as the lightweight replacement for
    C(gather_facts) on SONiC, where the generic fact collection is slow.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
options:
  gather_subset:
    description:
      - Which facts to collect.
      - V(min) collects the basic device facts (platform, HWSKU, ASIC type,
        hostname, MAC address, version, management VRF state and feature
        states). It is cheap and is always included unless it is explicitly
        excluded with V(!min) or V(!all).
      - V(config_db) adds the complete running configuration database as
        RV(ansible_facts.sonic.config_db). This can be large.
      - V(saved_config_db) adds the parsed C(/etc/sonic/config_db.json) as
        RV(ansible_facts.sonic.saved_config_db), the configuration the switch
        boots with.
      - V(all) collects everything.
      - A subset prefixed with C(!) is excluded, like with
        M(ansible.builtin.setup). When only exclusions are given the module
        starts from V(all), so V(['!saved_config_db']) collects the basic facts
        and the running configuration database.
    type: list
    elements: str
    default: [min]
    choices: [all, min, config_db, saved_config_db, '!all', '!min', '!config_db', '!saved_config_db']
notes:
  - The saved configuration C(/etc/sonic/config_db.json) is normally world
    readable on SONiC. If the connecting user cannot read it, the
    C(saved_config_db) fact is omitted and a warning is reported.
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Gather the basic SONiC facts
  community.sonic.sonic_facts:

- name: Show what we are running on
  ansible.builtin.debug:
    msg: "{{ ansible_facts.sonic.hwsku }} on {{ ansible_facts.sonic.platform }} running {{ ansible_facts.sonic.version }}"

- name: Gather the basic facts and the running configuration database
  community.sonic.sonic_facts:
    gather_subset:
      - min
      - config_db

- name: Only configure breakout ports on platforms that have them
  community.sonic.interface_port:
    interface: Ethernet4
    speed: 25G
  when: "'Ethernet4' in ansible_facts.sonic.config_db.PORT"

- name: Gather everything, including the saved configuration
  community.sonic.sonic_facts:
    gather_subset:
      - all

- name: Everything except the running configuration database
  community.sonic.sonic_facts:
    gather_subset:
      - '!config_db'

- name: Warn about unsaved configuration changes
  ansible.builtin.debug:
    msg: The running PORT table differs from the saved configuration
  when:
    - ansible_facts.sonic.saved_config_db is defined
    - ansible_facts.sonic.config_db.PORT != ansible_facts.sonic.saved_config_db.PORT
'''

RETURN = r'''
ansible_facts:
  description: Facts to add to C(ansible_facts).
  returned: always
  type: dict
  contains:
    sonic:
      description: The SONiC facts.
      returned: always
      type: dict
      contains:
        platform:
          description: The platform identifier, from C(DEVICE_METADATA) or C(/etc/sonic/sonic-environment).
          returned: when the V(min) subset is gathered
          type: str
          sample: x86_64-kvm_x86_64-r0
        hwsku:
          description: The hardware SKU, from C(DEVICE_METADATA) or C(/etc/sonic/sonic-environment).
          returned: when the V(min) subset is gathered
          type: str
          sample: Force10-S6000
        asic_type:
          description: The ASIC type, from C(/etc/sonic/sonic-environment) or C(/etc/sonic/sonic_version.yml).
          returned: when the V(min) subset is gathered
          type: str
          sample: broadcom
        device_type:
          description: The device role, from C(DEVICE_METADATA) or C(/etc/sonic/sonic-environment).
          returned: when the V(min) subset is gathered
          type: str
          sample: LeafRouter
        hostname:
          description: The hostname configured in C(DEVICE_METADATA).
          returned: when the V(min) subset is gathered
          type: str
          sample: sonic
        mac:
          description: The system MAC address configured in C(DEVICE_METADATA).
          returned: when the V(min) subset is gathered
          type: str
          sample: 52:54:00:12:34:56
        version:
          description:
            - The SONiC build version (C(build_version) in C(/etc/sonic/sonic_version.yml)).
            - This is the raw value from the file; C(show version) prints it with a C(SONiC.) prefix.
          returned: when the V(min) subset is gathered
          type: str
          sample: 202311.0-20240101.42
        kernel:
          description: The kernel version (C(kernel_version) in C(/etc/sonic/sonic_version.yml)).
          returned: when the V(min) subset is gathered
          type: str
          sample: 6.1.0-11-2-amd64
        debian:
          description: The Debian base version (C(debian_version) in C(/etc/sonic/sonic_version.yml)).
          returned: when the V(min) subset is gathered
          type: str
          sample: '12.1'
        build:
          description: Details about the SONiC build, from C(/etc/sonic/sonic_version.yml).
          returned: when the V(min) subset is gathered
          type: dict
          contains:
            branch:
              description: The source branch the image was built from.
              type: str
              sample: '202311'
            release:
              description: The release the image belongs to.
              type: str
              sample: '202311'
            commit_id:
              description: The sonic-buildimage commit the image was built from.
              type: str
              sample: d83e8e8ed
            date:
              description: When the image was built.
              type: str
              sample: Mon Jan 01 12:00:00 UTC 2024
            number:
              description: The build number.
              type: str
              sample: '42'
            built_by:
              description: Who built the image.
              type: str
              sample: user@buildhost
        version_info:
          description: All fields of C(/etc/sonic/sonic_version.yml), as strings.
          returned: when the V(min) subset is gathered
          type: dict
          sample: {'build_version': '202311.0-20240101.42', 'debian_version': '12.1', 'asic_type': 'vs'}
        mgmt_vrf_enabled:
          description: Whether the management VRF is enabled (C(MGMT_VRF_CONFIG|vrf_global)).
          returned: when the V(min) subset is gathered
          type: bool
          sample: false
        features:
          description: The state of every entry of the C(FEATURE) table.
          returned: when the V(min) subset is gathered
          type: dict
          sample: {'bgp': 'enabled', 'lldp': 'enabled', 'sflow': 'disabled', 'database': 'always_enabled'}
        config_db:
          description: The complete running configuration database, one key per table holding C(key -> entry) dictionaries. Compound keys are joined with C(|).
          returned: when the V(config_db) subset is gathered
          type: dict
          sample: {'PORT': {'Ethernet0': {'alias': 'etp1', 'speed': '25000'}}, 'VLAN_MEMBER': {'Vlan100|Ethernet0': {'tagging_mode': 'untagged'}}}
        saved_config_db:
          description: The parsed C(/etc/sonic/config_db.json), the configuration the switch boots with.
          returned: when the V(saved_config_db) subset is gathered and the file is readable
          type: dict
          sample: {'PORT': {'Ethernet0': {'alias': 'etp1', 'speed': '25000'}}}
'''

import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native, to_text
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    str_to_bool,
)


SONIC_VERSION_FILE = '/etc/sonic/sonic_version.yml'
SONIC_ENVIRONMENT_FILE = '/etc/sonic/sonic-environment'
SAVED_CONFIG_DB_FILE = '/etc/sonic/config_db.json'

#: The subsets that can be gathered; ``all`` expands to these.
SUBSETS = ('min', 'config_db', 'saved_config_db')

#: ``build`` fact field -> key in ``sonic_version.yml``.
BUILD_FIELDS = (
    ('branch', 'branch'),
    ('release', 'release'),
    ('commit_id', 'commit_id'),
    ('date', 'build_date'),
    ('number', 'build_number'),
    ('built_by', 'built_by'),
)


def resolve_subsets(requested):
    """Expand a ``gather_subset`` list into the set of subsets to gather.

    Mirrors ``ansible.builtin.setup``: ``all`` expands to every subset, a
    ``!`` prefix excludes a subset (``!all`` excludes everything) and ``min``
    is included unless it is explicitly excluded. When only exclusions are
    given the starting point is ``all``.

    Raises :class:`ValueError` for an unknown subset name.
    """
    include = set()
    exclude = set()
    for item in requested or []:
        name = str(item).strip()
        negate = name.startswith('!')
        if negate:
            name = name[1:].strip()
        if name == 'all':
            # ``!all`` keeps ``min``, which has to be excluded explicitly with ``!min``.
            names = set(SUBSETS) - set(['min']) if negate else set(SUBSETS)
        elif name in SUBSETS:
            names = set([name])
        else:
            raise ValueError('unknown gather_subset "%s"; expected one of all, %s (optionally prefixed with !)'
                             % (item, ', '.join(SUBSETS)))
        (exclude if negate else include).update(names)

    if not include:
        include = set(SUBSETS) if exclude else set(['min'])
    include.add('min')
    return include - exclude


def parse_flat_yaml(text):
    """Parse a flat ``key: value`` YAML file such as ``sonic_version.yml`` into ``{key: str}``.

    The file is written by the build system with one scalar per line, so a
    YAML parser is not needed on the target. Comments and blank lines are
    skipped, surrounding single or double quotes are removed and values are
    always strings (``build_number: 0`` becomes ``'0'``).
    """
    result = {}
    for line in to_text(text, errors='surrogate_or_strict').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped == '---':
            continue
        if ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key] = value
    return result


def parse_environment(text):
    """Parse a shell style ``KEY=value`` file such as ``/etc/sonic/sonic-environment`` into ``{KEY: str}``.

    Comments and blank lines are skipped, an optional ``export`` prefix and
    surrounding quotes are removed.
    """
    result = {}
    for line in to_text(text, errors='surrogate_or_strict').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        if stripped.startswith('export '):
            stripped = stripped[len('export '):].strip()
        key, value = stripped.split('=', 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key] = value
    return result


def read_text_file(path):
    """Return the contents of ``path`` as text. Raises ``OSError`` (``IOError``) when it cannot be read."""
    with open(path, 'rb') as f:
        return to_text(f.read(), errors='surrogate_or_strict')


def build_min_facts(device_metadata, mgmt_vrf, feature_table, version_info, environment):
    """Build the ``min`` facts from the CONFIG_DB entries and the parsed files.

    ``device_metadata`` is the ``DEVICE_METADATA|localhost`` entry, ``mgmt_vrf``
    the ``MGMT_VRF_CONFIG|vrf_global`` entry, ``feature_table`` the ``FEATURE``
    table, ``version_info`` the parsed ``sonic_version.yml`` and ``environment``
    the parsed ``sonic-environment``; each may be ``{}`` when unavailable.
    """
    device_metadata = device_metadata or {}
    mgmt_vrf = mgmt_vrf or {}
    feature_table = feature_table or {}
    version_info = version_info or {}
    environment = environment or {}

    def first(*values):
        for value in values:
            if value not in (None, ''):
                return value
        return None

    build = dict((fact, version_info.get(key)) for fact, key in BUILD_FIELDS)
    features = dict((name, entry.get('state') if isinstance(entry, dict) else None)
                    for name, entry in feature_table.items())
    return {
        'platform': first(device_metadata.get('platform'), environment.get('PLATFORM')),
        'hwsku': first(device_metadata.get('hwsku'), environment.get('HWSKU')),
        'asic_type': first(environment.get('ASIC_TYPE'), version_info.get('asic_type'), device_metadata.get('asic_type')),
        'device_type': first(device_metadata.get('type'), environment.get('DEVICE_TYPE')),
        'hostname': device_metadata.get('hostname'),
        'mac': device_metadata.get('mac'),
        'version': version_info.get('build_version'),
        'kernel': version_info.get('kernel_version'),
        'debian': version_info.get('debian_version'),
        'build': build,
        'version_info': version_info,
        'mgmt_vrf_enabled': str_to_bool(mgmt_vrf.get('mgmtVrfEnabled'), default=False),
        'features': features,
    }


def run_module():
    module_args = dict(
        gather_subset=dict(
            type='list', elements='str', default=['min'],
            choices=['all', 'min', 'config_db', 'saved_config_db', '!all', '!min', '!config_db', '!saved_config_db'],
        ),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    try:
        subsets = resolve_subsets(module.params['gather_subset'])
    except ValueError as e:
        module.fail_json(msg=to_native(e))

    facts = {}
    db = ConfigDB(module).connect()
    try:
        if 'min' in subsets:
            version_info = {}
            environment = {}
            try:
                version_info = parse_flat_yaml(read_text_file(SONIC_VERSION_FILE))
            except (IOError, OSError) as e:
                module.warn('could not read %s: %s' % (SONIC_VERSION_FILE, to_native(e)))
            try:
                environment = parse_environment(read_text_file(SONIC_ENVIRONMENT_FILE))
            except (IOError, OSError) as e:
                module.warn('could not read %s: %s' % (SONIC_ENVIRONMENT_FILE, to_native(e)))
            facts.update(build_min_facts(
                db.get_entry('DEVICE_METADATA', 'localhost'),
                db.get_entry('MGMT_VRF_CONFIG', 'vrf_global'),
                db.get_table('FEATURE'),
                version_info,
                environment))

        if 'config_db' in subsets:
            facts['config_db'] = db.get_config()

        if 'saved_config_db' in subsets:
            try:
                saved = json.loads(read_text_file(SAVED_CONFIG_DB_FILE))
                if not isinstance(saved, dict):
                    raise ValueError('expected a JSON object with one key per table')
                facts['saved_config_db'] = saved
            except (IOError, OSError) as e:
                module.warn('could not read %s: %s; the saved_config_db fact is not available'
                            % (SAVED_CONFIG_DB_FILE, to_native(e)))
            except ValueError as e:
                module.warn('could not parse %s as JSON: %s; the saved_config_db fact is not available'
                            % (SAVED_CONFIG_DB_FILE, to_native(e)))
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(changed=False, ansible_facts={'sonic': facts})


def main():
    run_module()


if __name__ == '__main__':
    main()
