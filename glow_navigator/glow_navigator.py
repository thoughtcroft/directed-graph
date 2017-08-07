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


Special commands
----------------
You vary the degree of expansion when looking at a specific
object. Entering '$$max_level=n' will stop expanding the parent or
children beyond the specified level. Default value is '1', setting to '0'
will expand all available levels.

To ignore particular types of entities when searching and expanding the graph
use the '$$ignore=foo, bar' to ignore types 'foo' and 'bar'. Just provide an
empty list to clear out the ignore list.

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
MAX_LEVEL = 1
IGNORE_TYPES = []


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
        c_dict["type"] = "link"
        c_dict["link_type"] = "conditional task"
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
        f_dict["link_type"] = "form dependency"
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
        p_dict["link_type"] = "property dependency"
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
    graph = nx.MultiDiGraph(name="Glow")

    # add entity first so the command dict is available
    attrs = glow_file_object("entity")
    abs_path = os.path.abspath(attrs["path"])
    label_text = "{0:25}".format("Loading entities")
    with click.progressbar(glob.glob(abs_path), label=label_text, show_eta=False) as progress_bar:
        for file_name in progress_bar:
            values = load_file(file_name)
            values["name"] = base_name(file_name)
            glow_object = GlowObject(attrs, values)
            add_entity_to_graph(graph, glow_object)

    for attrs in glow_file_objects(omit=["entity"]):
        abs_path = os.path.abspath(attrs["path"])
        label_text = "{0:25}".format("Analysing {}s".format(attrs["type"]))
        with click.progressbar(glob.glob(abs_path), label=label_text, show_eta=False) as progress_bar:
            for file_name in progress_bar:
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
                    add_metadata_to_graph(graph, glow_object, file_name)
                if glow_object.type == "module":
                    add_module_to_graph(graph, glow_object)
                if glow_object.type == "template":
                    add_template_to_graph(graph, glow_object)
    return graph

def add_metadata_to_graph(graph, metadata, file_name):
    """Add additional entity metadata and edges to the graph
    """
    if not metadata.name:
        field = metadata.fields["name"]
        metadata.name = base_name(file_name)
        metadata.values[field] = metadata.name
    m_dict = {
        "name": metadata.name,
        "type": "entity",
        "entity": metadata.name
    }
    graph.add_node(metadata.name, m_dict)
    if not metadata.data:
        return

    data = metadata.data
    m_dict = {
        "name":      "Entity metadata",
        "type":      "link"
    }
    rdo_fld = metadata.fields["read_only"]
    con_fld = metadata.fields["condition"]
    if (rdo_fld in data and
            isinstance(data[rdo_fld], dict) and
            con_fld in data[rdo_fld]):
        condition_guid = data[rdo_fld][con_fld]
        m_dict["link_type"] = "read_only"
        graph.add_edge(metadata.name, condition_guid.lower(), attr_dict=m_dict)

    if "icon" in data:
        m_dict["link_type"] = "icon_image"
        graph.add_edge(metadata.name, data["icon"].lower(), attr_dict=m_dict)

def add_formflow_to_graph(graph, formflow):
    """Add a formflow object and its edges to the graph

    Also iterates through tasks (formflow steps) and
    adds form displays, formflow jump, run command rules
    as well as any referenced conditions
    """
    graph.add_node(formflow.guid, formflow.map())

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
        # build a dictionary so we can process conditions first
        # and then add any that aren't subject to conditions
        for task in formflow.tasks:
            go_task = GlowObject(settings["task"], task)
            add_task_edge_to_graph(graph, formflow, go_task)

    if formflow.data:
        xml_parser = XMLParser(formflow.data)
        for condition in xml_parser.iterfind("ConditionalIfActivity"):
            graph.add_edge(formflow.guid, condition["condition"].lower(), attr_dict=condition)

def add_task_edge_to_graph(graph, formflow, task):
    """Add an edge to the graph from a task object
    """
    if task.task == "FRM" and task.template:
        graph.add_edge(formflow.guid, task.template.lower(), attr_dict=task.map())
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
        graph.add_edge(module.guid, module.template.lower(), attr_dict=m_dict)

