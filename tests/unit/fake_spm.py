# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""A fake ``sonic-package-manager`` for unit tests.

:class:`FakeSpm` stands in for ``AnsibleModule.run_command`` and
``get_bin_path``. It keeps a ``packages.json`` database file (a real file under
``tmp_path``) in the format SPM uses, renders ``sonic-package-manager list``
from it with the same ``tabulate`` layout, and applies ``repository add``,
``repository remove``, ``install`` and ``uninstall`` to the file the way SPM
would, so modules can be tested end to end without SPM or Docker.

Every command is recorded in ``calls`` (argument lists without the binary).
Set ``fail_next`` to ``(rc, stderr)`` to make the next command fail, and
``tarballs``/``registry`` to describe the sources ``install`` can read.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json


BUILT_IN = {
    'database': {
        'repository': 'docker-database',
        'description': 'SONiC database service',
        'default-reference': '1.0.0',
        'installed-version': '1.0.0',
        'installed': True,
        'built-in': True,
        'image-id': None,
        'docker-image-reference': None,
    },
}

LIST_HEADER = ['Name', 'Repository', 'Description', 'Version', 'Status']


def record(repository=None, description=None, default_reference=None, version=None,
           installed=False, built_in=False, image_id=None, docker_image_reference=None):
    """Build one ``packages.json`` record."""
    return {
        'repository': repository,
        'description': description,
        'default-reference': default_reference,
        'installed-version': version,
        'installed': installed,
        'built-in': built_in,
        'image-id': image_id,
        'docker-image-reference': docker_image_reference,
    }


def status_of(rec):
    if rec.get('built-in'):
        return 'Built-In'
    if rec.get('installed'):
        return 'Installed'
    return 'Not Installed'


def render_list(database):
    """Render ``sonic-package-manager list`` output (tabulate 'simple' format)."""
    rows = []
    for name in sorted(database):
        rec = database[name]
        rows.append([name, rec.get('repository') or 'N/A', rec.get('description') or 'N/A',
                     rec.get('installed-version') or 'N/A', status_of(rec)])
    widths = [len(h) for h in LIST_HEADER]
    for row in rows:
        widths = [max(w, len(v)) for w, v in zip(widths, row)]

    def fmt(values):
        return '  '.join(v.ljust(w) for v, w in zip(values, widths)).rstrip()

    lines = [fmt(LIST_HEADER), '  '.join('-' * w for w in widths)]
    lines += [fmt(row) for row in rows]
    return '\n'.join(lines) + '\n'


