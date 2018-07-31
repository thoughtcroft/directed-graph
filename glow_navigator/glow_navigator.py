#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin

"""Glow Navigator

Command line tool for exloring the relationships between
Form-flows, Templates and other objects in Glow designed apps
"""

# python2 and python3 portability
from __future__ import print_function
from builtins import input

# standard libraries
import copy
import glob
import os.path
import re
try:
    import readline                 # pylint: disable=unused-import
except ImportError:
    import pyreadline as readline   # pylint: disable=unused-import
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
import time
import xml.etree.ElementTree as ET

# external libraries
import click
import networkx as nx
from colorama import init

from . glow_config import settings
from . glow_utils import (
    base_name,
    colorized,
    full_guid,
    glow_file_object,
    glow_file_objects,
    invalid_regex,
    load_yaml_file,
    load_object_from_file,
    save_object_to_file,
    match,
    pindent)

COMMAND_LOOKUP = {}
FORMSTEP_LOOKUP = {}
FORMFLOW_LOOKUP = {}
MODULE_LOOKUP = {}
MAX_LEVEL = 1
IGNORE_TYPES = []
EDGE_MATCH = False
MINIMAL_DISPLAY = True
CACHE_FILE = os.path.abspath("glow_graph.pickle")
GLOW_GRAPH = None


class GlowObject(object):
    # pylint: disable=too-few-public-methods
    """Glow Object class

    Represents various objects available in Glow.
    A field mapping provides a friendly and object
    neutral way to access various values passed
    in from the YAML definition
    """
    def __init__(self, mapping, values):
        self.type = mapping["type"]
        self.fields = mapping["fields"]
        self.values = values

    def __getattr__(self, attr):
        """Provide value lookup as attributes

        Allows value dict items to be accessed as
        properties e.g. {"foo": "bar"} can be
        accessed as my_obj.foo.

        Also uses the friendly mapping such that
        if "foo" is mapped to "baz" then we can
        call my_obj.baz to obtain "bar"
        """
        field = attr
        if attr in self.fields:
            field = self.fields[attr]
        if field in self.values:
            result = self.values[field]
            if attr == "guid":
                result = result.lower()
            return result

    def map(self):
        """Return a dict of values mapped to fields

        Returns a limited subset of values: those that
        have keys mapped in the fields dictionary
        """
        noisy_attributes = (
            "data", "guid", "tasks",
            "dependencies", "properties"
        )
        mapping = {k : self.values[v]
                   for k, v in self.fields.iteritems()
                   if v in self.values}
        mapping["type"] = self.type
        for attr in noisy_attributes:
            mapping.pop(attr, None)
        return mapping


class BusinessTestParser(object):
    """Glow Business Test parser for locating object references
    """

    def __init__(self, file_name, matchers):
        self.name = base_name(file_name)
        self.matchers = matchers
        with open(file_name, "r") as f:
            self.content = f.read()

    def matches(self, matcher):
        """Return unique hits on matcher
        """
        results = set()
        if matcher in self.matchers:
            for regex in self.matchers[matcher]:
                pattern = r"{}".format(regex)
                for m in re.finditer(pattern, self.content):
                    results.add(m.group(matcher).rstrip())
        return results

    def map(self):
        """Return attributes for adding to graph
        """
        return {"name": self.name, "type": "test"}


