#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin

"""Glow Navigator Utilities

Various utility functions used throught the project
"""

# python2 and python3 portability
from __future__ import print_function

# standard libraries
import os.path
import re
import uuid

# external libraries
from termcolor import colored
import yaml

from . glow_config import settings

## file related

def load_file(file_name):
    """Return YAML from required file
    """
    try:
        return yaml.load(open(file_name, "r"))
    except yaml.scanner.ScannerError as err_msg:
        print()
        print("-> Error: '{}' in {}".format(err_msg, file_name))

def raw_guid(guid):
    """Remove hyphens from string guid
    """
    return uuid.UUID(guid).hex

def full_guid(guid):
    """Format guid with hyphens
    """
    return str(uuid.UUID(guid))

def base_name(file_name):
    """Return the base name of the file
    """
    return os.path.basename(file_name).rsplit('.', 1)[0]

def glow_file_object(name):
    """Return a single glow object
    """
    if name in settings:
        return settings[name]

def glow_file_objects(omit=None):
    """Return the glow objects with files

    Ignore any objects passed in omit list
    """
    if omit is None:
        omit = []
    return (v for k, v in settings.iteritems()
            if "path" in v and not k in omit)


## Printing in color and indenting for readibility

def pindent(text, level):
    """Indent print by specified level
    """
    print("{:>3} {}{}".format(level, "  " * level, text))

def coloring(data_dict):
    """Lookup data properties to determine the best color
    """
    try:
        color = settings[data_dict["type"]]["color"]
    except KeyError:
        color = "white"
    return color

def colorized(data_dict, color=None):
    """Format and color node or edge data"""
    if color is None:
        color = coloring(data_dict)
    data = serialize(data_dict, display=True)
    return colored(data, color)


## Searching and matching using regex

def invalid_regex(expression):
    """Check for bad regex expression
    """
    result = True
    if expression:
        try:
            re.compile(r"{}".format(expression))
        except re.error:
            pass
        else:
            result = False
    return result

def match(query, g_dict):
    """Check if the regex query matches dict
    """
    s_dict = serialize(g_dict)
    pattern = r"{}".format(query)
    return re.search(pattern, s_dict, flags=re.IGNORECASE)

def serialize(g_dict, display=False):
    """Serialize a node or edge properties

    Used for searching full list or optional
    display=True for printing minimal list
    """
    if (display and "type" in g_dict and
            g_dict["type"] in settings):
        d_dict = settings[g_dict["type"]]
        g_list = ("{}: {}".format(k, g_dict[k])
                  for k in d_dict["display"]
                  if k in g_dict)
    else:
        g_list = ("{}: {}".format(k, v)
                  for (k, v) in g_dict.iteritems())
    return ", ".join(g_list)

if __name__ == "__main__":
    print()
    print("This module is only a container for utility functions")
    print()
