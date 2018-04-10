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

    @data([{"name":          "New Incident",
            "description":   "New Incident Form",
            "image":         "74a27a16-4dc1-45d4-b5a8-916b1376be68",
            "formflow":      "ba5e37ac-b967-41e7-99de-016ddb2d1bc8"}])
    def test_xml_tile(self, result):
        """Test that parsing a Template xml object works
        """
        with open("tests/test_data/test_tile.xml") as xml_file:
            xml_data = xml_file.read()
        parser = XMLParser(xml_data)
        target = list(parser.iterfind("control", "TIL"))
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


class TemplateBase(unittest.TestCase):
    """Set up and tear down for the template tests
    """
    def setUp(self):
        self.template_data = load_yaml_file("tests/test_data/test_template_controls.yaml")
        self.template = GlowObject(settings["template"], self.template_data)
        self.parser = XMLParser(self.template.data)

    def tearDown(self):
        self.template_data = None
        self.template = None
        self.parser = None

@ddt
class TestTemplateControlsCase(TemplateBase):
    """Unit tests requiring full template
    """
    @data(["c0529c69-e509-441a-af3c-9e32fcca6471"])
    def test_background_image(self, result):
        """Test that parsing locates background images
        """
        target = list(self.parser.iterfind("form"))
        images = [d["image"] for d in target if "image" in d]
        self.assertEqual(images, result)

    @data(["02b88b26-d37c-4848-8d54-5e33846d37e4"])
    def test_static_image(self, result):
        """Test that parsing locates static images
        """
        target = list(self.parser.iterfind("control", "SIM"))
        images = [d["image"] for d in target if "image" in d]
        self.assertEqual(images, result)

    @data(["348a333c-f878-443b-a231-df4516dc5399", "e99c2aac-f827-4a95-a325-a5ea6de73b80"])
    def test_tile_image(self, result):
        """Test that parsing locates tile images
        """
        target = list(self.parser.iterfind("control", "TIL"))
        images = [d["image"] for d in target if "image" in d]
        self.assertEqual(images, result)




if __name__ == "__main__":
    unittest.main()
