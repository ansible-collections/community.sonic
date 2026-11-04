#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: acl_table
short_description: Configure SONiC ACL tables
version_added: "0.4.0"
description:
  - Manage entries of the C(ACL_TABLE) table of the SONiC configuration database,
    the declarative equivalent of C(config acl add table) and C(config acl remove table).
  - A dual-stack data-plane policy is described once and the module picks the
    table layout the ASIC supports, see O(family_mode). The rules for such a
    policy are managed with M(community.sonic.acl_rule), which looks up the
    layout in the configuration database.
  - After writing, the module waits for orchagent to report the table as
    C(Active) in C(STATE_DB) (C(ACL_TABLE_TABLE)) and fails if the ASIC
    rejected it, instead of reporting success for a table that was silently
    refused. See the notes for how an update of an existing table is checked.
  - Removing a table also removes its rules from C(ACL_RULE).
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
      - Name of the ACL table (policy). With O(family_mode=split) this is the
        IPv4 table and the IPv6 table is named RV(tables) C(<name><v6_suffix>).
    required: true
    type: str
  state:
    description: Whether the table(s) should exist.
    type: str
    choices: [present, absent]
    default: present
  type:
    description:
      - Explicit table type, written to the C(type) field as given. Common values are
        V(L3), V(L3V6), V(L3V4V6), V(L2), V(MIRROR), V(MIRRORV6), V(MIRROR_DSCP) and
        V(CTRLPLANE); the names of user-defined C(ACL_TABLE_TYPE) entries are accepted too.
      - Use this for a single table of a specific type. Leave it out for a dual-stack
        IPv4 and IPv6 policy and let O(family_mode) choose between V(L3V4V6) and V(L3) plus V(L3V6).
      - Mutually exclusive with O(family_mode).
    type: str
  family_mode:
    description:
      - How a dual-stack IPv4 and IPv6 policy is laid out when O(type) is not given.
      - V(combined) creates one V(L3V4V6) table named O(name).
      - V(split) creates O(name) as V(L3) for IPv4 and C(<name><v6_suffix>) as V(L3V6) for IPv6.
      - V(auto) (the default) keeps the layout of an existing policy; for a new policy it reads
        the C(supported_L3V4V6) capability orchagent publishes in C(STATE_DB)
        (C(ACL_STAGE_CAPABILITY_TABLE)) and, on releases that do not publish it, tries a
        V(L3V4V6) table and watches its status. If the table goes C(Inactive) or never gets a
        status within O(status_timeout), the attempt is removed and the split layout is used.
      - In check mode the probe cannot run; when nothing else decides, V(combined) is assumed.
      - Set this per host to override a platform that gets the probe wrong.
    type: str
    choices: [auto, combined, split]
  v6_suffix:
    description: Suffix appended to O(name) for the IPv6 table of a split policy.
    type: str
    default: _v6
  stage:
    description: The ACL stage, written to the C(stage) field.
    type: str
    choices: [ingress, egress]
    default: ingress
  ports:
    description:
      - Ports and PortChannels the table is bound to (the C(ports) field), by name
        (C(Ethernet0)) or alias (C(QSFP1)). Treated as a set, order does not matter.
      - An empty list unbinds the table from every port; the table then exists but applies nowhere.
      - When omitted, the existing bindings are left as they are.
    type: list
    elements: str
  description:
    description: Free text stored in the C(policy_desc) field. Left alone when omitted.
    type: str
  services:
    description:
      - Services a V(CTRLPLANE) table applies to (the C(services) field), for example
        V(SSH), V(SNMP) or V(NTP). Left alone when omitted.
    type: list
    elements: str
  status_timeout:
    description:
      - Seconds to wait for orchagent to report every written table as C(Active) in C(STATE_DB).
      - V(0) skips the check, for example on a device where C(swss) is not running;
        O(family_mode=auto) then uses the split layout when nothing else decides.
    type: int
    default: 30
