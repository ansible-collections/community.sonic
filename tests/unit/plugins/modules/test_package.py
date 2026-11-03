# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for the package module, run against the fake sonic-package-manager."""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.sonic.plugins.module_utils import package_manager
from ansible_collections.community.sonic.plugins.modules import package
from ansible_collections.community.sonic.tests.unit.fake_spm import BUILT_IN, record


REPO = 'registry.example.net/sonic/my-exporter'
TARBALL = '/tmp/my-exporter-1.4.2.tar'


def seed_exporter(spm, default_reference='1.4.2', **kwargs):
    """Register the exporter repository; ``installed=True, version=...`` installs it."""
    db = dict(BUILT_IN)
    db['my-exporter'] = record(REPO, 'Prometheus exporter', default_reference, **kwargs)
    spm.seed(db)
    spm.registry[REPO + ':1.4.1'] = ('my-exporter', '1.4.1')
    spm.registry[REPO + ':1.4.2'] = ('my-exporter', '1.4.2')
    spm.registry[REPO + ':1.5.0'] = ('my-exporter', '1.5.0')
    spm.registry[REPO + ':latest'] = ('my-exporter', '1.5.0')
    spm.tarballs[TARBALL] = ('my-exporter', '1.4.2', 'my-exporter')
    spm.tarballs['/tmp/my-exporter-1.5.0.tar'] = ('my-exporter', '1.5.0', 'my-exporter')


def installed(spm, name='my-exporter'):
    rec = spm.database().get(name)
    return (rec or {}).get('installed', False), (rec or {}).get('installed-version')


# -- pure helpers --------------------------------------------------------------

def base_params(**overrides):
    params = dict(name='my-exporter', version=None, source=None, state='present', enabled=None, owner=None,
                  allow_downgrade=False, skip_host_plugins=False, keep_config=False, force=False,
                  custom_name=None, manifest=None)
    params.update(overrides)
    return params


def test_install_arguments_minimal():
    assert package.install_arguments(base_params(), None) == ['install', '-y', 'my-exporter']
    assert package.install_arguments(base_params(), '1.4.2') == ['install', '-y', 'my-exporter==1.4.2']


def test_install_arguments_all_options():
    params = base_params(enabled=True, owner='kube', allow_downgrade=True, skip_host_plugins=True, force=True,
                         custom_name='exp', manifest=True)
    # SPM only accepts --enable/--set-owner on a first install and --allow-downgrade on an upgrade.
    assert package.install_arguments(params, 'v2') == [
        'install', '-y', '--force', '--skip-host-plugins', '--enable', '--set-owner', 'kube',
        '--name', 'exp', '--use-local-manifest', 'my-exporter@v2']
    assert package.install_arguments(params, 'v2', upgrade=True) == [
        'install', '-y', '--force', '--skip-host-plugins', '--allow-downgrade',
        '--name', 'exp', '--use-local-manifest', 'my-exporter@v2']


def test_install_arguments_enabled_false_passes_nothing():
    assert package.install_arguments(base_params(enabled=False), None) == ['install', '-y', 'my-exporter']


@pytest.mark.parametrize('source,version,expected', (
    ('/tmp/x.tar', None, ['--from-tarball', '/tmp/x.tar']),
    ('/tmp/x.tar', '1.0.0', ['--from-tarball', '/tmp/x.tar']),
    ('registry.example.net/sonic/x', None, ['--from-repository', 'registry.example.net/sonic/x']),
    ('registry.example.net/sonic/x', '1.0.0', ['--from-repository', 'registry.example.net/sonic/x:1.0.0']),
    ('registry.example.net:5000/sonic/x', '1.0.0', ['--from-repository', 'registry.example.net:5000/sonic/x:1.0.0']),
    ('registry.example.net/sonic/x:2.0.0', '1.0.0', ['--from-repository', 'registry.example.net/sonic/x:2.0.0']),
    ('registry.example.net/sonic/x@sha256:abcd', '1.0.0', ['--from-repository', 'registry.example.net/sonic/x@sha256:abcd']),
))
def test_source_arguments(source, version, expected):
    assert package.source_arguments(source, version) == expected


