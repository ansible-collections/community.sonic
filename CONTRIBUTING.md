# Contributing

We welcome bug reports, fixes, documentation improvements, and new maintainers.
Report bugs and request features in the
[issue tracker](https://github.com/ansible-collections/community.sonic/issues).
Include the collection, ansible-core, Python, and SONiC versions, a minimal
playbook, and the expected and actual results. Remove credentials from reports.

Open pull requests against `main`. Add regression tests for behavior changes
and an appropriate YAML fragment under `changelogs/fragments/`. Run the unit,
sanity, documentation, and changelog checks described in [README.md](README.md)
and [MAINTAINING.md](MAINTAINING.md). Integration tests require a KVM-capable host.

Follow the [Ansible contribution guide](https://docs.ansible.com/projects/ansible/latest/community/index.html)
and our [Code of Conduct](CODE_OF_CONDUCT.md), including its reporting process.
Join the [Ansible Forum](https://forum.ansible.com/c/project/collection-development/27)
for collection development questions; use the `collections` tag and mention
`community.sonic` in the topic title.

## Writing a module

The modules in this collection run on the SONiC host and talk to the
configuration database (CONFIG_DB) through SONiC's `swsscommon` Python
bindings. The shared plumbing lives in
`plugins/module_utils/config_db.py`; new modules should build on it rather
than calling `swsscommon` directly. Open issues
[#21](https://github.com/ansible-collections/community.sonic/issues/21) to
[#36](https://github.com/ansible-collections/community.sonic/issues/36) list
the modules we would like to see.

### Naming convention

Modules use short names without a `sonic_` prefix: `vlan`, `portchannel`,
`acl_table`, `feature`, `interface_ip`, ... The fully qualified name
`community.sonic.vlan` already carries the collection name. Name a module after
the CONFIG_DB object it manages, in singular form, and use `<parent>_member` for
membership tables (`vlan_member`, `portchannel_member`). The one legacy module,
`sonic_interface_port`, was renamed to `interface_port`; the old name is a
deprecated redirect in `meta/runtime.yml` and is removed in 2.0.0. Options are
`snake_case`, booleans are Ansible booleans (`enabled: true`, not
`admin_status: up`), and `state` takes `present`/`absent`.

### The helper layer

```python
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.sonic.plugins.module_utils.config_db import (
    ConfigDB, ConfigDBError, bool_to_up_down)


def run_module():
    module = AnsibleModule(argument_spec=dict(...), supports_check_mode=True)
    db = ConfigDB(module).connect()          # fails with missing_required_lib if swsscommon is absent
    try:
        port = db.resolve_port(module.params['interface'])   # 'QSFP1' -> 'Ethernet0'
        change = db.ensure_entry('PORT', port,
                                 {'admin_status': bool_to_up_down(module.params['enabled'])},
                                 exclusive=False)
    except ConfigDBError as e:
        module.fail_json(msg=str(e))
    module.exit_json(**change.result(interface=port))
```

`ConfigDB` wraps `swsscommon.ConfigDBConnector`:

* `connect()` connects and returns the wrapper. `ConfigDB(module, db_name='STATE_DB')`
  connects to another SONiC database for read-only checks (feature status, ACL state).
* Reads: `get_table(table)`, `get_keys(table)`, `get_entry(table, key)`,
  `has_entry(table, key)`, `get_config()`. Compound keys are returned as
  `'Vlan100|Ethernet0'` strings. `get_entry` returns `{}` for absent *and* for
  empty entries (SONiC stores membership-style entries as `{}`), so use
  `has_entry` when presence matters.
* Writes: `set_entry` (replace), `mod_entry` (merge), `delete_entry`,
  `delete_table`. **All writes are skipped in check mode**, so modules can be
  written straight-line.
* `ensure_entry(table, key, desired, exclusive=True)` compares the normalised
  `desired` entry with the stored one, writes only when needed (never in check
  mode) and returns an `EntryChange(changed, before, after)` whose `.diff` and
  `.result(**extra)` build the module output. Use `exclusive=True` when the
  module owns the whole entry (`VLAN`, `VLAN_MEMBER`); use `exclusive=False`
  to merge into entries that carry fields you do not manage (`DEVICE_METADATA`,
  `FEATURE`, `PORT`), where a field value of `None` removes that field.
  `ensure_absent(table, key)` or `desired=None` deletes the entry.
* Values are normalised to what CONFIG_DB stores: numbers become strings,
  lists become lists of strings, booleans become `'true'`/`'false'`. Use
  `bool_to_up_down`, `bool_to_enabled_disabled` and `str_to_bool` for the
  other vocabularies SONiC uses.
* Interface helpers: `resolve_port(name)` and `resolve_interface(name)` accept
  port aliases; `interface_kind`, `interface_table` and `l3_interface_table`
  map `Ethernet*`/`PortChannel*`/`Vlan*`/`Loopback*` to `INTERFACE`,
  `PORTCHANNEL_INTERFACE`, `VLAN_INTERFACE` and `LOOPBACK_INTERFACE`.
  `join_key`/`split_key` handle compound keys.
* Errors derive from `ConfigDBError` (`UnknownInterfaceError`,
  `UnsupportedInterfaceError`); catch it and call `fail_json(msg=str(e))`.

Keep the pure logic of a module (building the desired entry from the
parameters) in a plain function so it can be unit tested without a database;
see `build_vlan_entry` in `plugins/modules/vlan.py`.

### Check mode, diff mode and results

Every module declares `supports_check_mode=True` and documents
`check_mode: full` and `diff_mode: full` (or `none` for read-only modules) in
its `attributes`. Results always contain `changed` and
`diff: {before: <entry>, after: <entry>}` where an absent entry is `{}`;
`EntryChange.result()` and `build_result()` produce this layout. In check mode
`changed` and `diff` must be exactly what a real run would report, with no
writes. Running a module twice must report `changed: false` the second time.
Mark secrets (SNMP communities, keys) `no_log=True` and keep them out of the
diff.

### Tests

* Unit tests live under `tests/unit/plugins/modules/test_<module>.py`. The
  fixtures in `tests/unit/conftest.py` give you `fake_swsscommon`, a dict-backed
  CONFIG_DB that mirrors the real connector's quirks, and
  `run_module(module, params, check_mode=False, expect_failure=False)`, which
  runs the module and returns its result dictionary:

  ```python
  def test_create(fake_swsscommon, run_module):
      fake_swsscommon.seed({'PORT': {'Ethernet0': {'alias': 'QSFP1'}}})
      result = run_module(my_module, dict(interface='QSFP1', enabled=True))
      assert result['changed'] is True
      assert fake_swsscommon.get_entry('PORT', 'Ethernet0')['admin_status'] == 'up'
      assert fake_swsscommon.writes == [('mod_entry', 'PORT', 'Ethernet0', {'admin_status': 'up'})]
  ```

  Cover: create, idempotent re-run, modify, remove, check mode for each of
  those, and the failure messages.
* Integration tests run against a virtual switch and live in
  `tests/integration/targets/<module>/` with an `aliases` file containing
  `network/sonic/group1` and `tasks/main.yaml` that creates, re-applies
  (asserting `not changed`), checks the result with `community.sonic.get_entry`
  or a `show` command, and cleans up what it created.
* Run `ansible-test units --venv --python 3.13`, `ansible-test sanity --venv
  --python 3.13`, `antsibull-changelog lint` and `antsibull-docs
  lint-collection-docs .` before opening a pull request. The GitHub Actions
  integration jobs must pass for modules that write to the device.

### Changelog fragments

Add `changelogs/fragments/<branch-or-topic>.yml` to every pull request. A new
module does not need a fragment (the changelog generator picks it up from the
module's `version_added`); set `version_added` to the next minor release. Other
changes use the `minor_changes`, `bugfixes` or `breaking_changes` sections and
start with the module name: `- vlan - compare the VLAN ID as a string.`.