notes:
  - Writes to an existing table only touch the given fields; orchagent updates
    the port bindings in place without recreating the table or its rules.
  - C(STATE_DB) keeps the status of the previous configuration until orchagent
    has processed an update, so before changing a table the module deletes its
    C(ACL_TABLE_TABLE) status entry and then only accepts the status orchagent
    writes back. Tables that are not changed keep their status and are not
    waited for. Nothing is deleted in check mode.
  - Changing O(type) or O(stage) of an existing table makes orchagent remove
    and recreate it, which briefly drops its rules.
seealso:
  - module: community.sonic.acl_rule
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Maintenance ACL (dual-stack, platform decides combined vs split)
  community.sonic.acl_table:
    name: BGP_CULL
    stage: ingress
    ports: "{{ cull_ports }}"
    description: Drop BGP during maintenance
  register: cull

- name: Show which tables were created
  ansible.builtin.debug:
    msg: "{{ cull.family_mode }}: {{ cull.tables }}"

- name: Force the split layout on a platform the probe gets wrong
  community.sonic.acl_table:
    name: BGP_CULL
    family_mode: split
    ports: [Ethernet56, PortChannel1]

- name: Uncull everything but keep the table
  community.sonic.acl_table:
    name: BGP_CULL
    ports: []

- name: An explicit single table
  community.sonic.acl_table:
    name: DATAACL
    type: L3
    ports: [QSFP1, QSFP2]
    description: Data plane ACL

- name: Control plane ACL
  community.sonic.acl_table:
    name: SSH_ONLY
    type: CTRLPLANE
    services: [SSH]

- name: Remove the policy and its rules
  community.sonic.acl_table:
    name: BGP_CULL
    state: absent
'''

RETURN = r'''
tables:
  description:
    - Names of the tables that make up the policy after the change, in the order IPv4 table, IPv6 table.
    - For O(state=absent) the tables that were (or would be) removed.
  type: list
  elements: str
  returned: always
  sample: [BGP_CULL, BGP_CULL_v6]
family_mode:
  description:
    - The resolved layout, V(combined) or V(split), of a dual-stack policy.
    - V(null) when O(type) was given.
  type: str
  returned: always
  sample: split
ports:
  description: The ports the table is bound to after the change, with aliases resolved. Only when O(ports) was given.
  type: list
  elements: str
  returned: when O(ports) is given
  sample: [Ethernet56, Ethernet72]
rules_removed:
  description: The C(ACL_RULE) keys removed together with their table.
  type: list
  elements: str
  returned: when a table is removed
  sample: ['BGP_CULL_v6|PERMIT_ALL']
diff:
  description: The managed C(ACL_TABLE) entries before and after the change, keyed by table name.
  type: dict
  returned: always
  sample: {"before": {}, "after": {"BGP_CULL": {"type": "L3V4V6", "stage": "ingress", "ports": ["Ethernet56"]}}}
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB,
    ConfigDBError,
    EntryChange,
    build_result,
    interface_kind,
    normalize_entry,
    split_key,
)
from ansible_collections.community.sonic.plugins.module_utils import acl


def resolve_ports(db, ports):
    """Resolve port names and aliases to canonical names, keeping the given order and dropping duplicates.

    Only physical ports and PortChannels can be bound to an ACL table.
    """
    if ports is None:
        return None
    resolved = []
    for port in ports:
        name = db.resolve_interface(port)
        if interface_kind(name) not in ('Ethernet', 'PortChannel'):
            raise acl.AclError('ACL tables can only be bound to Ethernet ports and PortChannels, not "%s"' % port)
        if name not in resolved:
            resolved.append(name)
    return resolved


def ordered_ports(current, desired):
    """Return ``desired`` ordered like ``current`` where the ports overlap, new ports appended.

    Ports are a set to the user; keeping the stored order avoids rewriting the
    entry when nothing but the order differs.
    """
    kept = [p for p in current if p in desired]
    return kept + [p for p in desired if p not in kept]