class XMLParser(object):
    """Glow Template XML parser
    """

    def __init__(self, xml):
        self.tree = ET.fromstring(xml.encode(encoding='utf-8'))

    def iterfind(self, tag, code=None):
        """Generator for elements matching tag with code

        Find nodes with tag of type code and return an
        appropriate data structure (varies by tag)
        """
        for node in self.tree.iter():
            if self.remove_xmlns(node.tag) == tag:
                if code is None or ("code" in node.attrib and node.attrib["code"] == code):
                    yield self._data(node, tag)

    def iteritems(self, tag):
        """Generator for obtaining attributes of elements matching tag
        """
        for node in self.tree.iter():
            if self.remove_xmlns(node.tag) == tag:
                yield node.attrib

    def properties_by_name(self, name):
        """Return a dict of property dicts from all elements
        """
        result_set = {}
        for n_dict in self.iterfind("placeholder"):
            if n_dict and name in n_dict:
                field = n_dict[name]
                n_dict.update(result_set.get(field, {}))
                result_set[field] = n_dict
        return result_set

    def search_list_properties(self, list_type, prop_type):
        """Return properties referenced in search lists
        """
        result_set = set()
        for n_dict in self.iterfind("control", "SRL"):
            if list_type in n_dict:
                search_list = n_dict.get("search_list")
                my_xml = XMLParser(n_dict[list_type])
                for my_node in my_xml.tree.iter():
                    if self.remove_xmlns(my_node.tag) == prop_type:
                        result_set.add((search_list, my_node.text))
        return result_set

    def _data(self, node, tag):
        """Generate the object according to tag
        """
        if tag in ("control", "form", "placeholder"):
            return self._ph_dict(node)
        if tag in ("ConditionalIfActivity", "ConditionalWhileActivity", "NativeTransitionInfo"):
            return self._condition_dict(node)
        if tag == "ShowFormActivity":
            return self._template_dict(node)
        if tag == "JumpToActivity":
            return self._formflow_dict(node)
        if tag == "RunCommandActivity":
            return self._command_dict(node)
        if tag == "PlayAudioActivity":
            return self._sound_dict(node)
        if tag == "Grid":
            return self._grid_dict(node)
        if tag in ("calculatedProperty", "simpleConditionExpression"):
            return self._prop_dict(node)

    def _ph_dict(self, node, ph_name="placeholder"):
        """Create the dictionary of placeholders

        The nodes placeholder element attributes
        are remapped using the topics dict. Each
        {name: topic, value: amount} is turned into
        {topic: amount} if value has been set
        """
        topics = {
            "BackgroundImagePk":          "image",
            "BindingPath":                "property",
            "CaptionOverride":            "caption",
            "ColumnDefinitions":          "columns",
            "CommandRule":                "command",
            "DefaultFilter":              "filters",
            "DefaultSortFields":          "sortfields",
            "Description":                "description",
            "EntityType":                 "entity",
            "FilterType":                 "search_list",
            "FormFlowPKForFoundItem":     "formflow",
            "FormFlowPKForNewItem":       "formflow",
            "FormFlowPKForNoItem":        "formflow",
            "FormFlowPKForMultipleItems": "formflow",
            "Image":                      "image",
            "ItemTemplateID":             "component",
            "Link":                       "property",
            "NewWorkflow":                "formflow",
            "PagePK":                     "template",
            "SingleResultFormFlow":       "formflow",
            "TemplateID":                 "component",
            "Text":                       "name",
            "Url":                        "url",
            "VisibilityCondition":        "condition",
            "Workflow":                   "formflow"
            }

        ph_dict = self._convert_dict(node, ph_name)
        return self.build_dict(ph_dict, topics)

    def _grid_dict(self, node):
        """Create the dictionary of the form Grid

        Need to get to the last element and
        then return our normal placeholder dictionary
        """
        g_dict = {}
        if list(node):
            g_dict = self._ph_dict(node[-1])
        return g_dict

    def _formflow_dict(self, node):
        """Create the dictionary of the Jump To

        The JumpToActivity element refers to the formflow
        """
        topics = {
            "ResKey":                   "guid",
            "DisplayName":              "name",
            "WorkflowTemplatePK":       "formflow"
            }

        f_dict = self.build_dict(node.attrib, topics)
        f_dict["type"] = "link"
        f_dict["link_type"] = "jump to formflow task"
        return f_dict

    def _template_dict(self, node):
        """Create the dictionary of the Show Form

        The ShowFormActivity element refers to the template
        """
        topics = {
            "ResKey":       "guid",
            "DisplayName":  "name",
            "FormPK":       "template"
            }

        t_dict = self.build_dict(node.attrib, topics)
        t_dict["type"] = "link"
        t_dict["link_type"] = "show form task"
        return t_dict

    def _condition_dict(self, node):
        """Create the dictionary of the Condition

        The ConditionalIfActivity, ConditionalWhileActivity,
        NativeTransitionInfo elements refer to conditions
        """
        topics = {
            "ResKey":            "guid",
            "DisplayName":       "name",
            "SelectedCondition": "condition",
            "ConditionPK":       "condition",
            "x:Key":             "name"
            }

        c_dict = self.build_dict(node.attrib, topics)
        if c_dict["condition"] == "{x:Null}":
            c_dict = None
        else:
            c_dict["type"] = "link"
            c_dict["link_type"] = "conditional task"
        return c_dict

    def _command_dict(self, node):
        """Create the dictionary of the Command

        The RunCommandActivity element refers to the command
        """
        topics = {
            "ResKey":       "guid",
            "DisplayName":  "name",
            "RuleName":     "command"
            }

        c_dict = self.build_dict(node.attrib, topics)
        c_dict["type"] = "link"
        c_dict["link_type"] = "run command task"
        return c_dict

    def _sound_dict(self, node):
        """Create the dictionary of the Sound

        The PlayAudioActivity element refers to the sound
        """
        topics = {
            "ResKey":       "guid",
            "DisplayName":  "name",
            "AudioPK":      "sound"
            }

        s_dict = self.build_dict(node.attrib, topics)
        s_dict["type"] = "link"
        s_dict["link_type"] = "play sound task"
        return s_dict

    def _form_dict(self, node):
        """Create the dictionary for form dependent link
        """
        topics = {
            "BackgroundImagePk": "image",
            "path":              "property",
            "templateID":        "template",
            "templatePK":        "template",
            "workflowID":        "formflow"
            }

        f_dict = self.build_dict(node.attrib, topics)
        f_dict["type"] = "link"
        f_dict["link_type"] = "form dependency"
        return f_dict

    def _prop_dict(self, node):
        """Create the dictionary for property dependent link
        """
        topics = {
            "path":         "property",
            "propertypath": "property"
            }

        p_dict = self.build_dict(node.attrib, topics)
        p_dict["type"] = "link"
        p_dict["link_type"] = "property dependency"
        return p_dict

    def _convert_dict(self, node, tag):
        """Convert names/value pairs to dict

        Converts name:foo, value:bar into foo:bar
        """
        def convert_elem(e_dict):
            if "value" in e_dict and e_dict["value"]:
                p_dict[e_dict["name"]] = e_dict["value"]
            if "Value" in e_dict and e_dict["Value"]:
                p_dict[e_dict["Name"]] = e_dict["Value"]

        p_dict = {}
        if node.getchildren():
            for elem in node.getchildren():
                if self.remove_xmlns(elem.tag) == tag:
                    convert_elem(elem.attrib)
        else:
            convert_elem(node.attrib)
        return p_dict

    @staticmethod
    def build_dict(attrib, topics):
        """Build a dictionary of topics using attributes

        If there is more than one attribute, return a list
        """
        result = {}
        for key, field in topics.iteritems():
            if key in attrib:
                try:
                    result[field].append(attrib[key])
                except AttributeError:
                    result[field] = [result[field], attrib[key]]
                except KeyError:
                    result[field] = attrib[key]
        return result

    @staticmethod
    def remove_xmlns(text):
        """Strip out any xmlns from xml tag
        """
        return re.sub(r"\{.*\}", "", text)

