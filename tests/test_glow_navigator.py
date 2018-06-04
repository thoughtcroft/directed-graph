#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module

"""Glow Navigator Unit Tests
"""

import unittest
from ddt import ddt, data, unpack

from glow_navigator.glow_utils import (
    flatten,
    load_yaml_file)
from glow_navigator.glow_navigator import (
    BusinessTestParser,
    GlowObject,
    settings,
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

    @data({"active":    True,
           "entity":    "My Test Entity",
           "name":      "My Test Formflow",
           "type":      "formflow"})
    def test_value_map(self, result):
        """Returns a dictionary of mapped values
        """
        self.assertEqual(self.formflow.map(), result)

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
        self.data_parser = XMLParser(self.template.data)
        self.dep_parser = XMLParser(self.template.dependencies)

    def tearDown(self):
        self.template_data = None
        self.template = None
        self.data_parser = None
        self.dep_parser = None

@ddt
class TestTemplateControlsCase(TemplateBase):
    """Unit tests requiring full template
    """
    @data(["75152bfd-3af6-4e10-b636-ed5f5218e8ec"])
    def test_background_image(self, result):
        """Test that parsing locates background images
        """
        target = list(self.data_parser.iterfind("form"))
        images = [d["image"] for d in target if "image" in d]
        self.assertEqual(images, result)

    @data(["02b88b26-d37c-4848-8d54-5e33846d37e4"])
    def test_static_image(self, result):
        """Test that parsing locates static images
        """
        target = list(self.data_parser.iterfind("control", "SIM"))
        images = [d["image"] for d in target if "image" in d]
        self.assertEqual(images, result)

    @data(["f6f7be75-dcd7-404d-9f98-047e6465989a", "0caf614b-4da8-45c3-99fa-45135f26e641"])
    def test_tile_image(self, result):
        """Test that parsing locates tile images
        """
        target = list(self.data_parser.iterfind("control", "TIL"))
        images = [d["image"] for d in target if "image" in d]
        self.assertEqual(images, result)

    @data(['956e1bf6-27d4-4eef-8503-7e988a1a50c3', '0ead7e81-44d6-44e0-8957-3ed80c114383',
           '416d4a12-2383-4953-bc81-67f416d358ee', '5de71bd6-5703-4674-a37b-765584060655',
           '773406d0-1f65-4986-b9c7-f4e4f83c7484', 'b6dad538-b1c1-412c-a997-210508a9e878'])
    def test_(self, result):
        """Test that parsing locates formflows
        """
        target = list(self.data_parser.iterfind("control"))
        formflows = [d["formflow"] for d in target if "formflow" in d]
        self.assertEqual(flatten(formflows), result)

    @data(["http://wazza-is-awesome.com"])
    def test_tile_url(self, result):
        """Test that parsing locates url on a tile
        """
        target = list(self.data_parser.iterfind("control", "TIL"))
        urls = [d["url"] for d in target if "url" in d]
        self.assertEqual(urls, result)

    @data(['LTC_IsActive', 'LTC_ConnoteNumber', 'LTC_JobID'])
    def test_grid_columns(self, result):
        """Test that parsing locates column names on a search list
        """
        target = list(self.data_parser.search_list_properties("columns", "FieldName"))
        columns = [c for x,c in target]
        self.assertEqual(columns, result)

    @data(["LTC_Status"])
    def test_grid_filters(self, result):
        """Test that parsing locates filter names on a search list
        """
        target = list(self.data_parser.search_list_properties("filters", "PropertyPath"))
        filters = [c for x,c in target]
        self.assertEqual(filters, result)

    @data(["LTC_JobID"])
    def test_grid_sort(self, result):
        """Test that parsing locates sort fields on a search list
        """
        target = list(self.data_parser.search_list_properties("sortfields", "FieldName"))
        sortfields = [c for x,c in target]
        self.assertEqual(sortfields, result)

    @data(["e71c3d72-5976-45b9-af6f-5ccf7a227af6", "5e7b738d-21ab-428e-a10b-db44dda7f35a"])
    def test_template_dependencies(self, result):
        """Test that parsing locates template dependencies
        """
        target = list(self.dep_parser.iteritems("form"))
        templates = [d["templateID"] for d in target if "templateID" in d]
        self.assertEqual(templates, result)

    @data(["184b7395-c460-4655-89e2-fe61eb1a33e7"])
    def test_formflow_dependencies(self, result):
        """Test that parsing locates formflow dependencies
        """
        target = list(self.dep_parser.iteritems("workflow"))
        formflows = [d["workflowID"] for d in target if "workflowID" in d]
        self.assertEqual(formflows, result)

if __name__ == "__main__":
    unittest.main()
