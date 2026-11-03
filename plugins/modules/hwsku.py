#!/usr/bin/python
#
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = r'''
---
module: hwsku
short_description: Install and select the hardware SKU (HWSKU) of a SONiC switch
version_added: "0.4.0"
description:
  - Select the HWSKU a SONiC switch boots with, optionally installing a custom
    HWSKU directory first, and regenerate the C(PORT) table of the saved
    configuration for the new port layout.
  - The HWSKU is written to C(HWSKU=) in C(/etc/sonic/sonic-environment) and to
    C(DEVICE_METADATA.localhost.hwsku) in the saved configuration
    C(/etc/sonic/config_db.json). The running configuration database is not
    touched, so the change takes effect at the next reboot. The module never
    reboots; use RV(reboot_required) to decide when to.
  - With O(src) the directory is installed to
    C(/usr/share/sonic/device/<platform>/<name>/). The comparison is content
    based (file names, file contents and symlink targets); differences in
    mode or ownership are not reported as a change, because a false positive
    here would trigger a reboot. Files in the target directory that are not
    in O(src) are removed, so O(src) must contain the complete HWSKU.
  - When the selected HWSKU changes (in either file) or the installed HWSKU
    files change, and O(regenerate_ports) is true, the C(PORT) table is built
    from the HWSKU's C(port_config.ini) (or from the platform's
    C(platform.json) together with the HWSKU's C(hwsku.json) when there is no
    C(port_config.ini)) with C(sonic-cfggen) and replaces the C(PORT) table in
    the saved configuration. C(description) and C(admin_status) are carried
    over for port names that still exist; every other port setting (speed
    overrides, FEC, MTU, auto negotiation) is dropped because lane maps and
    port names change with the HWSKU. Re-apply them after the reboot, for
    example with M(community.sonic.interface_port).
  - Running the module with just O(name) set to the current HWSKU is a
    read-only query. It reports C(changed=false) and returns RV(platform)
    and RV(hwsku).
  - "The module needs root (C(become: true)) to write below C(/etc/sonic) and
    C(/usr/share/sonic/device)."
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
      - The HWSKU to select, that is the name of a directory under
        C(/usr/share/sonic/device/<platform>/).
      - Without O(src) the directory must already exist (a HWSKU shipped
        with the image or installed earlier).
    required: true
    type: str
  src:
    description:
      - A directory B(on the SONiC host) with the complete HWSKU
        (C(port_config.ini) or C(hwsku.json), C(sai.profile), SDK and ASIC
        configuration, buffer and QoS templates, ...). Its contents are
        installed to C(/usr/share/sonic/device/<platform>/<name>/).
      - Copy the directory to the switch first, for example with
        M(ansible.builtin.copy) or M(ansible.posix.synchronize).
      - Only file contents and symlink targets are compared; mode and
        ownership differences do not count as a change. New files are created
        with mode C(0644) (C(0755) when the source file is executable).
    type: path
  regenerate_ports:
    description:
      - Regenerate the C(PORT) table of the saved configuration from the
        HWSKU's port configuration when the HWSKU is switched or its files
        change. See the description for what is kept.
      - Set to V(false) to leave the saved C(PORT) table alone and manage it
        yourself.
    type: bool
    default: true
  backup:
    description:
      - Create a backup copy of C(/etc/sonic/config_db.json) (including a
        timestamp) before the saved configuration is rewritten.
    type: bool
    default: false
notes:
  - Other tables of the saved configuration that reference ports which no
    longer exist after the switch (C(VLAN_MEMBER), C(INTERFACE), C(ACL_TABLE),
    C(BUFFER_PG), ...) are left as they are. Clean them up before rebooting if
    the new HWSKU removes or renames ports.
  - RV(reboot_required) is also true when the running configuration database
    was booted with a different HWSKU than the one now selected, so a reboot
    that was skipped in an earlier run is still requested.
  - Dynamic port breakout (C(BREAKOUT_CFG)) is a different mechanism and is
    not handled by this module.
  - Multi-ASIC platforms are not supported.
requirements:
  - C(sonic-cfggen) on the SONiC host (part of every SONiC image).
author:
  - Christian Svensson (@bluecmd)
'''

