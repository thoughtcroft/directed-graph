#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
from ddt import ddt, data, unpack

from glow_navigator import *


class YAMLTestCase(unittest.TestCase):
    """Set up and tear down for the YAML files
    """
    def setUp(self):
        self.formflow_data = load_file("test_data/test_formflow.yaml")
        self.formflow = GlowObject(GLOW_OBJECTS["Formflow"], self.formflow_data)
        self.template_data = load_file("test_data/test_template.yaml")
        self.template = GlowObject(GLOW_OBJECTS["Template"], self.template_data)

    def tearDown(self):
        self.formflow_data = None
        self.formflow = None
        self.template_data = None
        self.template = None

@ddt
class BaseTestCase(YAMLTestCase):
    """Unit tests for general functions
    """
    @data(("1-2-3-4-5", "12345"), ("abc", "abc"), ("ab c5 / 0", "ab c5 / 0"))
    @unpack
    def test_raw_guid(self, first, second):
        """Converts string guid to plain form without hyphens
        """
        self.assertEqual(raw_guid(first), second)

    @data(("guid", "tic-tac-toe"), ("name", "My Test Template"),
          ("type", "Template"), ("bar", None),
          ("entity", "My Test Entity"), ("is_active", False))
    @unpack
    def test_template_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        value = getattr(self.template, first)
        self.assertEqual(value, second)

    @data(("type", "Formflow"), ("guid", "foo-bar-baz"),
          ("name", "My Test Formflow"), ("foo", None),
          ("entity", "My Test Entity"), ("is_active", True))
    @unpack
    def test_formflow_attribs(self, first, second):
        """Retrieves an attribute from parsed yaml
        """
        value = getattr(self.formflow, first)
        self.assertEqual(value, second)


    @data({"guid": "foo-bar-baz", "name": "My Test Formflow",
           "entity": "My Test Entity", "is_active": True})
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
        self.assertEqual(remove_xmlns(first), second)

    def test_glow_file_objects(self):
        """Ensure we can locate the objects with paths
        """
        target = sorted(list(glow_file_objects()))
        result = sorted([GLOW_OBJECTS["Formflow"], GLOW_OBJECTS["Template"]])
        self.assertEqual(target, result)


    @data([{'guid': 'b7a3b8ec-3bf8-469a-a52b-4df9a5f9ad99', 'name': 'Order Manager', 'description': 'Order Manager'}])
    def test_xml_handling(self, result):
        """Test that parsing a Template xml object works
        """
        with open("test_data/test_xml.xml") as file:
            xml_data = file.read()
        parser = XMLParser(xml_data)
        target = list(parser.iterfind("Tile"))
        self.assertEqual(target, result)

if __name__ == '__main__':
    unittest.main()
