#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module

"""Glow Navigator Utils Unit Tests
"""

import unittest
from ddt import ddt, data, unpack

from glow_navigator.glow_utils import (
    base_name,
    coloring,
    full_guid,
    glow_file_object,
    invalid_regex,
    load_yaml_file,
    match,
    raw_guid,
    serialize)


class YAMLBase(unittest.TestCase):
    """Set up and tear down for the YAML files
    """
    def setUp(self):
        self.formflow = load_yaml_file("tests/test_data/test_formflow.yaml")
        self.template = load_yaml_file("tests/test_data/test_template.yaml")

    def tearDown(self):
        self.formflow = None
        self.template = None

@ddt
class YAMLTestCase(YAMLBase):
    """Unit tests requiring YAML files
    """
    @data(("VZ_PK", "tic-tac-toe"),
          ("VZ_FormID", "My Test Template"),
          ("VZ_EntityType", "My Test Entity"),
          ("VZ_IsActive", False))
    @unpack
    def test_template_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        self.assertEqual(self.template[first], second)

    @data(("VM_PK", "foo-bar-baz"),
          ("VM_Name", "My Test Formflow"),
          ("VM_IsActive", True))
    @unpack
    def test_formflow_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        self.assertEqual(self.formflow[first], second)

@ddt
class GlowUtilTestCase(unittest.TestCase):
    """Unit tests for utility functions
    """
    @data(("484a99c5-6e16-468a-924b-e177947f390e", "484a99c56e16468a924be177947f390e"))
    @unpack
    def test_raw_guid(self, first, second):
        """Converts string guid to plain form without hyphens
        """
        self.assertEqual(raw_guid(first), second)

    @data(("484a99c56e16468a924be177947f390e", "484a99c5-6e16-468a-924b-e177947f390e"))
    @unpack
    def test_full_guid(self, first, second):
        """Converts plain guid to hyphenated string form
        """
        self.assertEqual(full_guid(first), second)

    @data(({"type": "task", "task": "JMP",
            "active": True, "name": "Foo",
            "formflow": "bar"},
            "type: task, task: JMP, name: Foo",
            "task: JMP, type: task, name: Foo"))
    @unpack
    def test_display_properties(self, first, second, third):
        """Node dictionary displays subset
        """
        result = serialize(first, display=True)
        self.assertEqual(result, second)
        self.assertNotEqual(result, third)

    @data(({"type": "formflow"}, "green"),
          ({"foo": "bar"}, "white"),
          ({"foo": "bar", "type": "image"}, "yellow"))
    @unpack
    def test_coloring_lookup(self, first, second):
        """Color is determined by dict values
        """
        self.assertEqual(coloring(first), second)

    @data(({"foo": 123, "bar": "baz", "quz": True},
           "foo: 123, bar: baz, quz: True"))
    @unpack
    def test_dict_serialization(self, first, second):
        """Dictionary is serialized correctly
        """
        self.assertEqual(serialize(first), second)

    @data(("foo: 123", True),
          ("bar: b", True),
          ("foo: bar", False),
          ("a.: .a", True))
    @unpack
    def test_match_against_dict(self, first, second):
        """Matches correctly against a dictionary"""
        my_dict = {"foo": 123, "bar": "baz", "quz": True}
        self.assertEqual(bool(match(first, my_dict)), second)

    @data((".*", False), ("bar", False), ("(?=.*test)", False),
          ("*", True), ("(bad", True), ("[}", True), ("", True))
    @unpack
    def test_regex_validation(self, first, second):
        """Test that incorrect regex strings are detected
        """
        self.assertEqual(invalid_regex(first), second)

    @data(("foo/bar/baz.exe", "baz"),
          ("foo", "foo"),
          ("foo/bar.baz.quuz", "bar.baz"))
    @unpack
    def test_base_name(self, first, second):
        """Extracts the file base name from full path
        """
        self.assertEqual(base_name(first), second)

    @data(("tile", {"type": "tile",
                    "color": "blue",
                    "display":[
                        "type", "name", "description",
                        "warning", "entity", "counts"
                        ]}))
    @unpack
    def test_glow_file_object(self, first, second):
        """Test that an object can be returned from settings
        """
        self.assertEqual(glow_file_object(first), second)

if __name__ == "__main__":
    unittest.main()
