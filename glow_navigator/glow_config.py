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

print("Loading settings")

settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glow_settings.yaml')

with open(settings_file, "r") as f:
    settings = yaml.load(f)
