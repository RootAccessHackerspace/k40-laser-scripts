#!/usr/bin/env python
# coding=UTF-8
"""Module containing Gcode parsing functions"""

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"


####---- Imports ----####
from pygcode import Line, GCodeLinearMove

class GcodeFile(object):
    """A file of gcode"""
    def __init__(self, gcode_file=[]):
        self.file = gcode_file
        self.gcode = []
        self.extrema = dict(X=(None, None), Y=(None, None),
                            UL=(None, None), DR=(None, None),
                           )
        self.mids = dict(X=None, Y=None)
        if self.file and not self.gcode:
            self.__convert_gcode_internal()

    def add_file(self, gcode_file):
        """Read in a file of Gcode"""
        self.file = gcode_file
        self.__convert_gcode_internal()

    def __convert_gcode_internal(self):
        """Convert gcode into format that can be easily manipulated"""
        for line in self.file:
            self.gcode.append(Line(line))

    def bounding_box(self):
        """Take in file of gcode, return tuples of min/max bounding values"""
        if self.file or self.gcode:
            logger.error("Load file first")
            return None
        if (None, None) in self.extrema.values():
            params = [p.get_param_dict()
                      for p in self.gcode
                      if p.word == "G01"]
            x_pos = [p["X"] for p in params]
            y_pos = [p["Y"] for p in params]
            self.extrema["X"] = (min(x_pos), max(x_pos))
            self.extrema["Y"] = (min(y_pos), max(y_pos))
            self.extrema["UL"] = (self.extrema["X"][0],
                                  self.extrema["Y"][0])
            self.extrema["DR"] = (self.extrema["X"][1],
                                  self.extrema["Y"][1])
        return (self.extrema["UL"], self.extrema["DR"])

    def box_gcode(self):
        """Return G0 commands to bound gcode file"""
        gcode = []
        gcode.append(GCodeLinearMove(X=self.extrema["X"][0],
                                     Y=self.extrema["Y"][0])) #UL
        gcode.append(GCodeLinearMove(X=self.extrema["X"][0],
                                     Y=self.extrema["Y"][1])) #UR
        gcode.append(GCodeLinearMove(X=self.extrema["X"][1],
                                     Y=self.extrema["Y"][1])) #DR
        gcode.append(GCodeLinearMove(X=self.extrema["X"][1],
                                     Y=self.extrema["Y"][0])) #DL
        gcode.append(GCodeLinearMove(X=self.extrema["X"][0],
                                     Y=self.extrema["Y"][0])) #UL cycle
        # Convert from GCodeLinearMove class to string
        gcode = [str(line) for line in gcode]
        return gcode

    def mid_gcode(min_xy, max_xy):
        raise NotImplemented

