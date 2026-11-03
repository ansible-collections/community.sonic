# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for the config_save module.

The module shells out to ``sonic-cfggen`` and ``config save``; both are
replaced by :class:`FakeCommands`, which records every call and serves the
configured running configuration. The saved file is a real file under
``tmp_path``.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json

import pytest

from ansible.module_utils import basic

from ansible_collections.community.sonic.plugins.modules import config_save


RUNNING = {
    'DEVICE_METADATA': {'localhost': {'hostname': 'sonic', 'hwsku': 'Force10-S6000'}},
    'PORT': {'Ethernet0': {'alias': 'fortyGigE0/0', 'speed': '40000'}},
    'VLAN': {'Vlan3999': {'vlanid': '3999'}},
}


class FakeCommands(object):
    """Stand-in for ``AnsibleModule.run_command``/``get_bin_path``/``backup_local``.

    The bound methods are patched onto the class, so they do not take the
    module as their first argument.
    """

    def __init__(self):
        self.running = RUNNING
        self.cfggen_rc = 0
        self.cfggen_stdout = None
        self.cfggen_stderr = ''
        self.save_rc = 0
        self.save_stderr = ''
        self.calls = []
        self.backups = []

    def get_bin_path(self, name, required=False, opt_dirs=None):
        return '/usr/local/bin/' + name

    def run_command(self, args, **kwargs):
        self.calls.append(list(args))
        if args[0].endswith('sonic-cfggen'):
            assert args[1:] == ['-d', '--print-data']
            out = self.cfggen_stdout if self.cfggen_stdout is not None else json.dumps(self.running, indent=4)
            return self.cfggen_rc, out, self.cfggen_stderr
        if args[0].endswith('config'):
            assert args[1:3] == ['save', '-y']
            if self.save_rc == 0:
                with open(args[3], 'w') as f:
                    json.dump(self.running, f, indent=4)
            return self.save_rc, 'Running command: /usr/local/bin/sonic-cfggen -d --print-data > %s\n' % args[3], self.save_stderr
        raise AssertionError('unexpected command %r' % (args,))

    def backup_local(self, fn):
        backup = fn + '.2026-11-03@14:05:11~'
        with open(fn, 'rb') as src, open(backup, 'wb') as dst:
            dst.write(src.read())
        self.backups.append(backup)
        return backup

    @property
    def save_calls(self):
        return [c for c in self.calls if c[0].endswith('config')]


@pytest.fixture
def commands(monkeypatch):
    fake = FakeCommands()
    monkeypatch.setattr(basic.AnsibleModule, 'get_bin_path', fake.get_bin_path)
    monkeypatch.setattr(basic.AnsibleModule, 'run_command', fake.run_command)
    monkeypatch.setattr(basic.AnsibleModule, 'backup_local', fake.backup_local)
    monkeypatch.setattr(config_save.os, 'geteuid', lambda: 0)
    return fake


@pytest.fixture
def saved_file(tmp_path):
    """Path of the saved configuration file; ``write(config)`` fills it, ``read()`` parses it."""
    path = tmp_path / 'config_db.json'

    class Saved(object):
        def __str__(self):
            return str(path)

        def write(self, config, text=None):
            path.write_text(text if text is not None else json.dumps(config, indent=4))
            return self

        def read(self):
            return json.loads(path.read_text())

        def exists(self):
            return path.exists()

    return Saved()


def not_root(monkeypatch):
    monkeypatch.setattr(config_save.os, 'geteuid', lambda: 1000)


# -- pure helpers --------------------------------------------------------------

def test_normalize_config_converts_values_and_drops_empty_tables():
    config = {
        'VLAN': {'Vlan10': {'vlanid': 10, 'dhcp_servers': ['10.0.0.1', 2]}},
        'EMPTY': {},
        'NOT_A_TABLE': 'x',
        'FLAGS': {'localhost': {'enabled': True}},
    }
    assert config_save.normalize_config(config) == {
        'VLAN': {'Vlan10': {'vlanid': '10', 'dhcp_servers': ['10.0.0.1', '2']}},
        'FLAGS': {'localhost': {'enabled': 'true'}},
    }
    assert config_save.normalize_config(None) == {}


def test_config_diff_is_table_level():
    before = {'PORT': {'Ethernet0': {'speed': '40000'}}, 'VLAN': {'Vlan10': {'vlanid': '10'}}, 'OLD': {'k': {}}}
    after = {'PORT': {'Ethernet0': {'speed': '40000'}}, 'VLAN': {'Vlan20': {'vlanid': '20'}}, 'NEW': {'k': {}}}
    changed, before_diff, after_diff = config_save.config_diff(before, after)
    assert changed == ['NEW', 'OLD', 'VLAN']
    assert before_diff == {'VLAN': {'Vlan10': {'vlanid': '10'}}, 'OLD': {'k': {}}}
    assert after_diff == {'VLAN': {'Vlan20': {'vlanid': '20'}}, 'NEW': {'k': {}}}
    assert config_save.config_diff(before, before) == ([], {}, {})


