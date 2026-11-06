# -*- coding: utf-8 -*-
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared plumbing for the modules that drive ``sonic-package-manager``.

The SONiC Package Manager (SPM) keeps its state in
``/var/lib/sonic-package-manager/packages.json``. :class:`PackageManager`
reads that database directly, so the modules never have to interpret SPM exit
codes, and falls back to parsing the ``sonic-package-manager list`` table
when the file cannot be read. The entries are returned as plain
dictionaries with the keys that ``sonic-package-manager list`` shows plus the
rest of the database record::

    {'name': 'my-exporter', 'repository': 'registry.example.net/sonic/my-exporter',
     'description': 'Prometheus exporter', 'default_reference': '1.4.2',
     'version': '1.4.2', 'installed': True, 'built_in': False,
     'image_id': 'sha256:...', 'docker_image_reference': '...:1.4.2',
     'status': 'Installed'}

``status`` mirrors the SPM CLI: ``Built-In``, ``Installed`` or ``Not Installed``.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import errno
import json
import os
import re

from ansible.module_utils.common.text.converters import to_native


SPM_BIN = 'sonic-package-manager'
DATABASE_PATH = '/var/lib/sonic-package-manager/packages.json'

STATUS_BUILT_IN = 'Built-In'
STATUS_INSTALLED = 'Installed'
STATUS_NOT_INSTALLED = 'Not Installed'

_LIST_HEADER = ['Name', 'Repository', 'Description', 'Version', 'Status']
_SEMVER_RE = re.compile(r'^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+_-]*)?$')


class PackageManagerError(Exception):
    """Raised for anything the modules should report with ``fail_json``.

    ``details`` holds extra keys for ``fail_json`` (``rc``, ``stdout``,
    ``stderr`` of a failed command).
    """

    def __init__(self, msg, **details):
        super(PackageManagerError, self).__init__(msg)
        self.details = details


