#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


# NOTE: The FEC choices supported by SONiC is listed in
# sonic-swss/orchagent/port/portschema.h as PORT_FEC_* macros.

DOCUMENTATION = r'''
---
module: interface_port
short_description: Configure a SONiC interface port
version_added: "0.0.1"
description: Manage all settings related to interface ports in SONiC
extends_documentation_fragment:
  - community.sonic.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
    interface:
        description: The interface name to operate on. Alias naming is supported.
        required: true
        type: str
    description:
        description:
            - Update the interface description to this string.
            - Omitting this option or passing an empty string removes the description.
        required: false
        type: str
    speed:
        description: Human readable format for the interface speed
        required: false
        type: str
    fec:
        description: The FEC mode to use.
        choices:
            - none
            - rs
            - fc
            - auto
        required: false
        type: str
    enabled:
        description:
            - Admin status for the interface.
            - V(true) sets C(admin_status=up) and V(false) sets C(admin_status=down).
            - A port without an admin status in CONFIG_DB is treated as down.
            - Omitting this option leaves the admin status untouched.
        required: false
        type: bool
    laser_frequency:
        description:
            - Laser frequency in GHz for tunable or coherent optics such as 400ZR/ZR+ modules,
              for example V(194900). Stored in the C(laser_freq) field of the C(PORT) table
              and applied to the module by C(xcvrd).
            - Only meaningful for tunable modules. The value is written as-is and not
              validated against the inserted optic; the platform reports an unsupported
              frequency.
            - V(0) removes the field from CONFIG_DB. C(xcvrd) treats a missing or zero
              frequency as "not configured".
            - Omitting this option leaves the field untouched.
        required: false
        type: int
        version_added: 0.4.0
    tx_power:
        description:
            - Transmit output power in dBm for coherent optics, for example V(-10). Stored in
              the C(tx_power) field of the C(PORT) table and applied to the module by C(xcvrd).
            - Only meaningful for modules with a configurable output power. The value is
              written as-is and not validated against the inserted optic.
            - V(0) removes the field from CONFIG_DB. C(xcvrd) treats a missing or zero
              TX power as "not configured".
            - Omitting this option leaves the field untouched.
        required: false
        type: float
        version_added: 0.4.0
    dom_polling:
        description:
            - Whether C(xcvrd) polls the Digital Optical Monitoring (DOM) data of the
              transceiver. Stored in the C(dom_polling) field of the C(PORT) table.
            - V(default) removes the field from CONFIG_DB so SONiC applies its platform
              default, which is polling enabled.
            - Omitting this option leaves the field untouched.
        choices:
            - enabled
            - disabled
            - default
        required: false
        type: str
        version_added: 0.4.0

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
# Set the interface description of a port
- name: Set port description
  community.sonic.interface_port:
    interface: qsfp1
    description: This is the uplink

# Set the interface description, speed, and state of a port
- name: Set port description
  community.sonic.interface_port:
    interface: qsfp1
    description: This is the uplink
    speed: 1G
    enabled: True

# Tune the coherent optic on a long-haul link
- name: Set laser frequency and TX power on a 400ZR port
  community.sonic.interface_port:
    interface: qsfp1
    description: "Link: remote-site (400ZR)"
    speed: 400G
    fec: rs
    laser_frequency: 194900
    tx_power: -10
    dom_polling: enabled
    enabled: true

# Clear the transceiver settings again
- name: Remove laser frequency, TX power and DOM polling settings
  community.sonic.interface_port:
    interface: qsfp1
    laser_frequency: 0
    tx_power: 0
    dom_polling: default
'''

RETURN = r'''
interface:
    description: The resolved interface name
    type: str
    returned: always
'''

import copy
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    UnknownInterfaceError,
    build_result,
    resolve_port_name,
)


class ModuleError(Exception):
    pass


class NoSuchInterfaceError(ModuleError, UnknownInterfaceError):
    pass


class InvalidSpeedError(ModuleError):
    pass


class InvalidValueError(ModuleError):
    pass


# TODO: Figure out how to move this to a utils class
SIZE_RANGES = {
    'Y': 10 ** 24,
    'Z': 10 ** 21,
    'E': 10 ** 18,
    'P': 10 ** 15,
    'T': 10 ** 12,
    'G': 10 ** 9,
    'M': 10 ** 6,
    'K': 10 ** 3,
    'B': 1,
}


# Fork of human_to_bytes that uses decade instead of 2-power
def human_to_bits(number):
    """Convert number in string format into bytes (ex: '2K' => 2000) or using unit argument."""
    m = re.search(r'^\s*(\d*\.?\d*)\s*([A-Za-z]+)?', str(number), flags=re.IGNORECASE)
    if m is None:
        raise ValueError("human_to_bits() can't interpret following string: %s" % str(number))
    try:
        num = float(m.group(1))
    except Exception:
        raise ValueError("human_to_bits() can't interpret following number: %s (original input string: %s)" % (m.group(1), number))

    unit = m.group(2)
    if unit is None:
        unit = 'B'

    if unit is None:
        # No unit given, returning raw number
        return int(round(num))
    range_key = unit[0].upper()
    try:
        limit = SIZE_RANGES[range_key]
    except Exception:
        raise ValueError("human_to_bits() failed to convert %s (unit = %s). The suffix must be one of %s" % (number, unit, ", ".join(SIZE_RANGES.keys())))

    unit_class = 'b'
    unit_class_name = 'bit'
    # check unit value if more than one character (KB, MB)
    if len(unit) > 1:
        expect_message = 'expect %s%s or %s' % (range_key, unit_class, range_key)
        if range_key == 'B':
            expect_message = 'expect %s or %s' % (unit_class, unit_class_name)

        if unit_class_name in unit.lower():
            pass
        elif unit[1] != unit_class:
            raise ValueError("human_to_bits() failed to convert %s. Value is not a valid string (%s)" % (number, expect_message))

    return int(round(num * limit))


