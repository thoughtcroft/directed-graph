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
import readline  # pylint: disable=unused-import
import sys
import time
import uuid
import xml.etree.ElementTree as ET
import yaml

# external libraries
from glow_config import settings
import networkx as nx
from termcolor import colored

COMMAND_LOOKUP = {}
TEMPLATE_LOOKUP = {}

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
            if remove_xmlns(node.tag) == tag:
                yield self._data(node, tag)

    def _data(self, node, tag):
        """Generate the object according to tag
        """
        if tag == "AsyncImage":
            return self._ph_dict(node)
        if tag == "ConditionalIfActivity":
            return self._con_dict(node)
        if tag == "form":
            return self._form_dict(node)
        if tag == "Tile":
            return self._ph_dict(node)

    def _ph_dict(self, node):
        """Create the dictionary of Placeholders

        The nodes Placeholder element attributes
        are remapped using the topics dict. Each
        {name: topic, value: amount} is turned into
        {topic: amount} if value has been set
        """
        topics = {
            "Text":         "name",
            "Description":  "description",
            "PagePK":       "template",
            "Page":         "template_name",
            "Workflow":     "formflow",
            "Image":        "image",
            "CommandRule":  "command"
            }

        ph_dict = self._convert_dict(node, "Placeholder")
        return self._build_dict(ph_dict, topics)

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
            "path":       "entity_path"
            }

        f_dict = self._build_dict(node.attrib, topics)
        f_dict["type"] = "link"
        f_dict["name"] = "Form dependency"
        return f_dict

    @staticmethod
    def _convert_dict(node, tag):
        """Convert names/value pairs to dict

        Converts Name:foo, Value:bar into foo:bar
        """
        p_dict = {}
        for elem in node.iter():
            e_dict = elem.attrib
            if (remove_xmlns(elem.tag) == tag
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


# global functions

def load_file(file_name):
    """Return YAML from required file
    """
    try:
        return yaml.load(open(file_name, "r"))
    except yaml.scanner.ScannerError as err_msg:
        print("Error: '{}' in {}".format(err_msg, file_name))

def clear_screen():
    """Clear the screen for better view"""
    print("\033[H\033[J")

def raw_guid(guid):
    """Remove hyphens from string guid
    """
    return uuid.UUID(guid).hex

def full_guid(guid):
    """Format guid with hyphens
    """
    return str(uuid.UUID(guid))

def base_name(file_name):
    """Return the base name of the file
    """
    return os.path.basename(file_name).rsplit('.', 1)[0]

def remove_xmlns(text):
    """Strip out any xmlns from xml tag
    """
    return re.sub(r"\{.*\}", "", text)

def glow_file_object(name):
    """Return a single glow object
    """
    if name in settings:
        return settings[name]

def glow_file_objects(omit=None):
    """Return the glow objects with files

    Ignore any objects passed in omit list
    """
    if omit is None:
        omit = []
    return (v for k, v in settings.iteritems()
            if "path" in v and not k in omit)

def serialize(g_dict, display=False):
    """Serialize a node or edge properties

    Used for searching full list or optional
    display=True for printing minimal list
    """
    if (display and "type" in g_dict and
            g_dict["type"] in settings):
        d_dict = settings[g_dict["type"]]
        g_list = ("{}: {}".format(k, g_dict[k])
                  for k in d_dict["display"]
                  if k in g_dict)
    else:
        g_list = ("{}: {}".format(k, v)
                  for (k, v) in g_dict.iteritems())
    return ", ".join(g_list)

def match(query, g_dict):
    """Check if the regex query matches dict
    """
    s_dict = serialize(g_dict)
    pattern = r"{}".format(query)
    return re.search(pattern, s_dict, flags=re.IGNORECASE)


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
    for file_name in glob.iglob(abs_path):
        values = load_file(file_name)
        glow_object = GlowObject(attrs, values)
        add_entity_to_graph(graph, glow_object, file_name)

    for attrs in glow_file_objects(omit=["entity"]):
        abs_path = os.path.abspath(attrs["path"])
        for file_name in glob.iglob(abs_path):
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
    additional templates in the dependencies
    """
    graph.add_node(template.guid, template.map())
    if template.data:
        xml_parser = XMLParser(template.data)

        for image in xml_parser.iterfind("AsyncImage"):
            image["type"] = "image"
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

def update_template_reference(attrs):
    """Necessary to correct for old style of referencing

    Referencing by page name instead of page PK causes
    a problem as we may not have processed that template
    """
    assert "template_name" in attrs
    if "template" in attrs:
        return
    if not TEMPLATE_LOOKUP:
        # initialise on first use
        abs_path = os.path.abspath(settings["template"]["path"])
        for file_name in glob.iglob(abs_path):
            values = load_file(file_name)
            TEMPLATE_LOOKUP[values["VZ_FormID"]] = values["VZ_PK"]
    attrs["template"] = TEMPLATE_LOOKUP[attrs["template_name"]]

def add_entity_to_graph(graph, entity, file_name):
    """Add entity level information to the graph

    Only adds Command Rules for now which are based
    on 'name' as 'guid' is not used by referrers.
    Also creates COMMAND_LOOKUP to handle entity
    command inheritance
    """
    module_fields = {
        "ruleId":     "guid",
        "ruleType":   "rule_type",
        "methodName": "command_type"
        }

    entity_name = base_name(file_name)
    properties = entity.values['properties']
    for name, attrs in properties.iteritems():
        p_dict = attrs[0]
        e_dict = {}
        if p_dict["ruleType"] == "CMD":
            e_dict["name"] = name
            e_dict["type"] = "command"
            e_dict["entity"] = entity_name
            for key, value in p_dict.iteritems():
                if key in module_fields:
                    e_dict[module_fields[key]] = value
            add_to_command_lookup(name, entity_name)
            command = "{}-{}".format(name, entity_name)
            graph.add_node(command, e_dict)

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

def pindent(text, level):
    """Indent print by specified level
    """
    print("{:>3} {}{}".format(level, "  " * level, text))

def coloring(data_dict):
    """Lookup data properties to determine the best color
    """
    try:
        color = settings[data_dict["type"]]["color"]
    except KeyError:
        color = "white"
    return color

def colorized(data_dict, color=None):
    """Format and color node or edge data"""
    if color is None:
        color = coloring(data_dict)
    data = serialize(data_dict, display=True)
    return colored(data, color)

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

def invalid_regex(expression):
    """Check for bad regex expression
    """
    result = True
    if expression:
        try:
            re.compile(r"{}".format(expression))
        except re.error:
            pass
        else:
            result = False
    return result


def main():
    """Provide navigation of the selected Glow objects
    """
    clear_screen()
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

""")
    print("Generating directed graph (< 1 min) ...")
    start_time = time.time()
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
                query = input("Enter regex for selecting a node: ")
            if invalid_regex(query):
                print()
                print("--> '{}' is an invalid regex!".format(query))
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
        print()
    finally:
        print()
        print("Thanks for using the Glow Navigator")
        print()

if __name__ == "__main__":
    main()