class FakeSpm(object):
    BIN = '/usr/local/bin/sonic-package-manager'

    def __init__(self, database_path):
        self.database_path = str(database_path)
        self.calls = []
        self.fail_next = None
        self.euid = 0
        # path -> (name, version, repository) for --from-tarball sources
        self.tarballs = {}
        # 'repo:tag' or 'repo@sha256:...' -> (name, version) for --from-repository sources,
        # name==version / name@reference installs and 'show package manifest'
        self.registry = {}
        # name -> list of tags returned by 'show package versions'
        self.versions = {}
        self.seed(dict(BUILT_IN))

    # -- database file -----------------------------------------------------

    def seed(self, database):
        with open(self.database_path, 'w') as f:
            json.dump(database, f, indent=4)

    def database(self):
        with open(self.database_path) as f:
            return json.load(f)

    def save(self, database):
        self.seed(database)

    # -- patched AnsibleModule methods --------------------------------------

    def get_bin_path(self, name, required=False, opt_dirs=None):
        assert name == 'sonic-package-manager'
        return self.BIN

    def run_command(self, args, **kwargs):
        assert args[0] == self.BIN, args
        args = list(args[1:])
        self.calls.append(args)
        failure = self.fail_next
        if failure is not None:
            self.fail_next = None
            return failure[0], '', failure[1]
        handler = {
            'list': self._list,
            'show': self._show,
            'repository': self._repository,
            'install': self._install,
            'uninstall': self._uninstall,
        }.get(args[0])
        if handler is None:
            raise AssertionError('unexpected sonic-package-manager command %r' % (args,))
        return handler(args[1:])

    # -- command emulation -------------------------------------------------

    def _root(self):
        if self.euid != 0:
            return 1, '', 'Root privileges required for this operation\n'
        return None

    def _list(self, args):
        assert args == []
        return 0, render_list(self.database()), ''

    @staticmethod
    def _registry_key(repository, reference):
        """The key SPM would ask the registry for: ``repo@sha256:...`` for a digest, else ``repo:tag``."""
        return '%s%s%s' % (repository, '@' if reference.startswith('sha256:') else ':', reference)

    def _resolve_expression(self, db, expression):
        """Resolve ``name``, ``name==version`` or ``name@reference`` like SPM's get_package_source."""
        if '==' in expression:
            name, reference = expression.split('==', 1)
        elif '@' in expression:
            name, reference = expression.split('@', 1)
        else:
            name, reference = expression, None
        if name not in db:
            return None, None, 'Package %s is not found in database' % name
        if reference is None:
            if db[name].get('installed'):
                return name, db[name]['installed-version'], None
            reference = db[name].get('default-reference')
            if reference is None:
                return None, None, 'No default reference tag. Please specify the version or tag explicitly'
        key = self._registry_key(db[name]['repository'], reference)
        if key not in self.registry:
            return None, None, 'Failed to retrieve manifest for %s' % key
        return self.registry[key] + (None,)

    def _show(self, args):
        if args[:2] == ['package', 'manifest'] and len(args) in (3, 4):
            if args[2] == '--from-tarball':
                name, version, repository = self.tarballs[args[3]]
            elif args[2] == '--from-repository':
                if args[3] not in self.registry:
                    return 1, 'Failed to print manifest: Failed to retrieve manifest for %s\n' % args[3], ''
                name, version = self.registry[args[3]]
            else:
                assert len(args) == 3, args
                name, version, error = self._resolve_expression(self.database(), args[2])
                if error:
                    return 1, 'Failed to print manifest: %s\n' % error, ''
            return 0, json.dumps({'package': {'name': name, 'version': version}}), ''
        if args[:2] == ['package', 'versions']:
            assert args[3:] == ['--plain']
            tags = self.versions.get(args[2])
            if tags is None:
                return 1, '', 'Failed to get package versions for %s: not found\n' % args[2]
            return 0, ''.join(t + '\n' for t in tags), ''
        raise AssertionError('unexpected show command %r' % (args,))

    def _repository(self, args):
        failure = self._root()
        if failure:
            return failure
        db = self.database()
        if args[0] == 'add':
            name, repository = args[1], args[2]
            rest = args[3:]
            rec = record(repository=repository)
            while rest:
                opt, value = rest[0], rest[1]
                rest = rest[2:]
                if opt == '--default-reference':
                    rec['default-reference'] = value
                elif opt == '--description':
                    rec['description'] = value
                else:
                    raise AssertionError('unexpected repository add option %r' % opt)
            if name in db:
                return 1, '', 'Failed to add repository %s: Package %s already exists in database\n' % (name, name)
            db[name] = rec
        elif args[0] == 'remove':
            name = args[1]
            if name not in db:
                return 1, '', 'Failed to remove repository %s: Package %s is not found in database\n' % (name, name)
            if db[name].get('built-in'):
                return 1, '', 'Failed to remove repository %s: Package %s is built-in, cannot remove it\n' % (name, name)
            if db[name].get('installed'):
                return 1, '', 'Failed to remove repository %s: Package %s is installed, uninstall it first\n' % (name, name)
            del db[name]
        else:
            raise AssertionError('unexpected repository command %r' % (args,))
        self.save(db)
        return 0, '', ''

    def _install(self, args):
        failure = self._root()
        if failure:
            return failure
        assert '-y' in args, 'install must always pass -y'
        rest = [a for a in args if a != '-y']
        flags = set()
        options = {}
        source = None
        i = 0
        while i < len(rest):
            a = rest[i]
            if a in ('--force', '--skip-host-plugins', '--enable', '--allow-downgrade', '--use-local-manifest'):
                flags.add(a)
                i += 1
            elif a in ('--set-owner', '--name'):
                options[a] = rest[i + 1]
                i += 2
            elif a in ('--from-tarball', '--from-repository'):
                options[a] = rest[i + 1]
                i += 2
            else:
                assert source is None, 'two package expressions %r' % (rest,)
                source = a
                i += 1

        db = self.database()
        if '--from-tarball' in options:
            path = options['--from-tarball']
            if path not in self.tarballs:
                return 1, '', 'Failed to install %s: [Errno 2] No such file or directory\n' % path
            name, version, repository = self.tarballs[path]
        elif '--from-repository' in options:
            ref = options['--from-repository']
            if ref not in self.registry:
                return 1, '', 'Failed to install %s: manifest unknown\n' % ref
            name, version = self.registry[ref]
            repository = ref.split('@', 1)[0].rsplit(':', 1)[0]
        else:
            assert source is not None
            name, version, error = self._resolve_expression(db, source)
            if error:
                return 1, '', 'Failed to install %s: %s\n' % (source, error)
            repository = db[name]['repository']

        rec = db.get(name) or record(repository=repository)
        if rec.get('installed'):
            # SPM's opt_check rejects options the upgrade path does not take.
            unsupported = [o for o in ('--enable', '--set-owner') if o in flags or o in options]
            if unsupported:
                return 1, '', 'Failed to install %s: Unsupported options %r for upgrade_from_source\n' % (
                    source or name, unsupported)
            if rec.get('installed-version') == version:
                return 1, '', 'Failed to install %s: %s is already installed\n' % (source or name, version)
            if version < rec['installed-version'] and '--allow-downgrade' not in flags and '--force' not in flags:
                return 1, '', ('Failed to install %s: Request to downgrade from %s to %s. Downgrade might be not '
                               'supported by the package\n' % (source or name, rec['installed-version'], version))
        elif '--allow-downgrade' in flags:
            return 1, '', ('Failed to install %s: Unsupported options [\'allow_downgrade\'] for install_from_source\n'
                           % (source or name))
        rec['repository'] = rec.get('repository') or repository
        rec['installed'] = True
        rec['installed-version'] = version
        rec['image-id'] = 'sha256:' + ('0' * 60) + version.replace('.', '')[:4]
        rec['docker-image-reference'] = '%s:%s' % (repository, version)
        db[name] = rec
        self.save(db)
        return 0, '', ''

    def _uninstall(self, args):
        failure = self._root()
        if failure:
            return failure
        assert '-y' in args, 'uninstall must always pass -y'
        name = args[-1]
        db = self.database()
        if name not in db or not db[name].get('installed'):
            return 1, '', 'Failed to uninstall package %s: %s is not installed\n' % (name, name)
        if db[name].get('built-in'):
            return 1, '', 'Failed to uninstall package %s: Cannot uninstall built-in package %s\n' % (name, name)
        db[name]['installed'] = False
        db[name]['installed-version'] = None
        db[name]['image-id'] = None
        self.save(db)
        return 0, '', ''