def print_graph_info(graph):
    """Output stats about the graph
    """
    print(nx.info(graph))
    if graph.number_of_nodes() == 0:
        print("Nothing was added to the graph - run again in the Glow source root\n")
        sys.exit()
    missing_nodes(graph)

def create_graph():
    """Create directed graph of objects

    Each Glow object is added as a node
    to the graph and references are added
    as edges from caller to callee
    """
    def process_glow_object():
        """Handle the type of object that we are parsing
        """
        if glow_object.type == "entity":
            add_entity_to_graph(graph, glow_object, file_name)
        elif glow_object.type == "index":
            add_index_to_graph(graph, glow_object, file_name)
        elif glow_object.type == "metadata":
            add_metadata_to_graph(graph, glow_object, file_name)
        elif glow_object.type == "condition":
            add_condition_to_graph(graph, glow_object, file_name)
        elif glow_object.type == "formflow":
            add_formflow_to_graph(graph, glow_object)
        elif glow_object.type in  ("image", "sound"):
            graph.add_node(glow_object.guid, glow_object.map())
        elif glow_object.type == "module":
            add_module_to_graph(graph, glow_object)
        elif glow_object.type == "template":
            add_template_to_graph(graph, glow_object)

    start_time = time.time()
    graph = nx.MultiDiGraph(name="Glow")

    load_list = ["entity", "metadata", "index", "image", "sound"]
    omit_list = load_list + ["test"]

    # add entity related stuff first so the command dict is available
    for attrs in (glow_file_object(x) for x in load_list):
        abs_path = os.path.abspath(attrs["path"])
        label_text = "{0:25}".format("Loading {} list".format(attrs["type"]))
        with click.progressbar(
            glob.glob(abs_path),
            label=label_text,
            show_eta=False) as progress_bar:
            for file_name in progress_bar:
                values = load_yaml_file(file_name)
                if not values:
                    continue
                glow_object = GlowObject(attrs, values)
                process_glow_object()

    print()
    for attrs in glow_file_objects(omit=omit_list):
        abs_path = os.path.abspath(attrs["path"])
        label_text = "{0:25}".format("Analysing {}s".format(attrs["type"]))
        with click.progressbar(
            glob.glob(abs_path),
            label=label_text,
            show_eta=False) as progress_bar:
            for file_name in progress_bar:
                values = load_yaml_file(file_name)
                if not values:
                    continue
                glow_object = GlowObject(attrs, values)
                process_glow_object()

    # finally add test which are not yaml and need their own parsing strategy
    # also now in their own special folder which has to be computed from current
    attrs = settings["test"]
    abs_path = os.path.abspath(attrs["path"]).replace("Platform Builder", "BusinessTests")
    label_text = "{0:25}".format("Analysing {}s".format(attrs["type"]))
    with click.progressbar(
        glob.glob(abs_path),
        label=label_text,
        show_eta=False) as progress_bar:
        for file_name in progress_bar:
            test = BusinessTestParser(file_name, attrs["matchers"])
            if not test.matches("ignore"):
                graph.add_node(test.name, test.map())
                for module in test.matches("module"):
                    graph.add_edge(
                        test.name,
                        MODULE_LOOKUP.get(module, module),
                        attr_dict={
                            "type":      "link",
                            "link_type": "business test",
                            "ref_type":  "module",
                            "name":      module
                        })
                for template in test.matches("template"):
                    graph.add_edge(
                        test.name,
                        FORMSTEP_LOOKUP.get(template, template),
                        attr_dict={
                            "type":      "link",
                            "link_type": "business test",
                            "ref_type":  "template",
                            "name":      template
                        })
                for formflow in test.matches("formflow"):
                    graph.add_edge(
                        test.name,
                        FORMFLOW_LOOKUP.get(formflow, formflow),
                        attr_dict={
                            "type":      "link",
                            "link_type": "business test",
                            "ref_type":  "formflow",
                            "name":      formflow
                        })
    end_time = time.time()
    elapsed_time = round(end_time - start_time)
    print("\nGraph completed in {} seconds\n".format(elapsed_time))
    save_object_to_file(graph, CACHE_FILE)
    return graph

