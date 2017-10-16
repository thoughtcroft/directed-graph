#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin
# pylint: disable=invalid-name

"""Glow Navigator Config

Load settings and make available to callers
"""

# python2 and python3 portability
from __future__ import print_function

import os.path
import yaml

print("""

    Welcome to the Glow Navigator
    -----------------------------

This is a prototype exploration tool for
the relationship between formflows, pages, forms
conditions, command rules and images using a directed
graph.

Search strings are specified as regex
(see http://regex101.com for details).

For example to find:

 - anything containing 'truck'
   > truck

 - only templates containing 'truck'
   > (?=.*type: template)(?=.*truck)

 - anything with one or more parents
   > ^(?!.*counts: 0<)

You are only limited by your imagination (and regex skills)


Special commands
----------------

You vary the degree of expansion when looking at a specific
object. Entering '$$max_level=n' will stop expanding the parent or
children beyond the specified level. Default value is '1', setting to '0'
will expand all available levels.

To ignore particular types of entities when searching and expanding the graph
use the '$$ignore=foo, bar' to ignore types 'foo' and 'bar'. Just provide an
empty list to clear out the ignore list.

To include edges in matches, use the $$edges=True|False command. Default is
False to not search for matches in the edges atttached to a node.

To expand the level of detail in node printing use $$minimal=True|False. Default
is True to keep the level of detail reasonable.

To regenerate the graph afresh use $$regen. By default, if a cached copy exists
the graph will be reloaded from the cache. After being regenerated, it will be cached.

""")

settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glow_settings.yaml')

with open(settings_file, "r") as f:
    settings = yaml.safe_load(f.read())
