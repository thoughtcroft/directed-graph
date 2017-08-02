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
import click

from . glow_config import settings
from . glow_utils import load_file

template_lookup = {}
abs_path = os.path.abspath(settings["template"]["path"])
label_text = "{0:25}".format("Loading template lookup")

with click.progressbar(glob.glob(abs_path), label=label_text, show_eta=False) as bar:
    for file_name in bar:
        values = load_file(file_name)
        template_lookup[values["VZ_FormID"]] = values["VZ_PK"]
