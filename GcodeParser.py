#!/usr/bin/env python
# coding=UTF-8
"""Module containing Gcode parsing functions"""

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"


####---- Imports ----####
from pygcode import Line, GCodeLinearMove

def bounding_box(gcode_file):
    """Take in file of gcode, return dict of max and min bounding values"""
    raise NotImplemented

def box_gcode(min_xy, max_xy):
    """Take in min/max coordinate tuples, return G0 commands to bound it"""
    raise NotImplemented

def mid_gcode(min_xy, max_xy):
    """Take in min/max coord tuples, return G0 to go to midpoint"""
    raise NotImplemented