def fix_entity_name(entity, file_name):
    """Correct for missing entity name
    """
    field = entity.fields["name"]
    entity.name = base_name(file_name)
    entity.values[field] = entity.name

def add_metadata_to_graph(graph, metadata, file_name):
    """Add additional entity metadata and edges to the graph
    """
    if not metadata.name:
        fix_entity_name(metadata, file_name)
    graph.add_node(
        metadata.name,
        {
            "name": metadata.name,
            "type": "entity",
            "entity": metadata.name
        })

    if metadata.data:
        data = metadata.data
        rdo_fld = metadata.fields["read_only"]
        con_fld = metadata.fields["condition"]
        if (rdo_fld in data and
                isinstance(data[rdo_fld], dict) and
                con_fld in data[rdo_fld]):
            graph.add_edge(
                metadata.name,
                data[rdo_fld][con_fld].lower(),
                attr_dict={
                    "type":      "link",
                    "link_type": "entity read only condition",
                })
        if "icon" in data:
            graph.add_edge(
                metadata.name,
                data["icon"].lower(),
                attr_dict={
                    "type":      "link",
                    "link_type": "entity icon",
                })

    if metadata.properties:
        topics = {
            "aggregateMode": "method",
            "name":          "name",
            "propertyPath":  "property",
            "conditionId":   "condition"
            }
        for name, attrs in metadata.properties.iteritems():
            reference = "{}-{}".format(name, metadata.name)
            graph.add_node(
                reference,
                {
                    "name":   name,
                    "type":   "property",
                    "entity": metadata.name
                })
            for prop in attrs.get("collectionAggregate", []):
                pc_dict = XMLParser.build_dict(prop, topics)
                pc_dict["name"] = pc_dict.get("name", "").replace(" ", "")
                pc_dict["type"] = "property"
                pc_dict["calculated_property"] = "Aggregate{}".format(pc_dict["method"])
                pc_dict["entity"] = metadata.name
                if "property" in pc_dict:
                    pty = "{}.{}".format(name, pc_dict["property"])
                    pc_dict["property"] = pty
                prop_name = "{}-{}".format(pc_dict["name"], metadata.name)
                graph.add_node(prop_name, attr_dict=pc_dict)
                pl_dict = {
                    "type":      "link",
                    "link_type": "aggregate rule"
                    }
                graph.add_edge(reference, prop_name, attr_dict=pl_dict)
                if "condition" in pc_dict:
                    graph.add_edge(prop_name, pc_dict["condition"].lower(), attr_dict=pl_dict)