def test_uninstall_arguments():
    assert package.uninstall_arguments(base_params()) == ['uninstall', '-y', 'my-exporter']
    assert package.uninstall_arguments(base_params(force=True, keep_config=True)) == [
        'uninstall', '-y', '--force', '--keep-config', 'my-exporter']


def test_highest_version():
    assert package.highest_version(['1.4.1', '1.10.0', '1.9.3', '', 'latest', '2.0.0-rc1']) == '1.10.0'
    assert package.highest_version(['1.0.0-rc1', '1.0.0', '0.9.0+build.2']) == '1.0.0'
    assert package.highest_version(['latest', 'edge', '2.0.0-rc1']) is None
    assert package.highest_version([]) is None


# -- install -------------------------------------------------------------------

def test_install_from_repository(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter', version='1.4.2'))
    assert result['changed'] is True
    assert result['installed'] is True
    assert result['version'] == '1.4.2'
    assert result['repository'] == REPO
    assert result['status'] == 'Installed'
    assert result['diff'] == {
        'before': {'installed': False, 'version': None, 'repository': REPO},
        'after': {'installed': True, 'version': '1.4.2', 'repository': REPO},
    }
    assert result['commands'] == ['%s install -y my-exporter==1.4.2' % spm.BIN]
    assert spm.calls == [['install', '-y', 'my-exporter==1.4.2']]
    assert installed(spm) == (True, '1.4.2')


def test_install_default_reference_when_no_version(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter'))
    assert result['changed'] is True
    assert result['version'] == '1.4.2'
    # The default reference is resolved by the module so the result can report it.
    assert spm.calls == [['install', '-y', 'my-exporter==1.4.2']]


def test_install_check_mode(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter', version='1.4.2'), check_mode=True)
    assert result['changed'] is True
    assert result['installed'] is True
    assert result['version'] == '1.4.2'
    assert result['status'] == 'Installed'
    assert result['commands'] == []
    assert spm.calls == []
    assert installed(spm) == (False, None)
    # Without a version the default reference is reported.
    result = run_module(package, dict(name='my-exporter'), check_mode=True)
    assert result['version'] == '1.4.2'


def test_install_idempotent(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    for params in (dict(name='my-exporter', version='1.4.2'), dict(name='my-exporter'),
                   dict(name='my-exporter', version='1.4.2', enabled=True, owner='kube')):
        for check_mode in (False, True):
            result = run_module(package, params, check_mode=check_mode)
            assert result['changed'] is False
            assert result['installed'] is True
            assert result['version'] == '1.4.2'
            assert result['status'] == 'Installed'
            assert result['diff']['before'] == result['diff']['after']
            assert result['commands'] == []
    assert spm.calls == []


def test_install_passes_options(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter', version='1.4.2', enabled=True, owner='local',
                                      skip_host_plugins=True, force=True))
    assert result['changed'] is True
    assert spm.calls == [['install', '-y', '--force', '--skip-host-plugins', '--enable', '--set-owner', 'local',
                          'my-exporter==1.4.2']]


def test_upgrade(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.1')
    result = run_module(package, dict(name='my-exporter', version='1.4.2'))
    assert result['changed'] is True
    assert result['version'] == '1.4.2'
    assert result['diff']['before']['version'] == '1.4.1'
    assert result['diff']['after']['version'] == '1.4.2'
    assert spm.calls == [['install', '-y', 'my-exporter==1.4.2']]
    assert installed(spm) == (True, '1.4.2')


def test_upgrade_does_not_pass_install_only_options(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.1')
    result = run_module(package, dict(name='my-exporter', version='1.4.2', enabled=True, owner='kube',
                                      skip_host_plugins=True))
    assert result['changed'] is True
    assert spm.calls == [['install', '-y', '--skip-host-plugins', 'my-exporter==1.4.2']]


def test_install_does_not_pass_allow_downgrade(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter', version='1.4.2', allow_downgrade=True))
    assert result['changed'] is True
    assert spm.calls == [['install', '-y', 'my-exporter==1.4.2']]


def test_upgrade_check_mode(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.1')
    result = run_module(package, dict(name='my-exporter', version='1.4.2'), check_mode=True)
    assert result['changed'] is True
    assert result['version'] == '1.4.2'
    assert spm.calls == []
    assert installed(spm) == (True, '1.4.1')


def test_version_comparison_normalises_tags(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2+build.7')
    result = run_module(package, dict(name='my-exporter', version='1.4.2_build.7'))
    assert result['changed'] is False
    assert spm.calls == []


def test_downgrade_refused_without_allow_downgrade(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', version='1.4.1'), expect_failure=True)
    assert result['msg'] == ('sonic-package-manager install my-exporter failed with rc 1: Failed to install '
                             'my-exporter==1.4.1: Request to downgrade from 1.4.2 to 1.4.1. Downgrade might be not '
                             'supported by the package')
    assert result['commands'] == ['%s install -y my-exporter==1.4.1' % spm.BIN]
    assert installed(spm) == (True, '1.4.2')


def test_downgrade_with_allow_downgrade(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', version='1.4.1', allow_downgrade=True))
    assert result['changed'] is True
    assert result['version'] == '1.4.1'
    assert spm.calls == [['install', '-y', '--allow-downgrade', 'my-exporter==1.4.1']]
    assert installed(spm) == (True, '1.4.1')


def test_non_semver_version_uses_reference_syntax(spm, run_module):
    seed_exporter(spm)
    spm.registry[REPO + ':latest'] = ('my-exporter', 'latest')
    result = run_module(package, dict(name='my-exporter', version='latest'))
    assert result['changed'] is True
    assert spm.calls == [['install', '-y', 'my-exporter@latest']]


def test_install_without_repository_fails(spm, run_module):
    result = run_module(package, dict(name='my-exporter', version='1.4.2'), expect_failure=True)
    assert result['msg'] == ('no repository named my-exporter is registered; add one with '
                             'community.sonic.package_repository or set source')
    assert spm.calls == []


def test_install_without_version_or_default_reference_fails(spm, run_module):
    seed_exporter(spm, default_reference=None)
    result = run_module(package, dict(name='my-exporter'), expect_failure=True)
    assert result['msg'] == 'repository my-exporter has no default reference; set version'
    assert spm.calls == []


def test_upgrade_built_in_fails(spm, run_module):
    result = run_module(package, dict(name='database', version='2.0.0'), expect_failure=True)
    assert result['msg'] == 'package database is built-in and cannot be upgraded'
    result = run_module(package, dict(name='database', version='1.0.0'))
    assert result['changed'] is False
    assert result['status'] == 'Built-In'


def test_manifest_requires_custom_name(spm, run_module):
    result = run_module(package, dict(name='my-exporter', manifest=True), expect_failure=True)
    assert result['msg'] == 'manifest=true requires custom_name'


def test_custom_name_and_manifest(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter', version='1.4.2', custom_name='my-exporter', manifest=True))
    assert result['changed'] is True
    assert spm.calls == [['install', '-y', '--name', 'my-exporter', '--use-local-manifest', 'my-exporter==1.4.2']]


# -- sources -------------------------------------------------------------------

def test_install_from_tarball_creates_entry(spm, run_module):
    seed_exporter(spm)
    spm.seed(dict(BUILT_IN))  # no repository entry: a tarball install does not need one
    result = run_module(package, dict(name='my-exporter', source=TARBALL))
    assert result['changed'] is True
    assert result['installed'] is True
    assert result['version'] == '1.4.2'
    assert result['repository'] == 'my-exporter'
    assert result['diff']['before'] == {'installed': False, 'version': None, 'repository': None}
    assert spm.calls == [['install', '-y', '--from-tarball', TARBALL]]
    assert installed(spm) == (True, '1.4.2')


def test_install_from_tarball_idempotent_without_version(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', source=TARBALL))
    assert result['changed'] is False
    assert spm.calls == []


def test_install_from_tarball_with_version(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', source=TARBALL, version='1.4.2'))
    assert result['changed'] is False
    result = run_module(package, dict(name='my-exporter', source='/tmp/my-exporter-1.5.0.tar', version='1.5.0'))
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == [['install', '-y', '--from-tarball', '/tmp/my-exporter-1.5.0.tar']]


def test_install_from_tarball_check_mode_without_version(spm, run_module):
    result = run_module(package, dict(name='my-exporter', source=TARBALL), check_mode=True)
    assert result['changed'] is True
    assert result['installed'] is True
    assert result['version'] is None
    assert spm.calls == []


def test_install_from_registry_reference(spm, run_module):
    seed_exporter(spm)
    spm.seed(dict(BUILT_IN))
    result = run_module(package, dict(name='my-exporter', source=REPO, version='1.4.2'))
    assert result['changed'] is True
    assert result['version'] == '1.4.2'
    assert spm.calls == [['install', '-y', '--from-repository', REPO + ':1.4.2']]


def test_install_from_missing_tarball_reports_spm_error(spm, run_module):
    result = run_module(package, dict(name='my-exporter', source='/tmp/missing.tar'), expect_failure=True)
    assert result['msg'] == ('sonic-package-manager install my-exporter failed with rc 1: Failed to install '
                             '/tmp/missing.tar: [Errno 2] No such file or directory')


# -- latest --------------------------------------------------------------------

def test_latest_uses_default_reference(spm, run_module):
    seed_exporter(spm, default_reference='1.5.0', installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', state='latest'), check_mode=True)
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == []
    result = run_module(package, dict(name='my-exporter', state='latest'))
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == [['install', '-y', 'my-exporter==1.5.0']]
    result = run_module(package, dict(name='my-exporter', state='latest'))
    assert result['changed'] is False


def test_latest_installs_when_missing(spm, run_module):
    seed_exporter(spm)
    result = run_module(package, dict(name='my-exporter', state='latest'))
    assert result['changed'] is True
    assert result['version'] == '1.4.2'
    assert spm.calls == [['install', '-y', 'my-exporter==1.4.2']]


def test_latest_queries_registry_without_default_reference(spm, run_module):
    seed_exporter(spm, default_reference=None, installed=True, version='1.4.2')
    spm.versions['my-exporter'] = ['1.4.1', '1.4.2', '1.5.0']
    result = run_module(package, dict(name='my-exporter', state='latest'))
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == [['show', 'package', 'versions', 'my-exporter', '--plain'], ['install', '-y', 'my-exporter==1.5.0']]
    assert result['commands'] == ['%s install -y my-exporter==1.5.0' % spm.BIN]


def test_latest_without_any_version_fails(spm, run_module):
    seed_exporter(spm, default_reference=None)
    spm.versions['my-exporter'] = ['latest']
    result = run_module(package, dict(name='my-exporter', state='latest'), expect_failure=True)
    assert result['msg'].startswith('cannot determine the latest version of my-exporter')
    spm.versions = {}
    result = run_module(package, dict(name='my-exporter', state='latest'), expect_failure=True)
    assert result['msg'].startswith('sonic-package-manager show package versions my-exporter failed with rc 1')


def test_latest_without_repository_fails(spm, run_module):
    result = run_module(package, dict(name='my-exporter', state='latest'), expect_failure=True)
    assert result['msg'] == ('no repository named my-exporter is registered; add one with '
                             'community.sonic.package_repository or set source')


def test_latest_from_tarball_reads_manifest(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', state='latest', source=TARBALL))
    assert result['changed'] is False
    assert spm.calls == [['show', 'package', 'manifest', '--from-tarball', TARBALL]]
    spm.calls = []
    result = run_module(package, dict(name='my-exporter', state='latest', source='/tmp/my-exporter-1.5.0.tar'))
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == [['show', 'package', 'manifest', '--from-tarball', '/tmp/my-exporter-1.5.0.tar'],
                         ['install', '-y', '--from-tarball', '/tmp/my-exporter-1.5.0.tar']]


def test_latest_from_registry_reference_reads_manifest(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', state='latest', source=REPO + ':latest'))
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == [['show', 'package', 'manifest', '--from-repository', REPO + ':latest'],
                         ['install', '-y', '--from-repository', REPO + ':latest']]


# -- uninstall -----------------------------------------------------------------

def test_uninstall(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', state='absent'))
    assert result['changed'] is True
    assert result['installed'] is False
    assert result['version'] is None
    assert result['repository'] == REPO
    assert result['status'] == 'Not Installed'
    assert result['diff'] == {
        'before': {'installed': True, 'version': '1.4.2', 'repository': REPO},
        'after': {'installed': False, 'version': None, 'repository': REPO},
    }
    assert spm.calls == [['uninstall', '-y', 'my-exporter']]
    assert installed(spm) == (False, None)
    # The repository entry stays.
    assert 'my-exporter' in spm.database()


def test_uninstall_options(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', state='absent', force=True, keep_config=True))
    assert result['changed'] is True
    assert spm.calls == [['uninstall', '-y', '--force', '--keep-config', 'my-exporter']]


def test_uninstall_check_mode(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    result = run_module(package, dict(name='my-exporter', state='absent'), check_mode=True)
    assert result['changed'] is True
    assert result['installed'] is False
    assert result['status'] == 'Not Installed'
    assert spm.calls == []
    assert installed(spm) == (True, '1.4.2')


def test_uninstall_idempotent(spm, run_module):
    seed_exporter(spm)
    for check_mode in (False, True):
        result = run_module(package, dict(name='my-exporter', state='absent'), check_mode=check_mode)
        assert result['changed'] is False
        assert result['status'] == 'Not Installed'
    # A package without any database entry is absent too.
    result = run_module(package, dict(name='unknown', state='absent'))
    assert result['changed'] is False
    assert result['installed'] is False
    assert result['repository'] is None
    assert spm.calls == []


def test_uninstall_built_in_fails(spm, run_module):
    result = run_module(package, dict(name='database', state='absent'), expect_failure=True)
    assert result['msg'] == 'package database is built-in and cannot be uninstalled'


def test_uninstall_enabled_feature_adds_hint(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    spm.fail_next = (1, 'Failed to uninstall package my-exporter: my-exporter is enabled. Disable the feature first\n')
    result = run_module(package, dict(name='my-exporter', state='absent'), expect_failure=True)
    assert result['msg'] == ('sonic-package-manager uninstall my-exporter failed with rc 1: Failed to uninstall package '
                             'my-exporter: my-exporter is enabled. Disable the feature first '
                             '(disable the feature or set force=true)')


# -- privileges and state source -----------------------------------------------

@pytest.mark.parametrize('params,action', (
    (dict(name='my-exporter', version='1.5.0'), 'install'),
    (dict(name='my-exporter', state='absent'), 'uninstall'),
))
def test_not_root_fails_with_become_hint(spm, run_module, params, action):
    seed_exporter(spm, installed=True, version='1.4.2')
    spm.euid = 1000
    result = run_module(package, params, expect_failure=True)
    assert result['msg'] == ('sonic-package-manager %s my-exporter requires root privileges; run the task with '
                             '"become: true" (or as root)' % action)
    assert spm.calls == []
    assert installed(spm) == (True, '1.4.2')


def test_not_root_can_read_state(spm, run_module):
    seed_exporter(spm, installed=True, version='1.4.2')
    spm.euid = 1000
    assert run_module(package, dict(name='my-exporter', version='1.4.2'))['changed'] is False
    assert run_module(package, dict(name='my-exporter', version='1.5.0'), check_mode=True)['changed'] is True
    assert spm.calls == []


def test_state_from_list_when_database_unreadable(spm, run_module, monkeypatch):
    seed_exporter(spm, installed=True, version='1.4.2')
    monkeypatch.setattr(package_manager, 'DATABASE_PATH', '/nonexistent/packages.json')
    result = run_module(package, dict(name='my-exporter', version='1.4.2'))
    assert result['changed'] is False
    assert result['status'] == 'Installed'
    assert spm.calls == [['list']]
    spm.calls = []
    result = run_module(package, dict(name='my-exporter', version='1.5.0'))
    assert result['changed'] is True
    assert result['version'] == '1.5.0'
    assert spm.calls == [['list'], ['install', '-y', 'my-exporter==1.5.0'], ['list']]


def test_spm_install_failure_is_reported(spm, run_module):
    seed_exporter(spm)
    spm.fail_next = (1, 'Failed to install my-exporter==1.4.2: manifest validation failed\n')
    result = run_module(package, dict(name='my-exporter', version='1.4.2'), expect_failure=True)
    assert result['msg'] == ('sonic-package-manager install my-exporter failed with rc 1: Failed to install '
                             'my-exporter==1.4.2: manifest validation failed')
    assert result['commands'] == ['%s install -y my-exporter==1.4.2' % spm.BIN]
    assert result['rc'] == 1
    assert result['stderr'].startswith('Failed to install')
    assert installed(spm) == (False, None)
