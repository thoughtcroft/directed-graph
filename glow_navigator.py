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
    "Formflow": {
        "type":  "formflow",
        "path":  "BPMWorkflowTmpl/*.yaml",
        "fields": {
            "guid":        "VM_PK",
            "name":        "VM_Name",
            "entity":      "VM_EntityType",
            "form_factor": "VM_FormFactor",
            "is_active":   "VM_IsActive",
            "usage":       "VM_Usage",
            "tasks":       "BPMTaskTmpls"
            },
        "display": [
            "name", "type", "entity"
            ]
        },
    "Template": {
        "type":  "template",
        "path":  "BPMForm/*.yaml",
        "fields": {
            "guid":        "VZ_PK",
            "name":        "VZ_FormID",
            "entity":      "VZ_EntityType",
            "form_factor": "VZ_FormFactor",
            "is_active":   "VZ_IsActive",
            "type":        "VZ_FormType",
            "data":        "VZ_FormData"
            },
        "display": [
            "name", "type", "entity"
            ]
        },
    "Task": {
        "type":  "task",
        "fields": {
            "guid":        "VR_PK",
            "name":        "VR_Description",
            "entity":      "VR_DataContextOverride",
            "task":        "VR_Type",
            "formflow":    "VR_VM_JumpToWorkflowTemplate",
            "template":    "VR_VZ_Form",
            "is_active":   "VR_IsActive"
            },
        "display": [
            "name", "type", "task", "entity"
            ]
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

def display_properties(g_dict):
    """Node or edge properties for display
    """
    if g_dict["type"] in GLOW_OBJECTS:
        d_dict = GLOW_OBJECTS[g_dict["type"]]
        return {k: g_dict[k]
                for k in d_dict["display"]
                if k in g_dict}
    return g_dict

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
                    go_task = GlowObject(GLOW_OBJECTS["Task"], task)
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

def pindent(text, level, color="white"):
    """Indent print by specified level
    """
    text = colored(text, color)
    print("{} {}{}".format(level, "  " * level, text))

def coloring(data_dict):
    """Lookup data properties to determine the best color
    """
    for _, value in data_dict.iteritems():
        if value in COLOR_LOOKUP:
            return COLOR_LOOKUP[value]
    return "white"

def print_tree(graph, parent, seen=None, level=0):
    """Display all the reachable nodes from target"""
    if seen is None:
        seen = []
    seen.append(parent)
    node_data = display_properties(graph.node[parent])
    pindent(node_data, level, coloring(node_data))
    level += 1
    for child in graph.successors(parent):
        print()
        edge_data = display_properties(graph.get_edge_data(parent, child))
        pindent(edge_data, level, coloring(edge_data))
        if child in seen:
            pindent(graph.node[child], level, "white")
        else:
            print_tree(graph, child, seen, level)

def print_parents(graph, node):
    """Display all the predecessor nodes from target"""
    for parent in graph.predecessors(node):
        edge_data = display_properties(graph.get_edge_data(parent, node))
        node_data = display_properties(graph.node[parent])
        print()
        pindent(edge_data, 0, coloring(edge_data))
        pindent(node_data, 0, coloring(node_data))

def main():
    """Provide navigation of the selected Glow objects
    """
    print()
    print("Generating directed graph...")
    start_time = time.time()
    graph = create_graph()
    end_time = time.time()
    elapsed_time = round(end_time - start_time)
    print("Graph generated in {} seconds".format(elapsed_time))
    print()
    print(nx.info(graph))

    # use this for example navigation
    page_guid = "0e604158-7756-49fd-84da-2f82d94c9069"
    print()
    print("Example node: {}".format(page_guid))
    print()
    print_tree(graph, page_guid)
    print()
    print("Node predecessors")
    print()
    print_parents(graph, page_guid)
    print()
    pdb.set_trace()

if __name__ == "__main__":
    main()
