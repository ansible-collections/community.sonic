# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from ansible.module_utils.common.dict_transformations import recursive_diff


def compare_entries(new, cur):
    """Compares two config db entries

    If both new and current entries are empty/None return False.
    If one of the new or the current is empty/None but not the other return True.
    If both entries have values, compare them and return True if there are any differences.
    Else return False.
    """
    # if both new and cur is empty, both current and wanted state is absent
    if not new and not cur:
        return False
    # if new XOR cur is empty current and wanted state doesn't match
    elif (not new) != (not cur):
        return True
    # diff new and cur, if they are the same recursive_diff will return None
    if not recursive_diff(new, cur) is None:
        return True
    return False