def add_formflow_to_graph(graph, formflow):
    """Add a formflow object and its edges to the graph

    Also iterates through tasks (formflow steps) and
    adds form displays, formflow jump, run command rules
    as well as any referenced conditions
    """
    graph.add_node(formflow.guid, formflow.map())
    FORMFLOW_LOOKUP[formflow.name] = formflow.guid

    if formflow.entity:
        f_dict = {
            "type": "link",
            "link_type": "formflow entity"
        }
        graph.add_edge(formflow.entity, formflow.guid, attr_dict=f_dict)

    if formflow.image:
        i_dict = {
            "type": "link",
            "link_type": "formflow icon"
        }
        graph.add_edge(formflow.guid, formflow.image.lower(), attr_dict=i_dict)

    if formflow.conditions:
        for condition in formflow.conditions:
            c_dict = {
                "type":             "link",
                "link_type":        "formflow condition",
                "condition":        condition["VWT_ConditionId"].lower(),
                "guid":             condition["VWT_PK"].lower()
            }
            graph.add_edge(formflow.guid, c_dict["condition"], attr_dict=c_dict)

    if formflow.tasks:
        for task in formflow.tasks:
            go_task = GlowObject(settings["task"], task)
            add_task_edge_to_graph(graph, formflow, go_task)

    if formflow.data:
        xml_parser = XMLParser(formflow.data)
        for template in xml_parser.iterfind("ShowFormActivity"):
            template_id = template["template"].lower()
            FORMSTEP_LOOKUP[template["name"]] = template_id
            graph.add_edge(formflow.guid, template_id, attr_dict=template)
        for ff in xml_parser.iterfind("JumpToActivity"):
            graph.add_edge(formflow.guid, ff["formflow"].lower(), attr_dict=ff)
        for condition_type in ("ConditionalIfActivity", "ConditionalWhileActivity", "NativeTransitionInfo"):
            for condition in xml_parser.iterfind(condition_type):
                if condition:
                    graph.add_edge(formflow.guid, condition["condition"].lower(), attr_dict=condition)
        for sound in xml_parser.iterfind("PlayAudioActivity"):
            graph.add_edge(formflow.guid, sound["sound"].lower(), attr_dict=sound)
        for command in xml_parser.iterfind("RunCommandActivity"):
            command_name = command["command"]
            entity = get_command_entity(command_name, formflow.entity)
            command_full_name = "{}-{}".format(command_name, entity)
            graph.add_edge(formflow.guid, command_full_name, attr_dict=command)

def add_task_edge_to_graph(graph, formflow, task):
    """Add an edge to the graph from a task object
    """
    if task.task == "FRM" and task.template:
        graph.add_edge(formflow.guid, task.template.lower(), attr_dict=task.map())
        FORMSTEP_LOOKUP[task.name] = task.template.lower()
    elif task.task == "JMP" and task.formflow:
        graph.add_edge(formflow.guid, task.formflow.lower(), attr_dict=task.map())
    elif task.task == "RUN" and task.command:
        entity = get_command_entity(task.command, formflow.entity)
        command = "{}-{}".format(task.command, entity)
        graph.add_edge(formflow.guid, command, attr_dict=task.map())

def add_condition_to_graph(graph, condition, file_name):
    """Add a condition object to the graph
    """
    guid = full_guid(base_name(file_name))
    graph.add_node(guid, condition.map())
    if condition.expression:
        xml_parser = XMLParser(condition.expression)
        properties = {}
        for prop in xml_parser.iterfind("simpleConditionExpression"):
            reference = "{}-{}".format(prop["property"], condition.entity)
            properties[reference] = prop
        for prop, attrs in properties.iteritems():
            add_property_edge_if_exists(graph, guid, prop, attrs)

def add_index_to_graph(graph, entity, file_name):
    """Add an entity index object to the graph
    """
    topics = {
        "name":           "name",
        "propertyPath":   "property",
        "keyField":       "show_in_results",
        "trackingCommon": "trackable",
        "searchable":     "searchable",
        "common":         "quick_search",
        "where":          "conditional"
    }

    i_dict = {
        "type": "link",
        "link_type": "index"
    }

    entity_name = base_name(file_name)
    if entity.mappings:
        for field in entity.mappings:
            index = XMLParser.build_dict(field, topics)
            index["entity"] = entity_name
            index["type"] = "index"
            index_name = index["name"].upper()
            graph.add_node(index_name, {"type": "index", "name": index["name"]})
            graph.add_edge(entity_name, index_name, attr_dict=index)
            if "property" in index:
                prop_ref = "{}-{}".format(index["property"], entity_name)
                add_property_edge_if_exists(graph, index_name, prop_ref, i_dict)

def add_module_to_graph(graph, module):
    """Add a module object and its edges to the graph
    """
    graph.add_node(module.guid, module.map())
    if module.template:
        m_dict = {
            "type":       "link",
            "link_type":  "module",
            "name":       "Landing Page",
            "template":   module.template
        }
        graph.add_edge(module.guid, module.template.lower(), attr_dict=m_dict)
        MODULE_LOOKUP[module.code] = module.guid

