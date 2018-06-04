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
import pickle
import re
import uuid

# external libraries
from termcolor import colored
import yaml

from . glow_config import settings

## helper functions

def flatten(l, ltypes=(list, tuple)):
    assert isinstance(l, ltypes)
    ltype = type(l)
    l = list(l)
    i = 0
    while i < len(l):
        while isinstance(l[i], ltypes):
            if not l[i]:
                l.pop(i)
                i -= 1
                break
            else:
                l[i:i+1] = l[i]
        i += 1
    return ltype(l)

## file related

def load_object_from_file(file_name):
    """Return an unmarshaled object
    """
    with open(file_name, "rb") as f:
        return pickle.load(f)

def save_object_to_file(obj, file_name):
    """Marshal object and save to file
    """
    with open(file_name, "wb") as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_yaml_file(file_name):
    """Return YAML from required file
    """
    try:
        with open(file_name, "r") as f:
            return yaml.safe_load(f.read())
    except yaml.scanner.ScannerError as err_msg:
        print("\n\n-> Error: '{}' in {}".format(err_msg, file_name))

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

def glow_file_objects(*args, **kwargs):
    """Return the glow objects with files

    If there are args then the list is restricted to
    just those. If omit is passed ignore those ones.
    """
    omit = set(kwargs.pop('omit', []))
    if args:
        include = set(args)
    else:
        include = set(settings.keys())
    candidates = include.difference(omit)
    return (v for k, v in settings.iteritems()
            if "path" in v and k in candidates)


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

def colorized(data_dict, color=None, display=True):
    """Format and color node or edge data"""
    if color is None:
        color = coloring(data_dict)
    data = serialize(data_dict, display)
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
    pattern = r"{}".format(query)
    target = serialize(g_dict)
    return re.search(pattern, target, flags=re.IGNORECASE)

def serialize(g_dict, display=False):
    """Serialize a node or edge properties

    Used for searching full list or optional
    display=True for printing minimal list
    """
    mask = '{}: {}'   # unicode for compatibility
    if (display and "type" in g_dict and
            g_dict["type"] in settings):
        d_dict = settings[g_dict["type"]]
        g_list = (mask.format(k, g_dict[k])
                  for k in d_dict["display"]
                  if k in g_dict)
    else:
        g_list = (mask.format(k, v)
                  for (k, v) in g_dict.iteritems())
    return ", ".join(g_list)

if __name__ == "__main__":
    print()
    print("This module is only a container for utility functions")
    print()
