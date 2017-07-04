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
import xml.etree.ElementTree as ET
import yaml

# external libraries
import networkx as nx

GLOW_OBJECTS = {
    "Formflow": {
        "path": "BPMWorkflowTmpl/*.yaml",
        "type": "Formflow",
        "fields": {
            "guid": "VM_PK",
            "name": "VM_Name",
            "is_active": "VM_IsActive",
            "entity": "VM_EntityType",
            "tasks": "BPMTaskTmpls"
            }
        },
    "Template": {
        "path": "BPMForm/*.yaml",
        "type": "Template",
        "fields": {
            "guid": "VZ_PK",
            "name": "VZ_FormID",
            "is_active": "VZ_IsActive",
            "entity": "VZ_EntityType",
            "data": "VZ_FormData"
            }
        },
    "Task": {
        "type": "Task",
        "fields": {
            "guid": "VR_PK",
            "name": "VR_Description",
            "is_active": "VR_IsActive",
            "task_type": "VR_Type",
            "template": "VR_VZ_Form",
            "formflow": "VR_VM_JumpToWorkflowTemplate"
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

        Also uses the friednly mapping such that
        if "foo" is mapped to "baz" then we can
        call my_obj.baz to obtain "bar"
        """
        field = attr
        if attr in self.fields.keys():
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
        return {k : self.values[v]
                for k, v in self.fields.iteritems()
                if v in self.values.keys()}


class XMLParser(object):
    # pylint: disable=too-few-public-methods
    """Glow Template XML parser
    """
    TOPICS = {
        "Text": "name",
        "Description": "description",
        "PagePK": "template",
        "Workflow": "formflow"
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
            if "ResKey" in e_dict.keys():
                ph_dict["guid"] = e_dict["ResKey"]
            if e_dict["Value"] and e_dict["Name"] in self.TOPICS.keys():
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
            if "path" in v.keys())

def create_graph():
    """Create directed graph of objects
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
                    if "template" in tile.keys():
                        graph.add_edge(glow_object.guid, tile["template"], tile)
                    elif "formflow" in tile.keys():
                        graph.add_edge(glow_object.guid, tile["formflow"], tile)
                continue
    return graph

def main():
    """Provide navigation of the selected Glow objects
    """
    graph = create_graph()

    print(nx.info(graph))
    pdb.set_trace()

if __name__ == "__main__":
    main()