def add_template_to_graph(graph, template):
    """Add a template object and its edges to the graph

    Iterates through any tiles on the template and
    adds the relevant link as an edge. Also looks for
    additional references in the dependencies
    """
    def analyse_images():
        """Find all the image references and create edges
        """
        for image in xml_parser.iterfind("control", "SIM"):
            if "image" in image:
                image["type"] = "link"
                image["link_type"] = "static image"
                graph.add_edge(template.guid, image["image"].lower(), attr_dict=image)

        for image in xml_parser.iterfind("form"):
            if "image" in image:
                image["type"] = "link"
                image["link_type"] = "background image"
                graph.add_edge(template.guid, image["image"].lower(), attr_dict=image)

    def analyse_tiles():
        """Find all the tiles and creates edges to the objects they reference
        """
        for tile in xml_parser.iterfind("control", "TIL"):
            tile["type"] = "tile"
            if not "entity" in tile and template.entity:
                tile["entity"] = template.entity
            if "template" in tile:
                graph.add_edge(template.guid, tile["template"].lower(), attr_dict=tile)
            if "formflow" in tile:
                graph.add_edge(template.guid, tile["formflow"].lower(), attr_dict=tile)
            if "command" in tile:
                entity = get_command_entity(tile["command"], tile["entity"])
                command = "{}-{}".format(tile["command"], entity)
                graph.add_edge(template.guid, command, attr_dict=tile)
            if "image" in tile:
                graph.add_edge(template.guid, tile["image"].lower(), attr_dict=tile)
            if "property" in tile:
                reference = "{}-{}".format(tile["property"], template.entity)
                add_property_edge_if_exists(graph, template.guid, reference, tile)

    # main template processing
    FORMSTEP_LOOKUP[template.name] = template.guid
    graph.add_node(template.guid, template.map())

    if template.data:
        xml_parser = XMLParser(template.data)
        analyse_images()
        analyse_tiles()

        for component, comp_dict in xml_parser.properties_by_name("component").iteritems():
            comp_dict.update({
                "type":      "link",
                "link_type": "component template"
            })
            graph.add_edge(template.guid, component.lower(), attr_dict=comp_dict)

        for prop, prop_dict in xml_parser.properties_by_name("property").iteritems():
            reference = "{}-{}".format(prop, template.entity)
            prop_dict.update({
                "type":      "link",
                "link_type": "bound property"
            })
            add_property_edge_if_exists(graph, template.guid, reference, prop_dict)

        cap_link = {
            "type":      "link",
            "link_type": "caption override"
        }
        for caption, cap_dict in xml_parser.properties_by_name("caption").iteritems():
            cap_dict.update({
                "name": caption,
                "type": "caption"
            })
            prop = cap_dict.get("property")
            cap_ref = "{}-{}".format(caption, prop)
            graph.add_node(cap_ref, cap_dict)
            graph.add_edge(template.guid, cap_ref, attr_dict=cap_link)
            if prop:
                prop_ref = "{}-{}".format(prop, template.entity)
                add_property_edge_if_exists(graph, template.guid, prop_ref, cap_link)
                add_property_edge_if_exists(graph, cap_ref, prop_ref, cap_link)

        cd_dict = {
            "type":      "link",
            "link_type": "column definition"
        }
        for search_list, prop in xml_parser.search_list_properties("columns", "FieldName"):
            if search_list == "Global":
                index_name = prop.upper()
                graph.add_node(index_name)
                graph.add_edge(template.guid, index_name, attr_dict=cd_dict)
            else:
                reference = "{}-{}".format(prop, template.entity)
                add_property_edge_if_exists(graph, template.guid, reference, cd_dict)

def add_property_edge_if_exists(graph, parent, prop, attrs):
    """Conditionally add reference to property if exists

    Also deconstruct property name when checking so that
    'entity.collection.prop' checks against 'prop'
    """
    base_prop = prop.rsplit(".")[-1]
    name_prop = base_prop.rsplit("-")[0]
    if graph.has_node(base_prop):
        graph.add_edge(parent, base_prop, attr_dict=attrs)
    else:
        query = "name: {}".format(name_prop)
        nodes = select_nodes(graph, query)
        if len(nodes) == 1:
            graph.add_edge(parent, nodes[0][0], attr_dict=attrs)


