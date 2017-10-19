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
from . glow_utils import load_yaml_file

def build_template_lookup():
    label_text = "{0:25}".format("Loading template lookup")
    abs_path = os.path.abspath(settings["template"]["path"])
    template_lookup = {}

    with click.progressbar(glob.glob(abs_path), label=label_text, show_eta=False) as bar:
        for file_name in bar:
            values = load_yaml_file(file_name)
            template_lookup[values["VZ_FormID"]] = values["VZ_PK"]

    return template_lookup
