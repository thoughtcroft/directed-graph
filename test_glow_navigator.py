#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Glow Navigator Unit Tests
"""

import unittest
from ddt import ddt, data, unpack

from glow_navigator import (load_file, raw_guid,
                            remove_xmlns, glow_file_objects,
                            GlowObject, XMLParser, serialize,
                            GLOW_OBJECTS, coloring, match,
                            invalid_regex, base_name)


class YAMLBase(unittest.TestCase):
    """Set up and tear down for the YAML files
    """
    def setUp(self):
        self.formflow_data = load_file("test_data/test_formflow.yaml")
        self.formflow = GlowObject(GLOW_OBJECTS["formflow"], self.formflow_data)
        self.template_data = load_file("test_data/test_template.yaml")
        self.template = GlowObject(GLOW_OBJECTS["template"], self.template_data)

    def tearDown(self):
        self.formflow_data = None
        self.formflow = None
        self.template_data = None
        self.template = None

@ddt
class YAMLTestCase(YAMLBase):
    """Unit tests requiring YAML files
    """
    @data(("guid", "tic-tac-toe"),
          ("name", "My Test Template"),
          ("type", "template"),
          ("bar", None),
          ("entity", "My Test Entity"),
          ("is_active", False))
    @unpack
    def test_template_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        value = getattr(self.template, first)
        self.assertEqual(value, second)

    @data(("type", "formflow"),
          ("guid", "foo-bar-baz"),
          ("name", "My Test Formflow"),
          ("foo", None),
          ("entity", "My Test Entity"),
          ("is_active", True))
    @unpack
    def test_formflow_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        value = getattr(self.formflow, first)
        self.assertEqual(value, second)


    @data({"name":      "My Test Formflow",
           "entity":    "My Test Entity",
           "is_active": True,
           "type":      "Formflow"})
    def test_value_map(self, result):
        """Returns a dictionary of mapped values
        """
        self.assertEqual(sorted(self.formflow.map()), sorted(result))

@ddt
class NonYAMLTestCase(unittest.TestCase):
    """Unit tests for code not dependent on YAML
    """
    @data(("1-2-3-4-5", "12345"),
          ("abc", "abc"),
          ("ab c5 / 0", "ab c5 / 0"))
    @unpack
    def test_raw_guid(self, first, second):
        """Converts string guid to plain form without hyphens
        """
        self.assertEqual(raw_guid(first), second)

    @data(("{http://schemas.microsoft.com/winfx/}UserControl", "UserControl"),
          ("no name space here", "no name space here"))
    @unpack
    def test_namespace_remover(self, first, second):
        """Extracts the xml namespace from a string
        """
        self.assertEqual(remove_xmlns(first), second)

    @data([{"name":        "Order Manager",
            "description": "Order Manager"}])
    def test_xml_handling(self, result):
        """Test that parsing a Template xml object works
        """
        with open("test_data/test_xml.xml") as xml_file:
            xml_data = xml_file.read()
        parser = XMLParser(xml_data)
        target = list(parser.iterfind("Tile"))
        self.assertEqual(target, result)

    @data(({"type": "task", "task": "JMP",
            "is_active": True, "name": "Foo",
            "formflow": "bar"},
           "name: Foo, type: task, task: JMP",
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
          ({"foo": "bar", "baz": "JMP"}, "red"))
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
          ("*", True), ("(bad", True), ("[}", True))
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

if __name__ == "__main__":
    unittest.main()