# -- module runs ---------------------------------------------------------------

def test_unchanged_when_file_matches(commands, saved_file, run_module):
    saved_file.write(RUNNING)
    result = run_module(config_save, dict(path=str(saved_file)))
    assert result['changed'] is False
    assert result['path'] == str(saved_file)
    assert result['changed_tables'] == []
    assert result['diff']['before'] == {}
    assert result['diff']['after'] == {}
    assert 'backup_file' not in result
    assert 'config' not in result
    assert commands.save_calls == []


def test_unchanged_ignores_order_and_value_types(commands, saved_file, run_module):
    # Same content, different key order, numbers instead of strings and an empty table.
    reordered = {
        'VLAN': {'Vlan3999': {'vlanid': 3999}},
        'PORT': {'Ethernet0': {'speed': 40000, 'alias': 'fortyGigE0/0'}},
        'DEVICE_METADATA': {'localhost': {'hwsku': 'Force10-S6000', 'hostname': 'sonic'}},
        'ACL_TABLE': {},
    }
    saved_file.write(reordered)
    result = run_module(config_save, dict(path=str(saved_file)))
    assert result['changed'] is False
    assert commands.save_calls == []


def test_changed_writes_with_config_save(commands, saved_file, run_module):
    saved_file.write({'DEVICE_METADATA': RUNNING['DEVICE_METADATA'], 'PORT': RUNNING['PORT']})
    result = run_module(config_save, dict(path=str(saved_file)))
    assert result['changed'] is True
    assert result['changed_tables'] == ['VLAN']
    assert result['diff'] == {
        'before': {},
        'after': {'VLAN': {'Vlan3999': {'vlanid': '3999'}}},
        'before_header': str(saved_file),
        'after_header': 'running CONFIG_DB',
    }
    assert 'backup_file' not in result
    assert commands.save_calls == [['/usr/local/bin/config', 'save', '-y', str(saved_file)]]
    assert saved_file.read() == RUNNING


def test_changed_diff_shows_only_differing_tables(commands, saved_file, run_module):
    saved = {
        'DEVICE_METADATA': RUNNING['DEVICE_METADATA'],
        'PORT': {'Ethernet0': {'alias': 'fortyGigE0/0', 'speed': '10000'}},
        'VLAN': RUNNING['VLAN'],
        'VLAN_MEMBER': {'Vlan3999|Ethernet0': {'tagging_mode': 'tagged'}},
    }
    saved_file.write(saved)
    result = run_module(config_save, dict(path=str(saved_file)))
    assert result['changed'] is True
    assert result['changed_tables'] == ['PORT', 'VLAN_MEMBER']
    assert result['diff']['before'] == {'PORT': saved['PORT'], 'VLAN_MEMBER': saved['VLAN_MEMBER']}
    assert result['diff']['after'] == {'PORT': RUNNING['PORT']}


def test_check_mode_reports_change_without_writing(commands, saved_file, run_module):
    saved_file.write({'DEVICE_METADATA': RUNNING['DEVICE_METADATA']})
    result = run_module(config_save, dict(path=str(saved_file), backup=True), check_mode=True)
    assert result['changed'] is True
    assert result['changed_tables'] == ['PORT', 'VLAN']
    assert result['diff']['after'] == {'PORT': RUNNING['PORT'], 'VLAN': RUNNING['VLAN']}
    assert 'backup_file' not in result
    assert commands.save_calls == []
    assert commands.backups == []
    assert saved_file.read() == {'DEVICE_METADATA': RUNNING['DEVICE_METADATA']}


def test_check_mode_unchanged(commands, saved_file, run_module):
    saved_file.write(RUNNING)
    result = run_module(config_save, dict(path=str(saved_file)), check_mode=True)
    assert result['changed'] is False
    assert commands.save_calls == []


def test_missing_file_is_created(commands, saved_file, run_module):
    result = run_module(config_save, dict(path=str(saved_file), backup=True))
    assert result['changed'] is True
    assert result['changed_tables'] == ['DEVICE_METADATA', 'PORT', 'VLAN']
    assert result['diff']['before'] == {}
    # Nothing to back up when the file did not exist.
    assert 'backup_file' not in result
    assert commands.backups == []
    assert saved_file.read() == RUNNING