def normalize_table(entry):
    """Return a copy of an ``ACL_TABLE`` entry with empty list fields (read back as ``['']``) as ``[]``."""
    entry = dict(entry)
    for field in ('ports', 'services'):
        if field in entry:
            entry[field] = acl.list_field(entry, field)
    return entry


def build_table_entry(table_type, stage, current, ports=None, description=None, services=None):
    """Return the ``ACL_TABLE`` entry after merging the given options into ``current``; omitted options are left untouched."""
    entry = normalize_table(current)
    entry.update({'type': table_type, 'stage': stage})
    if ports is not None:
        entry['ports'] = ordered_ports(entry.get('ports') or [], ports)
    if description is not None:
        entry['policy_desc'] = description
    if services is not None:
        entry['services'] = list(services)
    return entry


def ensure_table(db, state_db, table_name, entry):
    """Write ``entry`` (the complete desired table) if it differs from what is stored; returns an ``EntryChange``.

    ``mod_entry`` is used rather than ``set_entry`` so orchagent sees an
    update and adjusts port bindings in place instead of recreating the table.
    The table's STATE_DB status is cleared first so the status check after
    the write cannot pick up the status of the previous configuration.
    """
    before = normalize_table(db.get_entry(acl.ACL_TABLE, table_name))
    after = normalize_entry(entry)
    if before == after and (before or db.has_entry(acl.ACL_TABLE, table_name)):
        return EntryChange(False, before, after)
    acl.clear_status(state_db, acl.STATE_ACL_TABLE_TABLE, [table_name])
    db.mod_entry(acl.ACL_TABLE, table_name, after)
    return EntryChange(True, before, after)


def rules_of_tables(db, table_names):
    """Return the ``ACL_RULE`` keys that belong to the given tables."""
    return sorted(k for k in db.get_keys(acl.ACL_RULE) if split_key(k)[0] in table_names)


def resolve_layout(module, state_db, name, params, acl_tables):
    """Decide which tables make up the policy; returns ``(family_mode, {table: type}, probe)``.

    ``probe`` is ``True`` when the family mode could not be decided from an
    existing policy or the published capabilities and has to be found out
    by trying an ``L3V4V6`` table.
    """
    suffix = params['v6_suffix']
    if params['type'] is not None:
        return None, {name: params['type']}, False

    family_mode = params['family_mode'] or acl.FAMILY_AUTO
    existing_mode, existing = acl.layout_from_config(name, acl_tables, suffix)
    if family_mode != acl.FAMILY_AUTO:
        return family_mode, acl.tables_for_mode(name, family_mode, suffix), False
    if existing_mode is not None:
        return existing_mode, acl.tables_for_mode(name, existing_mode, suffix), False
    if existing:
        raise acl.AclError(
            'ACL table "%s" exists with type %s, which is not a dual-stack policy; pass type=%s to manage it'
            % (name, existing[name], existing[name]))

    supported = acl.capability_l3v4v6(state_db, params['stage'])
    if supported is not None:
        mode = acl.FAMILY_COMBINED if supported else acl.FAMILY_SPLIT
        return mode, acl.tables_for_mode(name, mode, suffix), False
    if module.check_mode:
        module.warn('family_mode=auto cannot probe L3V4V6 support in check mode; assuming "combined"')
        return acl.FAMILY_COMBINED, acl.tables_for_mode(name, acl.FAMILY_COMBINED, suffix), False
    if not params['status_timeout']:
        # Without the status check the probe cannot tell; split tables work everywhere.
        return acl.FAMILY_SPLIT, acl.tables_for_mode(name, acl.FAMILY_SPLIT, suffix), False
    return acl.FAMILY_COMBINED, acl.tables_for_mode(name, acl.FAMILY_COMBINED, suffix), True


def apply_tables(db, state_db, tables, acl_tables, params):
    """Write every table in ``tables`` and return ``{name: EntryChange}``."""
    changes = {}
    for table_name, table_type in tables.items():
        current = acl_tables.get(table_name, {})
        entry = build_table_entry(table_type, params['stage'], current, ports=params['ports'],
                                  description=params['description'], services=params['services'])
        changes[table_name] = ensure_table(db, state_db, table_name, entry)
    return changes


