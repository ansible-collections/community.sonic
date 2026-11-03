#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: device_metadata
short_description: Configure SONiC device metadata (hostname, timezone, system MAC, ...)
version_added: "0.4.0"
description:
  - Manage the switch-level identity fields stored in the C(DEVICE_METADATA|localhost)
    entry of the SONiC configuration database.
  - Only the options that are given are written; every other field of the entry is
    left untouched, so values set at install time (such as C(hwsku) and C(platform))
    are preserved.
  - The hostname and timezone are applied asynchronously by C(hostcfgd), which
    updates C(/etc/hostname), C(/etc/hosts) and the system timezone shortly after
    the configuration database changes.
  - Changes are made to the running configuration database only. Persist them with
    C(config save) if they must survive a reboot.
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  hostname:
    description:
      - The device hostname.
      - Must be a valid hostname of at most 253 characters made of letters, digits
        and hyphens, with labels separated by dots.
    type: str
  timezone:
    description:
      - The system timezone as a zoneinfo name, for example V(UTC) or V(Europe/Stockholm).
      - The name is validated against the zoneinfo database of the device when it is available.
    type: str
  mac:
    description:
      - The system MAC address used by the switch and VLAN interfaces, in colon-separated
        form such as V(02:00:00:00:00:01).
      - The address is stored in lower case. Changing it requires a restart of the
        C(swss) service or a reboot to take effect; the module does not do that.
    type: str
  type:
    description:
      - The device role, for example V(LeafRouter), V(ToRRouter), V(SpineRouter) or
        V(BackEndToRRouter). It drives minigraph-derived default behaviour.
    type: str
  bgp_asn:
    description:
      - The local BGP autonomous system number.
    type: int
  default_bgp_status:
    description:
      - The default administrative state of new BGP sessions.
    type: str
    choices: [up, down]
  default_pfcwd_status:
    description:
      - Whether PFC watchdog is enabled on ports by default.
    type: str
    choices: [enable, disable]
  buffer_model:
    description:
      - The buffer model used by the buffer manager.
    type: str
    choices: [traditional, dynamic]
  synchronous_mode:
    description:
      - Whether C(orchagent) runs in synchronous mode.
    type: str
    choices: [enable, disable]
  hwsku:
    description:
      - The expected hardware SKU of the device.
      - The module does not change the hardware SKU. When this option is given the
        module fails if it differs from the configured SKU, which lets a play assert
        the SKU before configuring a device. See
        U(https://github.com/ansible-collections/community.sonic/issues/30) for the
        separate work on changing the SKU.
    type: str
  platform:
    description:
      - The expected platform identifier of the device.
      - The module does not change the platform. When this option is given the module
        fails if it differs from the configured platform. See
        U(https://github.com/ansible-collections/community.sonic/issues/30).
    type: str
notes:
  - At least one option must be given.
  - Fields cannot be removed from C(DEVICE_METADATA|localhost) with this module; it only
    sets the fields it is given.

author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Switch identity
  community.sonic.device_metadata:
    hostname: "{{ inventory_hostname_short }}"
    timezone: UTC

- name: Set the system MAC and BGP ASN
  community.sonic.device_metadata:
    mac: "02:00:00:00:00:01"
    bgp_asn: 65100
    default_bgp_status: up

- name: Make sure the switch is the expected SKU before configuring it
  community.sonic.device_metadata:
    hwsku: Accton-AS7726-32X
    hostname: leaf1
'''

RETURN = r'''
entry:
  description:
    - The C(DEVICE_METADATA|localhost) entry after the change (the predicted entry in check mode).
  type: dict
  returned: always
  sample:
    hostname: leaf1
    hwsku: Accton-AS7726-32X
    platform: x86_64-accton_as7726_32x-r0
    mac: "02:00:00:00:00:01"
    timezone: UTC
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import ConfigDB, ConfigDBError

try:
    import zoneinfo
except ImportError:  # Python < 3.9
    zoneinfo = None


TABLE = 'DEVICE_METADATA'
KEY = 'localhost'

#: Fields the module manages; option names are identical to the CONFIG_DB field names.
MANAGED_FIELDS = (
    'hostname',
    'timezone',
    'mac',
    'type',
    'bgp_asn',
    'default_bgp_status',
    'default_pfcwd_status',
    'buffer_model',
    'synchronous_mode',
)

#: Fields the module refuses to change; see https://github.com/ansible-collections/community.sonic/issues/30.
PROTECTED_FIELDS = ('hwsku', 'platform')

HWSKU_ISSUE_URL = 'https://github.com/ansible-collections/community.sonic/issues/30'

# Same shape as the stypes:hostname typedef in SONiC's YANG models.
_HOSTNAME_LABEL_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')
_MAC_RE = re.compile(r'^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$')
_TIMEZONE_RE = re.compile(r'^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$')


class ValidationError(ConfigDBError):
    """Raised for an option value SONiC would not accept."""


def validate_hostname(hostname):
    """Return ``hostname`` if it is a valid hostname, otherwise raise :class:`ValidationError`."""
    if not hostname or len(hostname) > 253:
        raise ValidationError('hostname "%s" must be between 1 and 253 characters long' % hostname)
    for label in hostname.split('.'):
        if not _HOSTNAME_LABEL_RE.match(label):
            raise ValidationError(
                'hostname "%s" is not valid: labels may only contain letters, digits and hyphens, '
                'must not start or end with a hyphen and must be at most 63 characters long' % hostname)
    return hostname


def validate_mac(mac):
    """Return ``mac`` normalised to lower case, or raise :class:`ValidationError` if it is malformed."""
    if not _MAC_RE.match(mac or ''):
        raise ValidationError('mac "%s" is not a valid MAC address; expected the form 02:00:00:00:00:01' % mac)
    return mac.lower()


def validate_bgp_asn(bgp_asn):
    """Return ``bgp_asn`` if it is a valid 32-bit ASN, otherwise raise :class:`ValidationError`."""
    if bgp_asn < 1 or bgp_asn > 4294967295:
        raise ValidationError('bgp_asn %s is out of range; expected 1-4294967295' % bgp_asn)
    return bgp_asn


def validate_timezone(timezone, available=None):
    """Return ``timezone`` if it is a known zoneinfo name, otherwise raise :class:`ValidationError`.

    ``available`` is the set of known zone names; by default it is taken from
    the ``zoneinfo`` module of the target interpreter. When no zone database is
    available (old Python or no ``tzdata``), only the shape of the name is checked.
    """
    if not _TIMEZONE_RE.match(timezone or ''):
        raise ValidationError('timezone "%s" is not a valid zoneinfo name; expected a name such as '
                              'UTC or Europe/Stockholm' % timezone)
    if available is None and zoneinfo is not None:
        try:
            available = zoneinfo.available_timezones()
        except Exception:  # pylint: disable=broad-except
            available = None
    if available and timezone not in available:
        raise ValidationError('timezone "%s" is not a known zoneinfo name on this device' % timezone)
    return timezone


def build_device_metadata_entry(params):
    """Build the ``DEVICE_METADATA|localhost`` fields to merge from the module parameters.

    Only the managed options that were given are included, validated and
    normalised to the form CONFIG_DB stores. Raises :class:`ValidationError`.
    """
    desired = {}
    for field in MANAGED_FIELDS:
        value = params.get(field)
        if value is None:
            continue
        if field == 'hostname':
            value = validate_hostname(value)
        elif field == 'mac':
            value = validate_mac(value)
        elif field == 'bgp_asn':
            value = validate_bgp_asn(value)
        elif field == 'timezone':
            value = validate_timezone(value)
        desired[field] = value
    return desired


def check_protected_fields(params, current):
    """Fail if a protected field (``hwsku``, ``platform``) is requested with a value other than the current one."""
    for field in PROTECTED_FIELDS:
        wanted = params.get(field)
        if wanted is None:
            continue
        actual = current.get(field)
        if wanted != actual:
            raise ValidationError(
                'refusing to change %s from "%s" to "%s": changing the hardware SKU or platform requires '
                'a reboot and is not supported by this module, see %s' % (field, actual, wanted, HWSKU_ISSUE_URL))


def run_module():
    module_args = dict(
        hostname=dict(type='str'),
        timezone=dict(type='str'),
        mac=dict(type='str'),
        type=dict(type='str'),
        bgp_asn=dict(type='int'),
        default_bgp_status=dict(type='str', choices=['up', 'down']),
        default_pfcwd_status=dict(type='str', choices=['enable', 'disable']),
        buffer_model=dict(type='str', choices=['traditional', 'dynamic']),
        synchronous_mode=dict(type='str', choices=['enable', 'disable']),
        hwsku=dict(type='str'),
        platform=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_one_of=[list(MANAGED_FIELDS) + list(PROTECTED_FIELDS)],
        supports_check_mode=True,
    )

    try:
        desired = build_device_metadata_entry(module.params)
    except ValidationError as e:
        module.fail_json(msg=str(e))

    config_db = ConfigDB(module).connect()

    try:
        current = config_db.get_entry(TABLE, KEY)
        check_protected_fields(module.params, current)
        change = config_db.ensure_entry(TABLE, KEY, desired, exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    module.exit_json(**change.result(entry=change.after))


def main():
    run_module()


if __name__ == '__main__':
    main()