EXAMPLES = r'''
- name: Report the current platform and HWSKU without changing anything
  community.sonic.hwsku:
    name: "{{ current_hwsku }}"
  become: true
  register: hwsku_info

- name: Select a HWSKU that ships with the image and reboot into it
  hosts: switches
  gather_facts: false
  tasks:
    - name: Select the HWSKU
      community.sonic.hwsku:
        name: Arista-7050-QX32
      become: true
      notify: Reboot into the new HWSKU

  handlers:
    - name: Reboot into the new HWSKU
      ansible.builtin.reboot:
        reboot_timeout: 900
      become: true

- name: Install and select a custom HWSKU
  hosts: switches
  gather_facts: false
  tasks:
    - name: Stage the HWSKU directory on the switch
      ansible.builtin.copy:
        src: "files/hwsku/{{ platform }}/Site-32x100G/"
        dest: /home/admin/hwsku/Site-32x100G/
        mode: preserve

    - name: Install and select the site HWSKU
      community.sonic.hwsku:
        name: Site-32x100G
        src: /home/admin/hwsku/Site-32x100G
        backup: true
      become: true
      register: hwsku

    - name: Reboot when the HWSKU changed
      ansible.builtin.reboot:
        reboot_timeout: 900
      become: true
      when: hwsku.reboot_required

- name: Switch the HWSKU but keep the saved PORT table as it is
  community.sonic.hwsku:
    name: Site-32x100G
    regenerate_ports: false
  become: true
'''

RETURN = r'''
platform:
  description: The platform identifier of the switch, as used under C(/usr/share/sonic/device/).
  type: str
  returned: always
  sample: x86_64-kvm_x86_64-r0
hwsku:
  description:
    - The HWSKU selected in C(/etc/sonic/sonic-environment) and the saved
      configuration after the module ran, that is O(name) (what a real run
      would select in check mode).
  type: str
  returned: always
  sample: Force10-S6000
previous_hwsku:
  description: The HWSKU that was selected in C(/etc/sonic/sonic-environment) before the module ran.
  type: str
  returned: always
  sample: Force10-S6000
running_hwsku:
  description:
    - The HWSKU the running configuration database was booted with, read
      with C(sonic-cfggen -d). Absent when the database could not be read.
  type: str
  returned: when available
  sample: Force10-S6000
hwsku_dir:
  description: The HWSKU directory.
  type: str
  returned: always
  sample: /usr/share/sonic/device/x86_64-kvm_x86_64-r0/Force10-S6000
reboot_required:
  description:
    - Whether a reboot is needed for the selected HWSKU to take effect, either
      because this run changed it or because the running configuration
      database still uses another HWSKU.
  type: bool
  returned: always
  sample: true
ports_regenerated:
  description: Whether the C(PORT) table of the saved configuration was (or, in check mode, would be) regenerated.
  type: bool
  returned: always
  sample: true
backup_file:
  description: Name of the backup copy of C(/etc/sonic/config_db.json).
  type: str
  returned: when O(backup=true) and the saved configuration was rewritten
  sample: /etc/sonic/config_db.json.2026-11-03@12:34:56~
diff:
  description:
    - The HWSKU in both files, the content digests of the installed HWSKU
      files when O(src) is given, and the saved C(PORT) table when it is
      regenerated, before and after the change.
  type: dict
  returned: always
  contains:
    before:
      description: The state before the change.
      type: dict
      returned: always
    after:
      description: The state after the change.
      type: dict
      returned: always
'''

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_bytes, to_native, to_text


#: Where SONiC keeps the platform directories; each contains one directory per HWSKU.
DEVICE_DIR = '/usr/share/sonic/device'
#: Environment file read at boot; carries ``PLATFORM=`` and ``HWSKU=``.
SONIC_ENVIRONMENT = '/etc/sonic/sonic-environment'
#: The saved configuration loaded into CONFIG_DB at boot.
CONFIG_DB_JSON = '/etc/sonic/config_db.json'
#: ONIE/Aboot machine description, fallback for the platform identifier.
MACHINE_CONF = '/host/machine.conf'
#: ``PORT`` fields carried over from the old table for ports that still exist.
PRESERVED_PORT_FIELDS = ('description', 'admin_status')

_ENV_LINE_RE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*?)\s*$')
_HWSKU_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+-]*$')


class HwskuError(Exception):
    """Raised for anything the module should report with ``fail_json``."""


# ---------------------------------------------------------------------------
# Pure helpers (unit tested without a host)
# ---------------------------------------------------------------------------

