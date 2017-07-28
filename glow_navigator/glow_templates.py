#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin
# pylint: disable=invalid-name

"""Glow Navigator Template Lookup

Create lookup for old style Page -> PK in formflows
"""

# python2 and python3 portability
from __future__ import print_function

import glob
import os.path
from . glow_config import settings
from . glow_utils import load_file

print("Loading template name lookup...")

template_lookup = {}
abs_path = os.path.abspath(settings["template"]["path"])

for file_name in glob.iglob(abs_path):
    values = load_file(file_name)
    template_lookup[values["VZ_FormID"]] = values["VZ_PK"]
