# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

import traceback


def get_swsscommon():
    """Get swsscommon

    Tries to import swsscommon, if succesful return (swsscommon, None).
    If the import fails, returns (None, traceback).
    """
    try:
        from swsscommon import swsscommon
    except ImportError:
        return None, traceback.format_exc()
    return swsscommon, None