def mutate_state(port_table,
                 interface,
                 description=None,
                 enabled=None,
                 speed=None,
                 fec=None,
                 laser_frequency=None,
                 tx_power=None,
                 dom_polling=None):
    changed = False
    try:
        ifname = resolve_port_name(port_table, interface)
    except UnknownInterfaceError:
        raise NoSuchInterfaceError(f'could not find interface "{interface}"')

    current_state = port_table[ifname]
    new_state = copy.copy(current_state)

    if 'description' in current_state:
        if description == '' or description is None:
            del new_state['description']
            changed = True
    if description and (description != current_state.get('description', '')):
        new_state['description'] = description
        changed = True

    if enabled is not None:
        wanted_admin_status = 'up' if enabled else 'down'
        # A port without admin_status in CONFIG_DB is treated as down by
        # SONiC (portmgrd default), so only write the field when it differs.
        if current_state.get('admin_status', 'down') != wanted_admin_status:
            new_state['admin_status'] = wanted_admin_status
            changed = True

    if speed is not None:
        try:
            b = int(human_to_bits(speed))
        except ValueError:
            raise InvalidSpeedError(f'could not parse speed "{speed}"')
        new_state['speed'] = str(b // 1000 // 1000)
        changed = changed or (
            new_state.get('speed') != current_state.get('speed'))

    # If the interface is configured for a speed that does not utilize FEC
    # (e.g. 40G, or 10G) we remove the old FEC mode if a new one is not
    # specified. This is done in order to not force the user to clean up
    # the old FEC that may have been set from when the interface possibly
    # operated on a higher speed.
    # As it is not currently possible to remove the FEC entry in a nice way,
    # we force it to 'none' instead.
    port_speed = new_state.get('speed')
    port_speed_gbit = int(port_speed) // 1000 if port_speed else None
    if port_speed_gbit is not None and port_speed_gbit != 25 and port_speed_gbit < 100:
        if fec is None and 'fec' in current_state:
            fec = 'none'

    if fec is not None:
        new_state['fec'] = fec
        changed = changed or (
            new_state.get('fec') != current_state.get('fec'))

    # Transceiver settings. xcvrd reads these fields from CONFIG_DB and
    # programs the module; a missing or zero laser_freq/tx_power means "not
    # configured" to xcvrd, so 0 is used to remove the field.
    if laser_frequency is not None:
        if laser_frequency < 0:
            raise InvalidValueError(
                f'invalid laser_frequency "{laser_frequency}": expected a frequency in GHz, or 0 to clear')
        if laser_frequency == 0:
            new_state.pop('laser_freq', None)
        else:
            new_state['laser_freq'] = str(laser_frequency)
        changed = changed or (
            new_state.get('laser_freq') != current_state.get('laser_freq'))

    if tx_power is not None:
        if tx_power == 0:
            new_state.pop('tx_power', None)
        elif not _same_float(current_state.get('tx_power'), tx_power):
            # Store the value the way "config interface transceiver tx_power"
            # does (str(float)), keeping an existing numerically equal value.
            new_state['tx_power'] = str(float(tx_power))
        changed = changed or (
            new_state.get('tx_power') != current_state.get('tx_power'))

    if dom_polling is not None:
        if dom_polling == 'default':
            new_state.pop('dom_polling', None)
        else:
            new_state['dom_polling'] = dom_polling
        changed = changed or (
            new_state.get('dom_polling') != current_state.get('dom_polling'))

    return (current_state, new_state, ifname, changed)


def _same_float(current, wanted):
    """True if the CONFIG_DB string ``current`` holds the same number as ``wanted``."""
    if current is None:
        return False
    try:
        return float(current) == float(wanted)
    except (TypeError, ValueError):
        return False


def run_module():
    module_args = dict(
        interface=dict(type='str', required=True),
        description=dict(type='str', required=False),
        enabled=dict(type='bool', required=False),
        speed=dict(type='str', required=False),
        fec=dict(type='str', required=False, choices=['none', 'rs', 'fc', 'auto']),
        laser_frequency=dict(type='int', required=False),
        tx_power=dict(type='float', required=False),
        dom_polling=dict(type='str', required=False, choices=['enabled', 'disabled', 'default']),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    config_db = ConfigDB(module).connect()
    port_table = config_db.get_table('PORT')

    try:
        old_state, new_state, ifname, changed = mutate_state(port_table, **module.params)
    except ModuleError as e:
        module.fail_json(msg=str(e))

    # ConfigDB skips writes in check mode, so only the "changed" guard is needed here.
    if changed:
        if 'description' in old_state and 'description' not in new_state:
            # Specifically for description, if it has been removed we need to clean
            # it up from APPL_DB / PORT_TABLE since that is not done automatically
            # as of this writing (2023-04-15).
            # The cleanest way to do this is to set the description to '' before
            # deleting it, which triggers the APPL_DB to refresh.
            config_db.mod_entry('PORT', ifname, {'description': ''})

        config_db.set_entry('PORT', ifname, new_state)

    module.exit_json(**build_result(changed, old_state, new_state, interface=ifname))


def main():
    run_module()


if __name__ == '__main__':
    main()
