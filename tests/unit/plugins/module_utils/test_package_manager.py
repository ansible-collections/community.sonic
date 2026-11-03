# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for module_utils.package_manager."""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json

import pytest

from ansible.module_utils import basic
from ansible.module_utils.testing import patch_module_args

from ansible_collections.community.sonic.plugins.module_utils import package_manager as pm
from ansible_collections.community.sonic.tests.unit.fake_spm import record, render_list


DATABASE = {
    'database': record('docker-database', 'SONiC database service', '1.0.0', '1.0.0', installed=True, built_in=True),
    'my-exporter': record('registry.example.net/sonic/my-exporter', 'Prometheus exporter', '1.4.2', '1.4.1',
                          installed=True, image_id='sha256:abc', docker_image_reference='registry.example.net/sonic/my-exporter:1.4.1'),
    'dhcp-relay': record('docker-dhcp-relay', None, None, None),
}


def test_parse_database():
    parsed = pm.parse_database(json.dumps(DATABASE))
    assert sorted(parsed) == ['database', 'dhcp-relay', 'my-exporter']
    assert parsed['database'] == dict(
        name='database', repository='docker-database', description='SONiC database service',
        default_reference='1.0.0', version='1.0.0', installed=True, built_in=True,
        image_id=None, docker_image_reference=None, status='Built-In')
    assert parsed['my-exporter']['status'] == 'Installed'
    assert parsed['my-exporter']['version'] == '1.4.1'
    assert parsed['my-exporter']['default_reference'] == '1.4.2'
    assert parsed['my-exporter']['image_id'] == 'sha256:abc'
    assert parsed['dhcp-relay'] == dict(
        name='dhcp-relay', repository='docker-dhcp-relay', description=None, default_reference=None,
        version=None, installed=False, built_in=False, image_id=None, docker_image_reference=None,
        status='Not Installed')


@pytest.mark.parametrize('content,message', (
    ('{not json', 'is not valid JSON'),
    ('[]', 'does not contain a JSON object'),
    ('{"x": 1}', 'entry for x is not a JSON object'),
))
def test_parse_database_errors(content, message):
    with pytest.raises(pm.PackageManagerError) as excinfo:
        pm.parse_database(content)
    assert message in str(excinfo.value)


def test_parse_list_output_matches_database():
    output = render_list(DATABASE)
    parsed = pm.parse_list_output(output)
    expected = pm.parse_database(json.dumps(DATABASE))
    for entry in expected.values():
        # The table does not carry these fields.
        entry['default_reference'] = None
        entry['image_id'] = None
        entry['docker_image_reference'] = None
    assert parsed == expected


def test_parse_list_output_real_sample():
    widths = (14, 32, 28, 9, 13)

    def row(*values):
        return '  '.join(v.ljust(w) for v, w in zip(values, widths)).rstrip() + '\n'

    output = (
        row('Name', 'Repository', 'Description', 'Version', 'Status')
        + '  '.join('-' * w for w in widths) + '\n'
        + row('database', 'docker-database', 'SONiC database service', '1.0.0', 'Built-In')
        + row('dhcp-relay', 'docker-dhcp-relay', 'N/A', 'N/A', 'Not Installed')
        + row('my-exporter', 'registry.example.net/my-exporter', 'Prometheus exporter: sensors', '1.4.2', 'Installed')
    )
    parsed = pm.parse_list_output(output)
    assert parsed['dhcp-relay']['repository'] == 'docker-dhcp-relay'
    assert parsed['dhcp-relay']['description'] is None
    assert parsed['dhcp-relay']['version'] is None
    assert parsed['dhcp-relay']['installed'] is False
    assert parsed['my-exporter']['repository'] == 'registry.example.net/my-exporter'
    assert parsed['my-exporter']['description'] == 'Prometheus exporter: sensors'
    assert parsed['my-exporter']['installed'] is True
    assert parsed['my-exporter']['status'] == 'Installed'
    assert parsed['database']['built_in'] is True


@pytest.mark.parametrize('output', ('', 'garbage\n', 'Foo  Bar\n---  ---\n'))
def test_parse_list_output_errors(output):
    with pytest.raises(pm.PackageManagerError) as excinfo:
        pm.parse_list_output(output)
    assert 'unexpected output from sonic-package-manager list' in str(excinfo.value)


@pytest.mark.parametrize('version,expected', (
    (None, None), ('1.2.3', '1.2.3'), (' 1.2.3 ', '1.2.3'), ('1.2.3_build4', '1.2.3+build4'),
))
def test_normalize_version(version, expected):
    assert pm.normalize_version(version) == expected


@pytest.mark.parametrize('version,expected', (
    (None, 'pkg'),
    ('1.4.2', 'pkg==1.4.2'),
    ('1.4.2-rc1', 'pkg==1.4.2-rc1'),
    ('1.4.2+build.7', 'pkg==1.4.2+build.7'),
    ('v1.4.2', 'pkg@v1.4.2'),
    ('latest', 'pkg@latest'),
    ('sha256:0123abcd', 'pkg@sha256:0123abcd'),
))
def test_package_expression(version, expected):
    assert pm.package_expression('pkg', version) == expected


def test_is_tarball_source(tmp_path):
    assert pm.is_tarball_source('/tmp/pkg.tar') is True
    assert pm.is_tarball_source('./pkg.tar') is True
    assert pm.is_tarball_source('../pkg.tar') is True
    assert pm.is_tarball_source('registry.example.net/sonic/my-exporter:1.4.2') is False
    assert pm.is_tarball_source('my-exporter') is False
    tarball = tmp_path / 'pkg.tar'
    tarball.write_bytes(b'')
    assert pm.is_tarball_source(str(tarball)) is True