def add_template_to_graph(graph, template):
    """Add a template object and its edges to the graph

    Iterates through any tiles on the template and
    adds the relevant link as an edge. Also looks for
    additional references in the dependencies
    """
    graph.add_node(template.guid, template.map())
    if template.entity:
        t_dict = {
            "type": "link",
            "link_type": "template entity"
        }
        graph.add_edge(template.entity, template.guid, attr_dict=t_dict)

    if template.data:
        xml_parser = XMLParser(template.data)

        for image in xml_parser.iterfind("AsyncImage"):
            if "image" in image:
                image["type"] = "link"
                image["link_type"] = "static image"
                graph.add_edge(template.guid, image["image"].lower(), attr_dict=image)

        for image in xml_parser.iterfind("Grid"):
            if "image" in image:
                image["type"] = "link"
                image["link_type"] = "background image"
                graph.add_edge(template.guid, image["image"].lower(), attr_dict=image)

        for tile in xml_parser.iterfind("Tile"):
            tile["type"] = "tile"
            if not "entity" in tile and template.entity:
                tile["entity"] = template.entity
            if "template_name" in tile:
                # need to correct for old style references
                update_template_reference(tile)
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

    if template.dependencies:
        xml_parser = XMLParser(template.dependencies)
        for form in xml_parser.iterfind("form"):
            graph.add_edge(template.guid, form["template"].lower(), attr_dict=form)
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
        graph.add_edge(parent, base_prop, attr_dict=attrs)

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

def add_entity_to_graph(graph, entity):
    """Add entity level information to the graph

    - adds Command Rules based on 'name' as 'guid'
      is not used by referrers.
    - creates COMMAND_LOOKUP to handle entity
      command inheritance
    - adds calculated properties
    - looks for conditions referenced in rules
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
        "ruleId":       "guid",
        "ruleType":     "property_type",
        "methodName":   "rule_type",
        "conditionIds": "conditions"
        }

    link_types = {
        "CMD": "command",
        "PRP": "calculated property",
        "PRO": "defaulting rule",
        "VAL": "validation rule",
        "LOO": "lookup rule"
        }

    graph.add_node(entity.name, entity.map())
    if entity.properties:
        for name, rules in entity.properties.iteritems():
            reference = "{}-{}".format(name, entity.name)
            for rule in rules:
                r_dict = build_dict(rule, topics)
                r_dict["name"] = name
                r_dict["entity"] = entity.name
                rule_type = r_dict["property_type"]

                if rule_type == "CMD":
                    r_dict["type"] = "command"
                    add_to_command_lookup(name, entity.name)
                else:
                    r_dict["type"] = "property"
                graph.add_node(reference, r_dict)

                e_dict = copy.deepcopy(r_dict)
                e_dict["type"] = "link"
                if rule_type in link_types:
                    e_dict["link_type"] = link_types[rule_type]
                else:
                    e_dict["link_type"] = "unknown->{}".format(rule_type)
                graph.add_edge(entity.name, reference, attr_dict=e_dict)


                if "conditions" in e_dict:
                    for condition in e_dict["conditions"]:
                        if condition:
                            graph.add_edge(reference, condition.lower(), attr_dict=e_dict)

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
        if "type" not in graph.node[node]:
            print()
            print(node)
            for caller in graph.predecessors(node):
                if caller:
                    edge = graph.get_edge_data(caller, node)
                    print()
                    print("-> from : {}".format(graph.node[caller]))
                    print("    via : {}".format(edge))

def print_children(graph, parent, seen=None, level=1):
    """Display all the successor nodes from parent
    """
    walk_tree(graph, parent, None, level, graph.successors)

def print_parents(graph, child, level=1):
    """Display all the predecessor nodes from child
    """
    walk_tree(graph, child, None, level, graph.predecessors)

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
    """
    nodes = []
    for node in graph:
        node_data = get_node_data(graph, node)
        if ("type" in node_data and
                node_data["type"] in IGNORE_TYPES):
            continue
        if match(query, node_data):
            nodes.append((node, node_data))
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
    """Provide for special commands to change settings

    -> '$$max_level=n' to set graph expansion depth
    -> '$$ignore=foo bar' to ignore foo and bar types
    """
    if query.startswith("$$max_level="):
        global MAX_LEVEL
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
    elif query.startswith("$$ignore="):
        global IGNORE_TYPES
        IGNORE_TYPES = query.rsplit("=")[-1].split()
        print()
        print("-> IGNORE_TYPES updated to {}".format(IGNORE_TYPES))
        print()
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
                query = input("Enter regex for selecting nodes: ")
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
