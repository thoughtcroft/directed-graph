#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module

"""Glow Navigator Unit Tests
"""

import unittest
from ddt import ddt, data, unpack

from glow_navigator.glow_utils import load_yaml_file
from glow_navigator.glow_navigator import (
    GlowObject,
    settings,
    BusinessTestParser,
    XMLParser)


class YAMLBase(unittest.TestCase):
    """Set up and tear down for the YAML files
    """
    def setUp(self):
        self.formflow_data = load_yaml_file("tests/test_data/test_formflow.yaml")
        self.formflow = GlowObject(settings["formflow"], self.formflow_data)
        self.template_data = load_yaml_file("tests/test_data/test_template.yaml")
        self.template = GlowObject(settings["template"], self.template_data)

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
          ("active", False))
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
          ("active", True))
    @unpack
    def test_formflow_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        value = getattr(self.formflow, first)
        self.assertEqual(value, second)

    @data({"name":      "My Test Formflow",
           "entity":    "My Test Entity",
           "active": True,
           "type":      "Formflow"})
    def test_value_map(self, result):
        """Returns a dictionary of mapped values
        """
        self.assertEqual(sorted(self.formflow.map()), sorted(result))

@ddt
class NonYAMLTestCase(unittest.TestCase):
    """Unit tests for code not dependent on YAML
    """
    @data(("{http://schemas.microsoft.com/winfx/}UserControl", "UserControl"),
          ("no name space here", "no name space here"))
    @unpack
    def test_namespace_remover(self, first, second):
        """Extracts the xml namespace from a string
        """
        self.assertEqual(XMLParser.remove_xmlns(first), second)

    @data([{"name":          "Order Manager",
            "description":   "Order Manager",
            "image":         "36df2ef9-58c0-4fe7-84e0-6f68065a5f32",
            "template_name": "PO Search List"}])
    def test_xml_tile(self, result):
        """Test that parsing a Template xml object works
        """
        with open("tests/test_data/test_tile.xml") as xml_file:
            xml_data = xml_file.read()
        parser = XMLParser(xml_data)
        target = list(parser.iterfind("Tile"))
        self.assertEqual(target, result)

    @data([{"guid":           "foo-bar-baz",
            "type":           "link",
            "link_type":      "conditional task",
            "name":           "Check Status",
            "condition":      "my awesome condition"}])
    def test_xml_condition(self, result):
        """Test that parsing a Formflow xml object works
        """
        with open("tests/test_data/test_condition.xml") as xml_file:
            xml_data = xml_file.read()
        parser = XMLParser(xml_data)
        target = list(parser.iterfind("ConditionalIfActivity"))
        self.assertEqual(target, result)

    @data(("template", ["Foo", "Baz"]),
          ("formflow", ["Bar"]))
    @unpack
    def test_business_test_parser(self, match, result):
        """Test that we can find forms etc in a Business Test
        """
        matchers = settings["test"]["matchers"]
        test = BusinessTestParser("tests/test_data/business_test.feature", matchers)
        self.assertEqual(test.matches(match), set(result))

if __name__ == "__main__":
    unittest.main()
