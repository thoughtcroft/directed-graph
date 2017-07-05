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

GLOW_OBJECTS = {
    "Formflow": {
        "path": "BPMWorkflowTmpl/*.yaml",
        "type": "Formflow",
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
    "Template": {
        "path": "BPMForm/*.yaml",
        "type": "Template",
        "fields": {
            "guid":        "VZ_PK",
            "name":        "VZ_FormID",
            "entity":      "VZ_EntityType",
            "form_factor": "VZ_FormFactor",
            "is_active":   "VZ_IsActive",
            "type":        "VZ_FormType",
            "data":        "VZ_FormData"
            }
        },
    "Task": {
        "type": "Task",
        "fields": {
            "guid":        "VR_PK",
            "name":        "VR_Description",
            "entity":      "VR_DataContextOverride",
            "task_type":   "VR_Type",
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
        for attr in ("data", "tasks"):
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
            if "ResKey" in e_dict:
                ph_dict["guid"] = e_dict["ResKey"]
            if e_dict["Value"] and e_dict["Name"] in self.TOPICS:
                key = self.TOPICS[e_dict["Name"]]
                ph_dict[key] = e_dict["Value"]
        return ph_dict


# global functions

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

            if glow_object.type == "Formflow" and glow_object.tasks:
                for task in glow_object.tasks:
                    go_task = GlowObject(GLOW_OBJECTS["Task"], task)
                    if go_task.task_type == "FRM":
                        graph.add_edge(glow_object.guid, go_task.template, go_task.map())
                    elif go_task.task_type == "JMP":
                        graph.add_edge(glow_object.guid, go_task.formflow, go_task.map())
                continue

            if glow_object.type == "Template" and glow_object.data:
                xml_parser = XMLParser(glow_object.data)
                for tile in xml_parser.iterfind("Tile"):
                    tile["type"] = "Tile"
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
    """Indent print by specified level"""
    print("{}{}{}".format(level, "  " * level, text))

def print_tree(graph, parent, seen=None, level=0):
    """Display all the reachable nodes from target"""
    if seen is None:
        seen = []
    seen.append(parent)
    pindent(graph.node[parent], level)
    level += 1
    for child in graph.successors(parent):
        print()
        edge_data = graph.get_edge_data(parent, child)
        pindent(edge_data, level)
        if child in seen:
            pindent(" {} already seen".format(child), level)
        else:
            print_tree(graph, child, seen, level)


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
    pdb.set_trace()

if __name__ == "__main__":
    main()