def remove_tables(db, table_names):
    """Delete the rules of the given tables and then the tables; returns ``({name: EntryChange}, removed rule keys)``."""
    rule_keys = rules_of_tables(db, table_names)
    for key in rule_keys:
        db.delete_entry(acl.ACL_RULE, key)
    changes = dict((t, db.ensure_absent(acl.ACL_TABLE, t)) for t in table_names)
    return changes, rule_keys


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        type=dict(type='str'),
        family_mode=dict(type='str', choices=[acl.FAMILY_AUTO, acl.FAMILY_COMBINED, acl.FAMILY_SPLIT]),
        v6_suffix=dict(type='str', default=acl.DEFAULT_V6_SUFFIX),
        stage=dict(type='str', default='ingress', choices=['ingress', 'egress']),
        ports=dict(type='list', elements='str'),
        description=dict(type='str'),
        services=dict(type='list', elements='str'),
        status_timeout=dict(type='int', default=30),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        mutually_exclusive=[['type', 'family_mode']],
    )
    params = module.params
    name = params['name']
    timeout = params['status_timeout']

    db = ConfigDB(module).connect()
    state_db = ConfigDB(module, db_name='STATE_DB').connect()
    try:
        acl_tables = db.get_table(acl.ACL_TABLE)
        params['ports'] = resolve_ports(db, params['ports'])
        family_mode, tables, probe = resolve_layout(module, state_db, name, params, acl_tables)
        extra = dict(tables=list(tables), family_mode=family_mode)
        if params['ports'] is not None:
            extra['ports'] = params['ports']

        if params['state'] == 'absent':
            # An explicit family_mode names the tables; auto removes whatever layout exists.
            present = [t for t in tables if t in acl_tables]
            changes, rules_removed = remove_tables(db, present)
            extra['tables'] = present
            if rules_removed:
                extra['rules_removed'] = rules_removed
        else:
            # Tables of a previous layout (combined -> split or back) are replaced.
            _mode, previous = acl.layout_from_config(name, acl_tables, params['v6_suffix'])
            stale = [t for t in previous if t not in tables]
            changes, rules_removed = remove_tables(db, stale)
            if rules_removed:
                extra['rules_removed'] = rules_removed
            changes.update(apply_tables(db, state_db, tables, acl_tables, params))

            if probe:
                statuses = acl.wait_for_status(state_db, acl.STATE_ACL_TABLE_TABLE, [name], timeout)
                if statuses[name] != acl.STATUS_ACTIVE:
                    # The ASIC refused L3V4V6 (or orchagent never answered): clean up and use split tables.
                    db.ensure_absent(acl.ACL_TABLE, name)
                    acl.wait_for_removal(state_db, acl.STATE_ACL_TABLE_TABLE, [name], timeout)
                    family_mode = acl.FAMILY_SPLIT
                    tables = acl.tables_for_mode(name, family_mode, params['v6_suffix'])
                    extra.update(tables=list(tables), family_mode=family_mode)
                    changes.update(apply_tables(db, state_db, tables, acl_tables, params))
            if not module.check_mode and timeout:
                acl.check_status(state_db, acl.STATE_ACL_TABLE_TABLE, list(tables), timeout,
                                 'ACL table%s %s' % ('s' if len(tables) > 1 else '', ', '.join(tables)))
    except ConfigDBError as e:
        module.fail_json(msg=str(e))

    before = dict((t, c.before) for t, c in changes.items() if c.before)
    after = dict((t, c.after) for t, c in changes.items() if c.after)
    changed = any(c.changed for c in changes.values()) or bool(extra.get('rules_removed'))
    module.exit_json(**build_result(changed, before, after, **extra))


def main():
    run_module()


if __name__ == '__main__':
    main()