def validate_hwsku_name(name):
    """Make sure ``name`` can be used as a directory name under the platform directory."""
    if not name or not _HWSKU_NAME_RE.match(name) or name in ('.', '..'):
        raise HwskuError('invalid HWSKU name "%s"; expected a plain directory name such as Force10-S6000' % name)
    return name


def parse_environment(text):
    """Parse ``KEY=VALUE`` lines (sonic-environment, machine.conf) into a dictionary.

    Comments and blank lines are ignored; surrounding quotes are stripped.
    """
    values = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        m = _ENV_LINE_RE.match(line)
        if m is None:
            continue
        value = m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        values[m.group(1)] = value
    return values


def set_environment_value(text, key, value):
    """Return ``text`` with the ``KEY=`` line set to ``value``, appending the line when it is missing."""
    lines = text.splitlines(True)
    newline = '\n'
    for line in lines:
        if line.endswith('\r\n'):
            newline = '\r\n'
            break
    replaced = False
    for i, line in enumerate(lines):
        m = _ENV_LINE_RE.match(line.rstrip('\r\n'))
        if m is not None and m.group(1) == key:
            lines[i] = '%s=%s%s' % (key, value, newline)
            replaced = True
    if not replaced:
        if lines and not lines[-1].endswith(('\n', '\r\n')):
            lines[-1] += newline
        lines.append('%s=%s%s' % (key, value, newline))
    return ''.join(lines)


def merge_port_table(old, new):
    """Return ``new`` with :data:`PRESERVED_PORT_FIELDS` copied from ``old`` for ports present in both."""
    merged = {}
    for port, entry in new.items():
        entry = dict(entry)
        previous = old.get(port)
        if isinstance(previous, dict):
            for field in PRESERVED_PORT_FIELDS:
                if field in previous:
                    entry[field] = previous[field]
        merged[port] = entry
    return merged


def file_digest(path):
    """Return the hex SHA-256 digest of a file's contents."""
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def directory_manifest(root):
    """Describe the contents of a directory by content, ignoring mode and ownership.

    Returns ``{relative_path: 'sha256:<digest>' | 'symlink:<target>'}`` for every
    regular file and symlink below ``root``; ``{}`` when ``root`` does not exist.
    Directories themselves are not listed. Anything else (sockets, devices)
    raises :class:`HwskuError`.
    """
    manifest = {}
    if not os.path.isdir(root):
        return manifest
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for entry in sorted(filenames) + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            path = os.path.join(dirpath, entry)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                manifest[rel] = 'symlink:%s' % os.readlink(path)
            elif os.path.isfile(path):
                manifest[rel] = 'sha256:%s' % file_digest(path)
            else:
                raise HwskuError('cannot install %s: not a regular file or symlink' % path)
        # Do not descend into symlinked directories; they were recorded as symlinks.
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
    return manifest


def sync_directory(src, dest, src_manifest, dest_manifest):
    """Make ``dest`` contain exactly the files of ``src`` according to the two manifests.

    Files missing from ``src`` are removed from ``dest``, changed and new files
    are copied by content. Modes of existing files are left alone; new files get
    ``0644`` (``0755`` when the source is executable), new directories ``0755``.
    """
    for rel in sorted(set(dest_manifest) - set(src_manifest)):
        os.unlink(os.path.join(dest, rel))
    if not os.path.isdir(dest):
        os.makedirs(dest, 0o755)
    for rel in sorted(src_manifest):
        if dest_manifest.get(rel) == src_manifest[rel]:
            continue
        src_path = os.path.join(src, rel)
        dest_path = os.path.join(dest, rel)
        parent = os.path.dirname(dest_path)
        if not os.path.isdir(parent):
            os.makedirs(parent, 0o755)
        if os.path.isdir(dest_path) and not os.path.islink(dest_path):
            shutil.rmtree(dest_path)
        elif os.path.lexists(dest_path):
            os.unlink(dest_path)
        if os.path.islink(src_path):
            os.symlink(os.readlink(src_path), dest_path)
        else:
            shutil.copyfile(src_path, dest_path)
            mode = 0o755 if os.stat(src_path).st_mode & stat.S_IXUSR else 0o644
            os.chmod(dest_path, mode)


