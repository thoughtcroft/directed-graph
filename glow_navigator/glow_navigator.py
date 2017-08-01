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
import glob
import os.path
import pdb
import re
try:
    import readline                 # pylint: disable=unused-import
except ImportError:
    import pyreadline as readline   # pylint: disable=unused-import
import sys
import time
import xml.etree.ElementTree as ET

# external libraries
import click
import networkx as nx
from colorama import init

# put this out as import generation takes time
start_time = time.time()
print("""

    Welcome to the Glow Navigator
    -----------------------------

This is a prototype exploration tool for
the relationship between formflows, pages, forms
conditions, command rules and images using a directed
graph.

Search strings are specified as regex
(see http://regex101.com for details).

For example to find:

 - anything containing 'truck'
   > truck

 - only templates containing 'truck'
   > (?=.*type: template)(?=.*truck)

 - anything with one or more parents
   > ^(?!.*counts: 0<)

You are only limited by your imagination (and regex skills)

You can also vary the degree of expansion when looking at a specific
object. Entering '$$max_level=n' will stop expanding the parent or
children beyond the specified level. Default value is '3', setting to '0'
will expand all available levels.
""")

from . glow_config import settings
from . glow_templates import template_lookup
from . glow_utils import (
    base_name,
    colorized,
    full_guid,
    glow_file_object,
    glow_file_objects,
    invalid_regex,
    load_file,
    match,
    pindent)


COMMAND_LOOKUP = {}
MAX_LEVEL = 3


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
        try:
            return self.values[field]
        except KeyError:
            return None

    def map(self):
        """Return a dict of values mapped to fields

        Returns a limited subset of values: those that
        have keys mapped in the fields dictionary
        """
        mapping = {k : self.values[v]
                   for k, v in self.fields.iteritems()
                   if v in self.values}
        # add type and remove noisy attributes
        mapping["type"] = self.type
        for attr in ("data", "guid", "tasks", "dependencies"):
            mapping.pop(attr, None)
        return mapping


class XMLParser(object):
    # pylint: disable=too-few-public-methods
    """Glow Template XML parser
    """

    def __init__(self, xml):
        try:
            self.tree = ET.fromstring(xml.encode(encoding='utf-8'))
        except UnicodeEncodeError:
            pdb.set_trace()

    def iterfind(self, tag):
        """Generator for elements matching tag

        Find nodes with tag and return an appropriate
        data structure (varies by tag)
        """
        for node in self.tree.iter():
            if self.remove_xmlns(node.tag) == tag:
                yield self._data(node, tag)

    def _data(self, node, tag):
        """Generate the object according to tag
        """
        if tag == "AsyncImage" or tag == "Tile":
            return self._ph_dict(node)
        if tag == "ConditionalIfActivity":
            return self._con_dict(node)
        if tag == "form":
            return self._form_dict(node)
        if tag == "Grid":
            return self._grid_dict(node)
        if tag == "calculatedProperty" or tag == "simpleConditionExpression":
            return self._prop_dict(node)

    def _ph_dict(self, node):
        """Create the dictionary of Placeholders

        The nodes Placeholder element attributes
        are remapped using the topics dict. Each
        {name: topic, value: amount} is turned into
        {topic: amount} if value has been set
        """
        topics = {
            "Text":              "name",
            "Description":       "description",
            "PagePK":            "template",
            "Page":              "template_name",
            "Workflow":          "formflow",
            "Image":             "image",
            "CommandRule":       "command",
            "BackgroundImagePk": "image",
            "Url":               "url"
            }

        ph_dict = self._convert_dict(node, "Placeholder")
        return self._build_dict(ph_dict, topics)

    def _grid_dict(self, node):
        """Create the dictionary of the form Grid

        Need to get to the last element and
        then return our normal Placeholder dictionary
        """
        g_dict = {}
        if len(node):
            g_dict = self._ph_dict(node[-1])
        return g_dict

    def _con_dict(self, node):
        """Create the dictionary of the Condition

        The ConditionalIfActivity element refers to the condition
        """
        topics = {
            "ResKey":            "guid",
            "DisplayName":       "name",
            "SelectedCondition": "condition",
            }

        c_dict = self._build_dict(node.attrib, topics)
        c_dict["type"] = "condition"
        c_dict["condition_type"] = "task"
        return c_dict

    def _form_dict(self, node):
        """Create the dictionary for form dependent link
        """
        topics = {
            "templateID": "template",
            "path":       "property"
            }

        f_dict = self._build_dict(node.attrib, topics)
        f_dict["type"] = "link"
        f_dict["name"] = "Form dependency"
        return f_dict

    def _prop_dict(self, node):
        """Create the dictionary for property dependent link
        """
        topics = {
            "path":         "property",
            "propertypath": "property"
            }

        p_dict = self._build_dict(node.attrib, topics)
        p_dict["type"] = "link"
        p_dict["name"] = "Property dependency"
        return p_dict
    def _convert_dict(self, node, tag):
        """Convert names/value pairs to dict

        Converts Name:foo, Value:bar into foo:bar
        """
        p_dict = {}
        for elem in node.iter():
            e_dict = elem.attrib
            if (self.remove_xmlns(elem.tag) == tag
                    and e_dict["Value"]):
                p_dict[e_dict["Name"]] = e_dict["Value"]
        return p_dict

    @staticmethod
    def _build_dict(attrib, topics):
        """Build a dictionary of topics using attributes
        """
        result = {}
        for key, field in topics.iteritems():
            if key in attrib:
                result[field] = attrib[key]
        return result

    @staticmethod
    def remove_xmlns(text):
        """Strip out any xmlns from xml tag
        """
        return re.sub(r"\{.*\}", "", text)