def error_line(stdout, stderr):
    """Pick the line of a failed SPM run that explains the failure.

    SPM prints its ``Failed to ...`` message with ``click.secho`` to stdout
    while its progress logging goes to stderr, so the last ``Failed``/``Error``
    line of either stream is preferred over the last line overall.
    """
    lines = [line.strip() for line in (stdout or '').splitlines() + (stderr or '').splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith('Failed') or line.startswith('Error') or 'Error:' in line:
            return line
    return lines[-1] if lines else 'no output'


def not_root_message(action):
    return ('%s requires root privileges; run the task with "become: true" (or as root)' % action)


def package_status(entry):
    """Return the status string ``sonic-package-manager list`` shows for an entry."""
    if entry.get('built_in'):
        return STATUS_BUILT_IN
    if entry.get('installed'):
        return STATUS_INSTALLED
    return STATUS_NOT_INSTALLED


def entry_from_database(name, record):
    """Convert one ``packages.json`` record into the dictionary layout used by the modules."""
    entry = dict(
        name=name,
        repository=record.get('repository'),
        description=record.get('description') or None,
        default_reference=record.get('default-reference'),
        version=record.get('installed-version') or None,
        installed=bool(record.get('installed', False)),
        built_in=bool(record.get('built-in', False)),
        image_id=record.get('image-id'),
        docker_image_reference=record.get('docker-image-reference'),
    )
    entry['status'] = package_status(entry)
    return entry


def parse_database(content):
    """Parse the content of ``packages.json`` into ``{name: entry}``."""
    try:
        data = json.loads(content)
    except ValueError as e:
        raise PackageManagerError('%s is not valid JSON: %s' % (DATABASE_PATH, to_native(e)))
    if not isinstance(data, dict):
        raise PackageManagerError('%s does not contain a JSON object' % DATABASE_PATH)
    result = {}
    for name, record in data.items():
        if not isinstance(record, dict):
            raise PackageManagerError('%s: entry for %s is not a JSON object' % (DATABASE_PATH, name))
        result[name] = entry_from_database(name, record)
    return result


def _column_spans(ruler):
    """Return ``[(start, end), ...]`` for a tabulate ``-----  ----`` ruler line."""
    return [(m.start(), m.end()) for m in re.finditer(r'-+', ruler)]


def parse_list_output(output):
    """Parse the table printed by ``sonic-package-manager list`` into ``{name: entry}``.

    The table is produced by ``tabulate`` in its ``simple`` format: a header
    line, a ruler of dashes whose runs give the column boundaries, and one
    line per package. ``N/A`` fields become ``None``. The table does not carry
    the default reference or the image information, so those keys are ``None``.
    """
    lines = [line.rstrip('\n') for line in output.splitlines() if line.strip()]
    if len(lines) < 2:
        raise PackageManagerError('unexpected output from sonic-package-manager list: no table header')
    header, ruler = lines[0], lines[1]
    spans = _column_spans(ruler)
    columns = [header[start:end].strip() for start, end in spans]
    if columns != _LIST_HEADER:
        raise PackageManagerError('unexpected output from sonic-package-manager list: columns %r' % (columns,))
    result = {}
    for line in lines[2:]:
        fields = []
        for index, (start, end) in enumerate(spans):
            # The last column runs to the end of the line.
            stop = None if index == len(spans) - 1 else end
            fields.append(line[start:stop].strip())
        name, repository, description, version, status = fields
        entry = dict(
            name=name,
            repository=None if repository == 'N/A' else repository,
            description=None if description == 'N/A' else description,
            default_reference=None,
            version=None if version == 'N/A' else version,
            installed=status in (STATUS_INSTALLED, STATUS_BUILT_IN),
            built_in=status == STATUS_BUILT_IN,
            image_id=None,
            docker_image_reference=None,
        )
        entry['status'] = package_status(entry)
        result[name] = entry
    return result


def normalize_version(version):
    """Normalise a version or tag for comparison with the installed version.

    SPM stores the manifest version (SemVer) in the database and converts it
    to a Docker tag by replacing ``+`` with ``_``; undo that so a tag given as
    ``1.2.3_build4`` matches the installed version ``1.2.3+build4``.
    """
    if version is None:
        return None
    return str(version).strip().replace('_', '+')


def is_semver(version):
    """Return whether ``version`` is a SemVer version (``1.4.2``, ``1.4.2-rc1``, ``1.4.2+build.7``, ``1.4.2_build.7``).

    Anything else, such as a ``stable`` tag or a ``sha256:...`` digest, is a
    registry reference that has to be resolved to a manifest version before
    it can be compared with the installed version.
    """
    return version is not None and bool(_SEMVER_RE.match(normalize_version(version)))


def is_digest(reference):
    """Return whether ``reference`` is an image digest (``sha256:...``) rather than a tag."""
    return reference is not None and str(reference).strip().startswith('sha256:')


def package_expression(name, version):
    """Build the ``PACKAGE_EXPR`` argument of ``sonic-package-manager install``.

    A SemVer version is passed as ``name==version``; any other reference
    (a non-SemVer tag or a ``sha256:...`` digest) as ``name@reference``.
    Without a version the bare name installs the repository's default reference.
    """
    if version is None:
        return name
    version = str(version).strip()
    # SPM parses ``==`` with a strict SemVer parser, so a Docker tag such as
    # ``1.4.2_build7`` (``+`` replaced by ``_``) has to go through ``name@tag``.
    if _SEMVER_RE.match(version):
        return '%s==%s' % (name, version)
    return '%s@%s' % (name, version)


def is_tarball_source(source):
    """Return whether a ``source`` value names an image tarball rather than a registry reference."""
    return source.startswith(('/', './', '../')) or os.path.isfile(source)


class PackageManager(object):
    """Run ``sonic-package-manager`` and read its package database for a module."""

    def __init__(self, module, database_path=None):
        self.module = module
        self.database_path = database_path or DATABASE_PATH
        self._bin = None
        self.commands = []

    @property
    def bin(self):
        if self._bin is None:
            self._bin = self.module.get_bin_path(SPM_BIN, required=True)
        return self._bin

    def is_root(self):
        return os.geteuid() == 0

    def read_database(self):
        """Return ``{name: entry}`` from ``packages.json``, or from ``sonic-package-manager list``.

        The file is the authoritative source and carries every field. When it
        cannot be read (for example as a non-root user on a system with
        restrictive permissions) the CLI table is parsed instead.
        """
        try:
            with open(self.database_path, 'rb') as f:
                content = f.read()
        except (IOError, OSError) as e:
            if e.errno in (errno.EACCES, errno.EPERM, errno.ENOENT):
                return self.list_packages()
            raise PackageManagerError('cannot read %s: %s' % (self.database_path, to_native(e)))
        try:
            return parse_database(content.decode('utf-8'))
        except UnicodeDecodeError as e:
            raise PackageManagerError('%s is not valid UTF-8: %s' % (self.database_path, to_native(e)))

    def list_packages(self):
        """Return ``{name: entry}`` parsed from ``sonic-package-manager list``."""
        out = self.run(['list'], 'sonic-package-manager list', record=False)
        return parse_list_output(out)

    def show_manifest(self, source_args):
        """Return the manifest of a package source as a dictionary.

        ``source_args`` are the ``--from-tarball``/``--from-repository`` (or
        ``PACKAGE_EXPR``) arguments of ``sonic-package-manager show package manifest``.
        """
        out = self.run(['show', 'package', 'manifest'] + list(source_args),
                       'sonic-package-manager show package manifest', record=False)
        try:
            manifest = json.loads(out)
        except ValueError as e:
            raise PackageManagerError('could not parse the manifest printed by sonic-package-manager: %s'
                                      % to_native(e))
        if not isinstance(manifest, dict):
            raise PackageManagerError('unexpected manifest output from sonic-package-manager: not a JSON object')
        return manifest

    def run(self, args, description, record=True):
        """Run ``sonic-package-manager`` with ``args``; return stdout or raise :class:`PackageManagerError`."""
        cmd = [self.bin] + list(args)
        if record:
            self.commands.append(' '.join(cmd))
        rc, out, err = self.module.run_command(cmd)
        if rc != 0:
            raise PackageManagerError('%s failed with rc %d: %s' % (description, rc, error_line(out, err)),
                                      rc=rc, stdout=out, stderr=err)
        return out

    def run_privileged(self, args, description):
        """Like :meth:`run`, but fail with a ``become`` hint instead of letting SPM reject non-root users."""
        if not self.is_root():
            raise PackageManagerError(not_root_message(description))
        return self.run(args, description)
