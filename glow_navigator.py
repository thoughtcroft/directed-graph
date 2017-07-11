#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin

"""Glow Navigator

Command line tool for exloring the relationships between
Form-flows and Templates in Glow designed apps
"""

# python2 and python3 portability
from __future__ import print_function
from builtins import input

# standard libraries
import glob
import pdb
import re
import readline
import time
import xml.etree.ElementTree as ET
import yaml

# external libraries
import networkx as nx
from termcolor import colored


COLOR_LOOKUP = {
    "formflow": "green",
    "template": "cyan",
    "FRM":      "blue",
    "JMP":      "red",
    "tile":     "yellow"
    }

GLOW_OBJECTS = {
    "entity": {
        "type": "entity",
        "path": "DotNet/Infrastructure/Rules/Configuration/Entities/*.yaml",
        "fields": {
            },
        "display": []
        },
    "formflow": {
        "type": "formflow",
        "path": "DotNet/SystemData/SystemData/BPM/BPMWorkflowTmpl/*.yaml",
        "display": ["name", "type", "entity"],
        "fields": {
            "guid":        "VM_PK",
            "name":        "VM_Name",
            "entity":      "VM_EntityType",
            "form_factor": "VM_FormFactor",
            "is_active":   "VM_IsActive",
            "usage":       "VM_Usage",
            "tasks":       "BPMTaskTmpls"
            }
        },
    "template": {
        "type": "template",
        "path": "DotNet/SystemData/SystemData/BPM/BPMForm/*.yaml",
        "display": ["name", "type", "form_type", "entity"],
        "fields": {
            "guid":        "VZ_PK",
            "name":        "VZ_FormID",
            "entity":      "VZ_EntityType",
            "form_factor": "VZ_FormFactor",
            "is_active":   "VZ_IsActive",
            "form_type":   "VZ_FormType",
            "data":        "VZ_FormData"
            }
        },
    "task": {
        "type": "task",
        "display": ["name", "type", "task", "entity"],
        "fields": {
            "guid":        "VR_PK",
            "name":        "VR_Description",
            "entity":      "VR_DataContextOverride",
            "task":        "VR_Type",
            "formflow":    "VR_VM_JumpToWorkflowTemplate",
            "template":    "VR_VZ_Form",
            "is_active":   "VR_IsActive"
            }
        }
    }


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
        for attr in ("data", "guid", "tasks"):
            mapping.pop(attr, None)
        return mapping


class XMLParser(object):
    # pylint: disable=too-few-public-methods
    """Glow Template XML parser
    """
    TOPICS = {
        "Text":         "name",
        "Description":  "description",
        "PagePK":       "template",
        "Workflow":     "formflow"
        }

    def __init__(self, xml):
        self.tree = ET.fromstring(xml)

    def iterfind(self, tag):
        """Generator for elements matching tag

        Find nodes with tag then burrow into its
        collection of Placeholder elements and return
        the name, value pairs as a dictionary
        """
        for node in self.tree.iter():
            if remove_xmlns(node.tag) == tag:
                yield self._ph_dict(node)

    def _ph_dict(self, node):
        """Create the dictionary of Placeholders

        The nodes Placeholder element attributes
        are remapped using the topics dict. Each
        {name: topic, value: amount} is turned into
        {topic: amount} if value has been set
        """
        ph_dict = {}
        for elem in node.iter():
            if remove_xmlns(elem.tag) != "Placeholder":
                continue
            e_dict = elem.attrib
            if e_dict["Value"] and e_dict["Name"] in self.TOPICS:
                key = self.TOPICS[e_dict["Name"]]
                ph_dict[key] = e_dict["Value"]
        return ph_dict


# global functions

def clear_screen():
    """Clear the screen for better view"""
    print("\033[H\033[J")

def raw_guid(guid):
    """Remove hyphens from string guid
    """
    return guid.replace("-", "")

def load_file(file_name):
    """Return YAML from required file
    """
    return yaml.load(open(file_name, "r"))

def remove_xmlns(text):
    """Strip out any xmlns from xml tag
    """
    return re.sub(r"\{.*\}", "", text)

def glow_file_objects():
    """Return the glow objects with files
    """
    return (v for _, v in GLOW_OBJECTS.iteritems()
            if "path" in v)

def serialize(g_dict, display=False):
    """Serialize a node or edge properties

    Used for searching full list or optional
    display=True for printing minimal list
    """
    if display and g_dict["type"] in GLOW_OBJECTS:
        d_dict = GLOW_OBJECTS[g_dict["type"]]
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
    for attrs in glow_file_objects():
        for file_name in glob.iglob(attrs["path"]):
            values = load_file(file_name)
            glow_object = GlowObject(attrs, values)
            graph.add_node(glow_object.guid, glow_object.map())

            if glow_object.type == "formflow" and glow_object.tasks:
                for task in glow_object.tasks:
                    go_task = GlowObject(GLOW_OBJECTS["task"], task)
                    if go_task.task == "FRM":
                        graph.add_edge(glow_object.guid, go_task.template, go_task.map())
                    elif go_task.task == "JMP":
                        graph.add_edge(glow_object.guid, go_task.formflow, go_task.map())
                continue

            if glow_object.type == "template" and glow_object.data:
                xml_parser = XMLParser(glow_object.data)
                for tile in xml_parser.iterfind("Tile"):
                    tile["type"] = "tile"
                    if not "entity" in tile:
                        tile["entity"] = glow_object.entity
                    if "template" in tile:
                        graph.add_edge(glow_object.guid, tile["template"], tile)
                    elif "formflow" in tile:
                        graph.add_edge(glow_object.guid, tile["formflow"], tile)
                continue
    return graph

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
    print("{} {}{}".format(level, "  " * level, text))

def coloring(data_dict):
    """Lookup data properties to determine the best color
    """
    for _, value in data_dict.iteritems():
        if value in COLOR_LOOKUP:
            return COLOR_LOOKUP[value]
    return "white"

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
        node_data = graph.node[node]
        if match(query, node_data):
            nodes.append((node, node_data))
    return nodes

def invalid_regex(expression):
    """Check for bad regex expression
    """
    try:
        re.compile(r"{}".format(expression))
    except re.error:
        return True
    return False



def main():
    """Provide navigation of the selected Glow objects
    """
    clear_screen()
    print("""

    Welcome to the Glow Navigator
    -----------------------------

This is a prototype exploration tool for
the relationship between formflows and
templates (forms and pages) using a directed
graph.

""")
    print("Generating directed graph (30 secs) ...")
    start_time = time.time()
    graph = create_graph()
    end_time = time.time()
    elapsed_time = round(end_time - start_time)
    print("Graph completed in {} seconds".format(elapsed_time))
    print()
    print(nx.info(graph))
    focus = None

    try:
        while True:
            print()
            if isinstance(focus, basestring):
                query = focus
            else:
                query = input("Enter regex for selecting a node: ")
            if invalid_regex(query):
                print()
                print("--> {} is an invalid regex!".format(query))
                continue

            nodes = select_nodes(graph, query)
            print()
            if nodes:
                nodes.sort(key=lambda (node, data): data["name"])
                for index, (node, node_data) in enumerate(nodes):
                    print("{:>3} {}".format(index, colorized(node_data)))

                print()
                focus = input("Enter number to naviagte or another regex to search again: ")
                try:
                    focus = int(focus)
                except ValueError:
                    continue
                if focus in range(len(nodes)):
                    node, node_data = nodes[int(focus)]
                    print()
                    print("{} : {}".format(node, colorized(node_data)))
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