def create_graph():
    """Create directed graph of objects

    Each Glow object is added as a node
    to the graph and references are added
    as edges from caller to callee
    """
    graph = nx.DiGraph(name="Glow")

    # add entity first so the command dict is available
    attrs = glow_file_object("entity")
    abs_path = os.path.abspath(attrs["path"])
    label_text = "{0:30}".format("Loading entities")
    with click.progressbar(glob.glob(abs_path), label=label_text, show_eta=False) as bar:
        for file_name in bar:
            values = load_file(file_name)
            glow_object = GlowObject(attrs, values)
            add_entity_to_graph(graph, glow_object, file_name)

    for attrs in glow_file_objects(omit=["entity"]):
        abs_path = os.path.abspath(attrs["path"])
        label_text = "{0:30}".format("Loading {}s".format(attrs["type"]))
        with click.progressbar(glob.glob(abs_path), label=label_text, show_eta=False) as bar:
            for file_name in bar:
                values = load_file(file_name)
                if not values:
                    continue
                glow_object = GlowObject(attrs, values)
                if glow_object.type == "condition":
                    add_condition_to_graph(graph, glow_object, file_name)
                if glow_object.type == "formflow":
                    add_formflow_to_graph(graph, glow_object)
                if glow_object.type == "image":
                    graph.add_node(glow_object.guid, glow_object.map())
                if glow_object.type == "metadata":
                    add_metadata_to_graph(graph, glow_object)
                if glow_object.type == "module":
                    add_module_to_graph(graph, glow_object)
                if glow_object.type == "template":
                    add_template_to_graph(graph, glow_object)
    return graph

def add_metadata_to_graph(graph, metadata):
    """Add additional entity metadata and edges to the graph

    Looks for read-only property referencing condition
    """
    if (metadata.data and
            "readOnly" in metadata.data and
            isinstance(metadata.data["readOnly"], dict) and
            "conditionId" in metadata.data["readOnly"]):
        condition_guid = metadata.data["readOnly"]["conditionId"]
        m_dict = {"name": metadata.name,
                  "type": metadata.type,
                  "link": "read_only",
                  "entity": metadata.name}
        graph.add_node(metadata.name, m_dict)
        graph.add_edge(metadata.name, condition_guid, {"type": "link"})

def add_formflow_to_graph(graph, formflow):
    """Add a formflow object and its edges to the graph

    Also iterates through tasks (formflow steps) and
    adds form displays, formflow jump, run command rules
    as well as any referenced conditions
    """
    graph.add_node(formflow.guid, formflow.map())

    if formflow.image:
        i_dict = {
            "type":      "link",
            "link_type": "formflow_icon"
            }
        graph.add_edge(formflow.guid, formflow.image, i_dict)

    if formflow.conditions:
        for condition in formflow.conditions:
            c_dict = {
                "type":             "condition",
                "name":             "If condition",
                "condition_type":   "formflow",
                "condition":        condition["VWT_ConditionId"],
                "guid":             condition["VWT_PK"]
                }
            graph.add_edge(formflow.guid, c_dict["condition"], c_dict)

    if formflow.tasks:
        # build a dictionary so we can process conditions first
        # and then add any that aren't subject to conditions
        for task in formflow.tasks:
            go_task = GlowObject(settings["task"], task)
            add_task_edge_to_graph(graph, formflow, go_task)

    if formflow.data:
        xml_parser = XMLParser(formflow.data)
        for condition in xml_parser.iterfind("ConditionalIfActivity"):
            graph.add_edge(formflow.guid, condition["condition"], condition)

def add_task_edge_to_graph(graph, formflow, task):
    """Add an edge to the graph from a task object
    """
    if task.task == "FRM" and task.template:
        graph.add_edge(formflow.guid, task.template, task.map())
    elif task.task == "JMP" and task.formflow:
        graph.add_edge(formflow.guid, task.formflow, task.map())
    elif task.task == "RUN" and task.command:
        entity = get_command_entity(task.command, formflow.entity)
        command = "{}-{}".format(task.command, entity)
        graph.add_edge(formflow.guid, command, task.map())

