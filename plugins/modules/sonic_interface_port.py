#!/usr/bin/python
# TODO: describe
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


# NOTE: The FEC choices supported by SONiC is listed in
# sonic-swss/orchagent/port/portschema.h as PORT_FEC_* macros.

DOCUMENTATION = r'''
---
module: sonic_interface_port
short_description: Configure a SONiC interface port
version_added: "0.0.1"
description: Manage all settings related to interface ports in SONiC
options:
    interface:
        description: The interface name to operate on. Alias naming is supported.
        required: true
        type: str
    description:
        description: Update the interface description to this string
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
        description: Admin status for the interface
        required: false
        type: bool

author:
    - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
# Set the interface description of a port
- name: Set port description
  community.sonic.sonic_interface_port:
    interface: qsfp1
    description: This is the uplink

# Set the interface description, speed, and state of a port
- name: Set port description
  community.sonic.sonic_interface_port:
    interface: qsfp1
    description: This is the uplink
    speed: 1G
    enabled: True
'''

RETURN = r'''
interface:
    description: The resolved interface name
    type: str
    returned: always
'''

import copy
import re
import traceback

from ansible.module_utils.basic import AnsibleModule, missing_required_lib

try:
    from swsscommon import swsscommon
except ImportError:
    HAS_SWSSCOMMON_LIBRARY = False
    SWSSCOMMON_IMPORT_ERROR = traceback.format_exc()
else:
    HAS_SWSSCOMMON_LIBRARY = True
    SWSSCOMMON_IMPORT_ERROR = None


class ModuleError(Exception):
    pass


class NoSuchInterfaceError(ModuleError):
    pass


class InvalidSpeedError(ModuleError):
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
                 fec=None):
    changed = False
    port_alias_table = {v['alias']: k for k, v in port_table.items() if 'alias' in v}
    ifname = port_alias_table.get(interface, interface)
    if ifname not in port_table:
        raise NoSuchInterfaceError(f'could not find interface "{ifname}"')

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
        if enabled:
            new_state['admin_status'] = 'up'
        else:
            del new_state['admin_status']
        changed = changed or (
            new_state.get('admin_status') != current_state.get('admin_status'))

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
    port_speed_gbit = int(new_state.get('speed') or current_state.get('speed')) // 1000
    if port_speed_gbit != 25 and port_speed_gbit < 100:
        if fec is None and 'fec' in current_state:
            fec = 'none'

    if fec is not None:
        new_state['fec'] = fec
        changed = changed or (
            new_state.get('fec') != current_state.get('fec'))

    return (current_state, new_state, ifname, changed)


def run_module():
    module_args = dict(
        interface=dict(type='str', required=True),
        description=dict(type='str', required=False),
        enabled=dict(type='bool', required=False),
        speed=dict(type='str', required=False),
        fec=dict(type='str', required=False),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if not HAS_SWSSCOMMON_LIBRARY:
        module.fail_json(
            msg=missing_required_lib('swsscommon'),
            exception=SWSSCOMMON_IMPORT_ERROR)

    config_db = swsscommon.ConfigDBConnector()
    config_db.connect()
    port_table = config_db.get_table('PORT')

    try:
        old_state, new_state, ifname, changed = mutate_state(port_table, **module.params)
    except ModuleError as e:
        module.fail_json(msg=str(e))

    if module.check_mode:
        module.exit_json(changed=changed, interface=ifname)

    if not changed:
        module.exit_json(changed=changed, interface=ifname)

    if 'description' in old_state and 'description' not in new_state:
        # Specifically for description, if it has been removed we need to clean
        # it up from APPL_DB / PORT_TABLE since that is not done automatically
        # as of this writing (2023-04-15).
        # The cleanest way to do this is to set the description to '' before
        # deleting it, which triggers the APPL_DB to refresh.
        config_db.mod_entry('PORT', ifname, {'description': ''})

    config_db.set_entry('PORT', ifname, new_state)

    module.exit_json(changed=changed, interface=ifname)


def main():
    run_module()


if __name__ == '__main__':
    main()