def add_entity_to_graph(graph, entity, file_name):
    """Add entity level information to the graph

    - adds Command Rules based on 'name' as 'guid'
      is not used by referrers.
    - creates COMMAND_LOOKUP to handle entity
      command inheritance
    - adds calculated properties
    - looks for conditions referenced in rules
    """
    def rule_details(rule):
        rule_type = r_dict["rule_type"]
        p_dict[rule_types[rule_type]] = rule["rule_name"]
        e_dict = {
            "name":      name,
            "entity":    entity.name,
            "type":      "link",
            "link_type": rule_types[rule_type],
            "rule_name": rule["rule_name"]
            }
        graph.add_edge(entity.name, reference, attr_dict=e_dict)
        if "conditions" in rule:
            for condition in rule["conditions"]:
                graph.add_edge(reference, condition.lower(), attr_dict=e_dict)

    topics = {
        "conditionIds": "conditions",
        "methodName":   "rule_name",
        "ruleId":       "guid",
        "ruleMappings": "rule_set",
        "ruleType":     "rule_type"
        }

    rule_types = {
        "CMD": "command",
        "PRP": "calculated_property",
        "PRO": "defaulting_rule",
        "VAL": "validation_rule",
        "LOO": "lookup_rule"
        }

    if not entity.name:
        fix_entity_name(entity, file_name)
    graph.add_node(entity.name, entity.map())

    if entity.properties:
        for name, rules in entity.properties.iteritems():
            reference = "{}-{}".format(name, entity.name)
            p_dict = {
                "name":   name,
                "entity": entity.name,
                "type":   "property"
            }
            for rule in rules:
                r_dict = XMLParser.build_dict(rule, topics)
                r_dict["name"] = name
                r_dict["entity"] = entity.name
                rule_type = r_dict["rule_type"]
                if rule_type == "CMD":
                    add_to_command_lookup(name, entity.name)
                elif "rule_set" in r_dict:
                    for rule_set in r_dict["rule_set"]:
                        rs_dict = XMLParser.build_dict(rule_set, topics)
                        rule_details(rs_dict)
                else:
                    rule_details(r_dict)
            graph.add_node(reference, p_dict)

def add_to_command_lookup(command, entity):
    """Add discovered command to lookup
    """
    commands = COMMAND_LOOKUP
    if command in commands:
        commands[command].append(entity)
    else:
        commands[command] = [entity]

def get_command_entity(command, entity):
    """Get the best command node name
    """
    result = entity
    commands = COMMAND_LOOKUP
    if command in commands:
        if not entity in commands[command]:
            result = commands[command][0]
    return result

def missing_nodes(graph):
    """Return data on nodes without data

    Indicates those nodes referenced in edges but which
    had were not added from files so represent orphan
    references from within other objects
    """
    print()
    print("These nodes have no data:")
    for node in graph:
        if ("type" not in graph.node[node]
            and not node.startswith("AttachToI")
            and graph.in_degree(node) > 0):
            print()
            print(node)
            for caller in graph.predecessors(node):
                if caller:
                    edge = graph.get_edge_data(caller, node)
                    print()
                    print("-> from : {}".format(graph.node[caller]))
                    print("    via : {}".format(edge))

def print_children(graph, parent):
    """Display all the successor nodes from parent
    """
    walk_tree(graph, parent, func=graph.successors)

def print_parents(graph, child):
    """Display all the predecessor nodes from child
    """
    walk_tree(graph, child, func=graph.predecessors)

def walk_tree(graph, target, seen=None, level=1, func=None):
    """Display all the parent / child nodes from target
    """
    if seen is None:
        seen = []
    seen.append(target)
    for node in func(target):
        node_data = graph.node[node]
        if ("type" in node_data and
                node_data["type"] in IGNORE_TYPES):
            continue

        print()
        if func == graph.predecessors:
            edge_data = graph.get_edge_data(node, target)
        else:
            edge_data = graph.get_edge_data(target, node)
        if node_data:
            if node in seen:
                pindent(colorized(node_data, "white"), level)
            else:
                pindent(colorized(node_data), level)
            for _, edge in edge_data.iteritems():
                pindent(colorized(edge), level)

            if not node in seen and (MAX_LEVEL == 0 or MAX_LEVEL > level):
                walk_tree(graph, node, seen, level+1, func)
        else:
            pindent("{} is an undefined reference!".format(node), level)


def select_nodes(graph, query):
    """Obtain list of nodes that match provided pattern

    Also match if any of the edges also match
    """
    nodes = []
    for node in graph:
        try:
            node_data = get_node_data(graph, node)
            if node_data.get("type") in IGNORE_TYPES:
                continue
            elif match(query, node_data):
                nodes.append((node, node_data))
                continue
            if EDGE_MATCH:
                for edge in graph.edges_iter(node, data=True):
                    _, _, edge_data = edge
                    if edge_data.get("type") in IGNORE_TYPES:
                        continue
                    elif match(query, edge_data):
                        nodes.append((node, node_data))
                    break
        except Exception as err_msg:
            print("\n\n-> Error: '{}' matching {} in {}".format(err_msg, query, node))
    return nodes