def add_condition_to_graph(graph, condition, file_name):
    """Add a condition object to the graph
    """
    guid = full_guid(base_name(file_name))
    graph.add_node(guid, condition.map())
    if condition.expression:
        xml_parser = XMLParser(condition.expression)
        for prop in xml_parser.iterfind("simpleConditionExpression"):
            reference = "{}-{}".format(prop["property"], condition.entity)
            add_property_edge_if_exists(graph, guid, reference, prop)

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
        graph.add_edge(module.guid, module.template, m_dict)

def add_template_to_graph(graph, template):
    """Add a template object and its edges to the graph

    Iterates through any tiles on the template and
    adds the relevant link as an edge. Also looks for
    additional references in the dependencies
    """
    graph.add_node(template.guid, template.map())
    if template.data:
        xml_parser = XMLParser(template.data)

        for image in xml_parser.iterfind("AsyncImage"):
            if "image" in image:
                image["type"] = "link"
                image["link_type"] = "static_image"
                graph.add_edge(template.guid, image["image"], image)

        for image in xml_parser.iterfind("Grid"):
            if "image" in image:
                image["type"] = "link"
                image["link_type"] = "background_image"
                graph.add_edge(template.guid, image["image"], image)

        for tile in xml_parser.iterfind("Tile"):
            tile["type"] = "tile"
            if not "entity" in tile and template.entity:
                tile["entity"] = template.entity
            if "template_name" in tile:
                # need to correct for old style references
                update_template_reference(tile)
            if "template" in tile:
                graph.add_edge(template.guid, tile["template"], tile)
            if "formflow" in tile:
                graph.add_edge(template.guid, tile["formflow"], tile)
            if "command" in tile:
                entity = get_command_entity(tile["command"], tile["entity"])
                command = "{}-{}".format(tile["command"], entity)
                graph.add_edge(template.guid, command, tile)
            if "image" in tile:
                graph.add_edge(template.guid, tile["image"], tile)

    if template.dependencies:
        xml_parser = XMLParser(template.dependencies)
        for form in xml_parser.iterfind("form"):
            graph.add_edge(template.guid, form["template"], form)
        for prop in xml_parser.iterfind("calculatedProperty"):
            reference = "{}-{}".format(prop["property"], template.entity)
            add_property_edge_if_exists(graph, template.guid, reference, prop)

def add_property_edge_if_exists(graph, parent, prop, attrs):
    """Conditionally add reference to property if exists

    Also deconstruct property name when checking so that
    'entity.collection.prop' checks against 'prop'
    """
    base_prop = prop.rsplit(".")[-1]
    if graph.has_node(base_prop):
        graph.add_edge(parent, base_prop, attrs)

def update_template_reference(attrs):
    """Necessary to correct for old style of referencing

    Referencing by page name instead of page PK causes
    a problem as we may not have processed that template
    """
    if "template" in attrs:
        return
    try:
        attrs["template"] = template_lookup[attrs["template_name"]]
    except KeyError as err_msg:
        print("-> Error: '{}' looking up {}".format(err_msg, attrs))

def add_entity_to_graph(graph, entity, file_name):
    """Add entity level information to the graph

    - adds Command Rules based on 'name' as 'guid'
      is not used by referrers.
    - creates COMMAND_LOOKUP to handle entity
      command inheritance
    - adds calculated properties
    """
    def build_dict(attrib, topics):
        """Build a dictionary of topics using attributes
        """
        result = {}
        for key, field in topics.iteritems():
            if key in attrib:
                result[field] = attrib[key]
        return result

    topics = {
        "ruleId":     "guid",
        "ruleType":   "property_type",
        "methodName": "rule_type"
        }

    entity_name = base_name(file_name)
    properties = entity.values['properties']
    if properties:
        for name, attrs in properties.iteritems():
            if attrs:
                e_dict = build_dict(attrs[0], topics)
                e_dict["name"] = name
                e_dict["entity"] = entity_name
                reference = "{}-{}".format(name, entity_name)
                if e_dict["property_type"] == "CMD":
                    e_dict["type"] = "command"
                    add_to_command_lookup(name, entity_name)
                    graph.add_node(reference, e_dict)
                elif e_dict["property_type"] == "PRP":
                    e_dict["type"] = "property"
                    graph.add_node(reference, e_dict)

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
    commands = COMMAND_LOOKUP
    if command in commands:
        if not entity in commands[command]:
            return commands[command][0]
    else:
        print("Bad command lookup: {}-{}".format(command, entity))
    return entity