class FakeModule(object):
    """Minimal AnsibleModule stand-in for the PackageManager tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_bin_path(self, name, required=False):
        return '/usr/local/bin/' + name

    def run_command(self, args):
        self.calls.append(list(args))
        return self.responses.pop(0)


def test_read_database_from_file(tmp_path):
    path = tmp_path / 'packages.json'
    path.write_text(json.dumps(DATABASE))
    module = FakeModule([])
    manager = pm.PackageManager(module, database_path=str(path))
    database = manager.read_database()
    assert database['my-exporter']['version'] == '1.4.1'
    assert module.calls == []


def test_read_database_falls_back_to_list_when_unreadable(tmp_path):
    module = FakeModule([(0, render_list(DATABASE), '')])
    manager = pm.PackageManager(module, database_path=str(tmp_path / 'missing.json'))
    database = manager.read_database()
    assert module.calls == [['/usr/local/bin/sonic-package-manager', 'list']]
    assert database['my-exporter']['installed'] is True
    assert database['my-exporter']['version'] == '1.4.1'
    # Reading the state is not recorded as a command that changed something.
    assert manager.commands == []


def test_read_database_fallback_failure_reports_last_line(tmp_path):
    module = FakeModule([(1, '', 'Traceback ...\nFailed to list repositories: cannot connect to docker\n')])
    manager = pm.PackageManager(module, database_path=str(tmp_path / 'missing.json'))
    with pytest.raises(pm.PackageManagerError) as excinfo:
        manager.read_database()
    assert str(excinfo.value) == ('sonic-package-manager list failed with rc 1: '
                                  'Failed to list repositories: cannot connect to docker')


def test_run_records_commands_and_errors(tmp_path):
    module = FakeModule([(0, 'ok', ''), (2, 'stdout message\n', 'INFO: pulling\n')])
    manager = pm.PackageManager(module, database_path=str(tmp_path / 'db.json'))
    assert manager.run(['repository', 'remove', 'x'], 'remove') == 'ok'
    assert manager.commands == ['/usr/local/bin/sonic-package-manager repository remove x']
    with pytest.raises(pm.PackageManagerError) as excinfo:
        manager.run(['install', '-y', 'x'], 'install')
    assert str(excinfo.value) == 'install failed with rc 2: INFO: pulling'
    assert excinfo.value.details == dict(rc=2, stdout='stdout message\n', stderr='INFO: pulling\n')
    assert manager.commands[-1] == '/usr/local/bin/sonic-package-manager install -y x'


@pytest.mark.parametrize('stdout,stderr,expected', (
    ('Failed to install x: boom\n', 'INFO: Downloading x\nINFO: done\n', 'Failed to install x: boom'),
    ('', 'Traceback\n  File ...\nPackageManagerError: Error: no\n', 'PackageManagerError: Error: no'),
    ('Usage: ...\n\nError: No such option: --bogus\n', '', 'Error: No such option: --bogus'),
    ('', '', 'no output'),
    ('something\n', 'else\n', 'else'),
))
def test_error_line(stdout, stderr, expected):
    assert pm.error_line(stdout, stderr) == expected


def test_run_privileged_requires_root(tmp_path, monkeypatch):
    module = FakeModule([])
    manager = pm.PackageManager(module, database_path=str(tmp_path / 'db.json'))
    monkeypatch.setattr(pm.os, 'geteuid', lambda: 1000)
    with pytest.raises(pm.PackageManagerError) as excinfo:
        manager.run_privileged(['install', '-y', 'x'], 'sonic-package-manager install x')
    assert str(excinfo.value) == ('sonic-package-manager install x requires root privileges; '
                                  'run the task with "become: true" (or as root)')
    assert module.calls == []


def test_show_manifest(tmp_path):
    module = FakeModule([(0, json.dumps({'package': {'name': 'x', 'version': '1.0.0'}}), ''),
                         (0, 'not json', ''), (0, '[]', '')])
    manager = pm.PackageManager(module, database_path=str(tmp_path / 'db.json'))
    assert manager.show_manifest(['--from-tarball', '/tmp/x.tar'])['package']['version'] == '1.0.0'
    assert module.calls[-1] == ['/usr/local/bin/sonic-package-manager', 'show', 'package', 'manifest',
                                '--from-tarball', '/tmp/x.tar']
    with pytest.raises(pm.PackageManagerError) as excinfo:
        manager.show_manifest(['--from-tarball', '/tmp/x.tar'])
    assert 'could not parse the manifest' in str(excinfo.value)
    with pytest.raises(pm.PackageManagerError) as excinfo:
        manager.show_manifest(['--from-tarball', '/tmp/x.tar'])
    assert 'not a JSON object' in str(excinfo.value)


def test_spm_fixture_uses_real_ansible_module(spm, monkeypatch):
    """The ``spm`` fixture wires the fake into AnsibleModule and the default database path."""
    with patch_module_args({}):
        module = basic.AnsibleModule(argument_spec={})
    manager = pm.PackageManager(module)
    assert manager.database_path == spm.database_path
    assert manager.read_database()['database']['status'] == 'Built-In'
    assert manager.list_packages()['database']['status'] == 'Built-In'
    assert spm.calls == [['list']]
