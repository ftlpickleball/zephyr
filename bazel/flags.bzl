# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

def flags_from_dict(flags_dict):
    """Converts a dict of flags into a list for the platform() flags attribute

    Args:
        flags_dict: A dictionary of flags.

    Returns:
        A list of flags for the platform() flags attribute.
    """
    return ["--{}={}".format(k, v) for k, v in flags_dict.items()]
