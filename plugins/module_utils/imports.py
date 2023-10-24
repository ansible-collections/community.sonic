# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

import traceback


_fake_imports = dict()


def _set_fake_import(name, value):
    """Set a fake import, for tests only"""
    _fake_imports[name] = value


def _unset_fake_import(name):
    """Remove a fake import, for tests only"""
    del _fake_imports[name]


def get_swsscommon():
    """Get swsscommon

    Tries to import swsscommon, if succesful return (swsscommon, None).
    If the import fails, returns (None, traceback).
    """
    if 'swsscommon' in _fake_imports:
        return _fake_imports['swsscommon'], None
    try:
        from swsscommon import swsscommon
    except ImportError:
        return None, traceback.format_exc()
    return swsscommon, None