def test_backup_keeps_previous_file(commands, saved_file, run_module):
    previous = {'DEVICE_METADATA': RUNNING['DEVICE_METADATA']}
    saved_file.write(previous)
    result = run_module(config_save, dict(path=str(saved_file), backup=True))
    assert result['changed'] is True
    assert result['backup_file'] == str(saved_file) + '.2026-11-03@14:05:11~'
    assert commands.backups == [result['backup_file']]
    with open(result['backup_file']) as f:
        assert json.load(f) == previous
    assert saved_file.read() == RUNNING


def test_no_backup_when_unchanged(commands, saved_file, run_module):
    saved_file.write(RUNNING)
    result = run_module(config_save, dict(path=str(saved_file), backup=True))
    assert result['changed'] is False
    assert 'backup_file' not in result
    assert commands.backups == []


def test_return_config(commands, saved_file, run_module):
    saved_file.write({})
    result = run_module(config_save, dict(path=str(saved_file), return_config=True))
    assert result['changed'] is True
    assert result['config'] == RUNNING
    # In check mode the running configuration (what would be saved) is returned too.
    result = run_module(config_save, dict(path=str(saved_file), return_config=True), check_mode=True)
    assert result['changed'] is False
    assert result['config'] == RUNNING


def test_invalid_json_is_overwritten_with_warning(commands, saved_file, run_module, monkeypatch):
    warnings = []
    monkeypatch.setattr(basic.AnsibleModule, 'warn', lambda self, msg: warnings.append(msg))
    saved_file.write(None, text='{not json')
    result = run_module(config_save, dict(path=str(saved_file)))
    assert result['changed'] is True
    assert result['diff']['before'] == {}
    assert len(warnings) == 1 and 'not valid JSON' in warnings[0]
    assert saved_file.read() == RUNNING


def test_not_root_fails_when_a_write_is_needed(commands, saved_file, run_module, monkeypatch):
    not_root(monkeypatch)
    saved_file.write({})
    result = run_module(config_save, dict(path=str(saved_file)), expect_failure=True)
    assert result['msg'] == 'writing %s requires root privileges; run the task with "become: true" (or as root)' % saved_file
    assert result['changed_tables'] == ['DEVICE_METADATA', 'PORT', 'VLAN']
    assert commands.save_calls == []
    assert saved_file.read() == {}


def test_not_root_can_compare(commands, saved_file, run_module, monkeypatch):
    not_root(monkeypatch)
    saved_file.write({})
    result = run_module(config_save, dict(path=str(saved_file)), check_mode=True)
    assert result['changed'] is True
    saved_file.write(RUNNING)
    result = run_module(config_save, dict(path=str(saved_file)))
    assert result['changed'] is False
    assert commands.save_calls == []


def test_unreadable_file_fails_with_become_hint(commands, saved_file, run_module, monkeypatch):
    def unreadable(*args, **kwargs):
        raise IOError(13, 'Permission denied')

    monkeypatch.setattr(config_save, 'open', unreadable, raising=False)
    result = run_module(config_save, dict(path=str(saved_file)), expect_failure=True)
    assert result['msg'].startswith('cannot read %s: ' % saved_file)
    assert 'become: true' in result['msg']
    assert commands.save_calls == []


def test_cfggen_failure(commands, saved_file, run_module):
    commands.cfggen_rc = 2
    commands.cfggen_stderr = 'Error: cannot connect to redis\n'
    result = run_module(config_save, dict(path=str(saved_file)), expect_failure=True)
    assert result['msg'] == 'sonic-cfggen -d --print-data failed with rc 2: Error: cannot connect to redis'
    assert result['rc'] == 2
    assert commands.save_calls == []


def test_cfggen_garbage_output(commands, saved_file, run_module):
    commands.cfggen_stdout = 'not json'
    result = run_module(config_save, dict(path=str(saved_file)), expect_failure=True)
    assert result['msg'].startswith('could not parse the output of sonic-cfggen -d --print-data')
    commands.cfggen_stdout = '[]'
    result = run_module(config_save, dict(path=str(saved_file)), expect_failure=True)
    assert result['msg'] == 'unexpected output from sonic-cfggen -d --print-data: not a JSON object'


def test_config_save_failure(commands, saved_file, run_module):
    commands.save_rc = 1
    commands.save_stderr = 'Root privileges are required for this operation\n'
    saved_file.write({})
    result = run_module(config_save, dict(path=str(saved_file)), expect_failure=True)
    assert result['msg'] == ('config save -y %s failed with rc 1: Root privileges are required for this operation'
                             % saved_file)
    assert result['path'] == str(saved_file)
    assert saved_file.read() == {}