def port_config_arguments(hwsku_dir, platform_dir):
    """Return the ``sonic-cfggen`` arguments selecting the HWSKU's port configuration.

    ``port_config.ini`` in the HWSKU directory wins; otherwise the platform's
    ``platform.json`` is used together with the HWSKU's ``hwsku.json`` when
    present. Raises :class:`HwskuError` when neither exists.
    """
    port_config = os.path.join(hwsku_dir, 'port_config.ini')
    if os.path.isfile(port_config):
        return ['-p', port_config]
    platform_json = os.path.join(platform_dir, 'platform.json')
    if os.path.isfile(platform_json):
        args = ['-p', platform_json]
        hwsku_json = os.path.join(hwsku_dir, 'hwsku.json')
        if os.path.isfile(hwsku_json):
            args += ['-S', hwsku_json]
        return args
    raise HwskuError(
        'found neither %s nor %s; cannot regenerate the PORT table (set regenerate_ports=false to skip it)'
        % (port_config, platform_json))


# ---------------------------------------------------------------------------
# Host access
# ---------------------------------------------------------------------------

def read_text(path):
    with open(path, 'rb') as f:
        return to_text(f.read(), errors='surrogate_or_strict')


def write_text_atomically(module, path, text):
    """Write ``text`` to ``path`` through a temporary file and ``atomic_move`` so a crash never leaves a half-written file."""
    fd, tmp = tempfile.mkstemp(prefix='.%s.' % os.path.basename(path), dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(to_bytes(text, errors='surrogate_or_strict'))
        module.atomic_move(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_saved_config(path):
    if not os.path.isfile(path):
        raise HwskuError('%s does not exist; save the running configuration first (config save -y)' % path)
    try:
        with open(path, 'rb') as f:
            config = json.loads(to_text(f.read(), errors='surrogate_or_strict'))
    except ValueError as e:
        raise HwskuError('%s is not valid JSON: %s' % (path, to_native(e)))
    if not isinstance(config, dict):
        raise HwskuError('%s does not contain a JSON object' % path)
    return config


def detect_platform(environment, saved_config):
    """Find the platform identifier from sonic-environment, machine.conf or the saved configuration."""
    platform = environment.get('PLATFORM')
    if platform:
        return platform
    if os.path.isfile(MACHINE_CONF):
        machine = parse_environment(read_text(MACHINE_CONF))
        for key in ('onie_platform', 'aboot_platform'):
            if machine.get(key):
                return machine[key]
    platform = saved_config.get('DEVICE_METADATA', {}).get('localhost', {}).get('platform')
    if platform:
        return platform
    raise HwskuError('could not determine the platform from %s, %s or %s' % (SONIC_ENVIRONMENT, MACHINE_CONF, CONFIG_DB_JSON))


class Cfggen(object):
    """Runs ``sonic-cfggen`` through ``module.run_command``."""

    def __init__(self, module):
        self.module = module
        self.path = module.get_bin_path('sonic-cfggen', opt_dirs=['/usr/local/bin'], required=True)

    def running_hwsku(self):
        """The HWSKU of the running CONFIG_DB, ``None`` when the database cannot be read."""
        rc, out, dummy = self.module.run_command([self.path, '-d', '-v', 'DEVICE_METADATA.localhost.hwsku'])
        if rc != 0:
            return None
        return out.strip() or None

    def generate_port_table(self, hwsku, port_config_args):
        """Build the ``PORT`` table for ``hwsku`` from its port configuration."""
        cmd = [self.path, '-H', '-k', hwsku] + port_config_args + ['--print-data']
        rc, out, err = self.module.run_command(cmd)
        if rc != 0:
            raise HwskuError('sonic-cfggen failed to build the PORT table for HWSKU "%s": %s'
                             % (hwsku, (err or out).strip()))
        try:
            data = json.loads(out)
        except ValueError as e:
            raise HwskuError('sonic-cfggen returned invalid JSON for HWSKU "%s": %s' % (hwsku, to_native(e)))
        ports = data.get('PORT') if isinstance(data, dict) else None
        if not ports:
            raise HwskuError('sonic-cfggen produced no PORT table for HWSKU "%s" from %s' % (hwsku, port_config_args[1]))
        return ports


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

def run_module():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),
            src=dict(type='path'),
            regenerate_ports=dict(type='bool', default=True),
            backup=dict(type='bool', default=False),
        ),
        supports_check_mode=True,
    )

    name = module.params['name']
    src = module.params['src']
    regenerate_ports = module.params['regenerate_ports']

    if os.geteuid() != 0:
        module.fail_json(msg='community.sonic.hwsku needs root to write %s and %s; run it with become: true'
                             % ('/etc/sonic', DEVICE_DIR))

    try:
        result = apply_hwsku(module, name, src, regenerate_ports, module.params['backup'])
    except HwskuError as e:
        module.fail_json(msg=to_native(e))
    except (IOError, OSError) as e:
        module.fail_json(msg='%s: %s' % (getattr(e, 'filename', None) or 'I/O error', to_native(e)))
    module.exit_json(**result)