def missing_nodes(graph):
    """Return data on nodes without data

    Indicates those nodes referenced in edges but which
    had were not added from files so represent orphan
    references from within other objects
    """
    print()
    print("These nodes have no data:")
    for node in graph:
        if "type" not in graph.node[node]:
            print()
            print(node)
            caller = graph.predecessors(node)[0]
            edge = graph.get_edge_data(caller, node)
            print()
            print("-> from : {}".format(graph.node[caller]))
            print("    via : {}".format(edge))

def print_children(graph, parent, seen=None, level=1):
    """Display all the successor nodes from parent
    """
    if seen is None:
        seen = []
    seen.append(parent)
    for child in graph.successors(parent):
        print()
        edge_data = graph.get_edge_data(parent, child)
        pindent(colorized(edge_data), level)
        node_data = graph.node[child]
        if node_data:
            if child in seen:
                pindent(colorized(node_data, "white"), level)
            else:
                pindent(colorized(node_data), level)
                if MAX_LEVEL == 0 or MAX_LEVEL > level:
                    print_children(graph, child, seen, level+1)
        else:
            pindent("{} is an undefined reference!".format(child), level)

def print_parents(graph, child, seen=None, level=1):
    """Display all the predecessor nodes from child
    """
    if seen is None:
        seen = []
    seen.append(child)
    for parent in graph.predecessors(child):
        print()
        edge_data = graph.get_edge_data(parent, child)
        pindent(colorized(edge_data), level)
        node_data = graph.node[parent]
        if node_data:
            if parent in seen:
                pindent(colorized(node_data, "white"), level)
            else:
                pindent(colorized(node_data), level)
                if MAX_LEVEL == 0 or MAX_LEVEL > level:
                    print_parents(graph, parent, seen, level+1)
        else:
            pindent("{} is an undefined reference!".format(parent), level)

def select_nodes(graph, query):
    """Obtain list of nodes that match provided pattern
    """
    nodes = []
    for node in graph:
        node_data = get_node_data(graph, node)
        if match(query, node_data):
            nodes.append((node, node_data))
    return nodes

def get_node_data(graph, node):
    """Retrieve data stored with node and add counts

    Adds 'counts: p<c' for parents and children
    """
    parents = len(graph.predecessors(node))
    children = len(graph.successors(node))
    node_data = graph.node[node]
    node_data["counts"] = "{}<{}".format(parents, children)
    return node_data

def special_command(query):
    """Provide for special commands to change settings
            if graph.has_node(reference):
                # we only want links to calculated properties
                graph.add_edge(template.guid, reference, prop)

    -> $$max_level=n is the only one supported so far
    """
    global MAX_LEVEL
    if query.startswith("$$max_level="):
        try:
            level = int(query.rsplit("=")[-1])
        except ValueError:
            print()
            print("-> Error: Invalid value for max level!")
            print()
        else:
            MAX_LEVEL = level
            print()
            print("-> MAX_LEVEL updated to {}".format(level))
            print()
        finally:
            return True

def main():
    """Provide navigation of the selected Glow objects
    """
    # ensure colors works on Windows, no effect on Linux
    init()
    graph = create_graph()
    end_time = time.time()
    elapsed_time = round(end_time - start_time)
    print()
    print("Graph completed in {} seconds".format(elapsed_time))
    print()
    print(nx.info(graph))

    if graph.number_of_nodes() == 0:
        print("Nothing was added to the graph - run again in the Glow source root")
        print()
        sys.exit()

    missing_nodes(graph)

    focus = None
    try:
        while True:
            if focus and isinstance(focus, basestring):
                query = focus
            else:
                print()
                query = input("Enter a $$ command or regex for selecting a node: ")
            if special_command(query):
                focus = None
                continue
            if invalid_regex(query):
                print()
                print("--> '{}' is an invalid regex!".format(query))
                focus = None
                continue

            nodes = select_nodes(graph, query)
            print()
            if not nodes:
                focus = None
            else:
                nodes.sort(key=lambda (node, data): ("name" in data and data["name"]))
                for index, (node, node_data) in enumerate(nodes):
                    print("{:>3} {}".format(index, colorized(node_data)))

                while True:
                    print()
                    focus = input("Enter number to navigate or another regex to search again: ")
                    try:
                        focus = int(focus)
                    except ValueError:
                        break
                    if focus in range(len(nodes)):
                        node, node_data = nodes[int(focus)]
                        print()
                        print("-" * 120)
                        print()
                        pindent(colorized(node_data), 0)
                        print()
                        print("These are the parents (predecessors):")
                        print_parents(graph, node)
                        print()
                        print("These are the children (successors):")
                        print_children(graph, node)

    except KeyboardInterrupt:
        pass
    finally:
        print()
        print()
        print("Thanks for using the Glow Navigator")
        print()
        print()
        sys.exit()

if __name__ == "__main__":
    main()
