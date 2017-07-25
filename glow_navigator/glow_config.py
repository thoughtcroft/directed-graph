#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin
# pylint: disable=invalid-name

"""Glow Navigator Config

Load settings and make available to callers
"""

import os.path
import yaml

settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glow_settings.yaml')

with open(settings_file, "r") as f:
    settings = yaml.load(f)