def apply_hwsku(module, name, src, regenerate_ports, backup):
    validate_hwsku_name(name)
    if src is not None and not os.path.isdir(src):
        raise HwskuError('src "%s" is not a directory on the SONiC host' % src)

    if not os.path.isfile(SONIC_ENVIRONMENT):
        raise HwskuError('%s does not exist; is this a SONiC host?' % SONIC_ENVIRONMENT)
    environment_text = read_text(SONIC_ENVIRONMENT)
    environment = parse_environment(environment_text)
    saved_config = read_saved_config(CONFIG_DB_JSON)
    metadata = saved_config.setdefault('DEVICE_METADATA', {}).setdefault('localhost', {})

    platform = detect_platform(environment, saved_config)
    platform_dir = os.path.join(DEVICE_DIR, platform)
    hwsku_dir = os.path.join(platform_dir, name)
    if not os.path.isdir(platform_dir):
        raise HwskuError('platform directory %s does not exist' % platform_dir)

    environment_hwsku = environment.get('HWSKU')
    saved_hwsku = metadata.get('hwsku')
    cfggen = Cfggen(module)
    running_hwsku = cfggen.running_hwsku()

    before = {'hwsku': saved_hwsku, 'environment_hwsku': environment_hwsku}
    after = {'hwsku': name, 'environment_hwsku': name}

    # 1. HWSKU directory
    files_changed = False
    if src is not None:
        src_manifest = directory_manifest(src)
        if not src_manifest:
            raise HwskuError('src "%s" is empty' % src)
        dest_manifest = directory_manifest(hwsku_dir)
        before['files'] = dest_manifest
        after['files'] = src_manifest
        files_changed = src_manifest != dest_manifest
    elif not os.path.isdir(hwsku_dir):
        raise HwskuError('HWSKU "%s" does not exist under %s; pass src to install it' % (name, platform_dir))

    switching = files_changed or environment_hwsku != name or saved_hwsku != name

    # 2. PORT table
    ports_regenerated = False
    new_ports = None
    if regenerate_ports and switching:
        port_config_dir = src if (src is not None and files_changed) else hwsku_dir
        new_ports = merge_port_table(saved_config.get('PORT') or {},
                                     cfggen.generate_port_table(name, port_config_arguments(port_config_dir, platform_dir)))
        before['PORT'] = saved_config.get('PORT') or {}
        after['PORT'] = new_ports
        ports_regenerated = new_ports != before['PORT']

    config_changed = saved_hwsku != name or ports_regenerated
    environment_changed = environment_hwsku != name
    changed = files_changed or config_changed or environment_changed

    result = dict(
        changed=changed,
        diff={'before': before, 'after': after},
        platform=platform,
        hwsku=name,
        previous_hwsku=environment_hwsku,
        hwsku_dir=hwsku_dir,
        ports_regenerated=ports_regenerated,
        reboot_required=changed or (running_hwsku is not None and running_hwsku != name),
    )
    if running_hwsku is not None:
        result['running_hwsku'] = running_hwsku

    if module.check_mode or not changed:
        return result

    # 3. Write, least harmful first: files, then the saved configuration, then the environment.
    if files_changed:
        sync_directory(src, hwsku_dir, src_manifest, dest_manifest)
    if config_changed:
        if backup:
            result['backup_file'] = module.backup_local(CONFIG_DB_JSON)
        metadata['hwsku'] = name
        if new_ports is not None:
            saved_config['PORT'] = new_ports
        write_text_atomically(module, CONFIG_DB_JSON, json.dumps(saved_config, indent=4) + '\n')
    if environment_changed:
        write_text_atomically(module, SONIC_ENVIRONMENT, set_environment_value(environment_text, 'HWSKU', name))
    return result


def main():
    run_module()


if __name__ == '__main__':
    main()