def get_node_data(graph, node):
    """Retrieve data stored with node and add counts

    Adds 'counts: p<c' for parents and children
    """
    node_data = graph.node[node]
    if node_data:
        parents = len(graph.predecessors(node))
        children = len(graph.successors(node))
        node_data["counts"] = "{}<{}".format(parents, children)
    return node_data

def special_command(query):
    # pylint: disable=global-statement
    """Provide for special commands to change settings

    -> '$$max_level=n' to set graph expansion depth
    -> '$$ignore=foo bar' to ignore foo and bar types
    -> '$$edges=True' to include edges in the match
    -> '$$minimal=False' to expand attributes printed
    -> '$$regen' to regenerate the graph
    """
    if query.startswith("$$max_level="):
        global MAX_LEVEL
        try:
            level = int(query.rsplit("=")[-1])
        except ValueError:
            print("\n-> Error: Invalid value for max level!\n")
        else:
            MAX_LEVEL = level
            print("\n-> MAX_LEVEL updated to {}\n".format(level))
        return True
    elif query.startswith("$$ignore="):
        global IGNORE_TYPES
        IGNORE_TYPES = query.rsplit("=")[-1].split()
        print("\n-> IGNORE_TYPES updated to {}\n".format(IGNORE_TYPES))
        return True
    elif query.startswith("$$edges="):
        global EDGE_MATCH
        value = query.rsplit("=")[-1].lower()
        EDGE_MATCH = {"true": True, "false": False}.get(value, False)
        print("\n-> EDGE_MATCH updated to {}\n".format(EDGE_MATCH))
        return True
    elif query.startswith("$$minimal="):
        global MINIMAL_DISPLAY
        value = query.rsplit("=")[-1].lower()
        MINIMAL_DISPLAY = {"true": True, "false": False}.get(value, True)
        print("\n-> MINIMAL_DISPLAY updated to {}\n".format(MINIMAL_DISPLAY))
        return True
    elif query.startswith("$$regen"):
        global GLOW_GRAPH
        print()
        GLOW_GRAPH = create_graph()
        print_graph_info(GLOW_GRAPH)
        return True

def print_nodes(nodes):
    """Print a sorted list of selected ndoes
    """
    print()
    if nodes:
        nodes.sort(key=lambda (_, data): ("name" in data and data["name"]))
        for index, (_, node_data) in enumerate(nodes):
            print("{:>3} {}".format(index, colorized(node_data)))

def print_selected_node(graph, index, nodes):
    """Display selected node details
    """
    node, node_data = nodes[index]
    print()
    print("-" * 120)
    print()
    pindent(colorized(node_data, display=MINIMAL_DISPLAY), 0)
    print()
    print("These are the parents (predecessors):")
    print_parents(graph, node)
    print()
    print("These are the children (successors):")
    print_children(graph, node)

def main():
    """Provide navigation of the selected Glow objects
    """
    global GLOW_GRAPH

    # ensure colors works on Windows, no effect on Linux
    init()

    if os.path.exists(CACHE_FILE):
        GLOW_GRAPH = load_object_from_file(CACHE_FILE)
        print("Graph loaded from cache: {} \n".format(CACHE_FILE))
    else:
        GLOW_GRAPH = create_graph()
    print_graph_info(GLOW_GRAPH)

    query = None
    nodes = []
    try:
        while True:
            print()
            question = "Enter regex for selecting nodes"
            if nodes:
                question += " or number of current node"
            query = input("{}: ".format(question))
            if special_command(query):
                continue
            elif nodes and query.isdigit() and int(query) in range(len(nodes)):
                print_selected_node(GLOW_GRAPH, int(query), nodes)
            elif invalid_regex(query):
                print()
                print("--> '{}' is an invalid regex!".format(query))
                continue
            else:
                nodes = select_nodes(GLOW_GRAPH, query)
                if len(nodes) == 1:
                    print_selected_node(GLOW_GRAPH, 0, nodes)
                else:
                    print_nodes(nodes)

    except KeyboardInterrupt:
        pass
    except Exception as err_msg:    # pylint: disable=broad-except
        print()
        print("-> Error occurred: {}".format(err_msg))
    finally:
        print()
        print()
        print("Thanks for using the Glow Navigator")
        print()
        print()
        sys.exit()

if __name__ == "__main__":
    main()
