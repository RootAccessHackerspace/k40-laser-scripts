#!/usr/bin/env python
# coding=UTF-8
"""Module containing Gcode parsing functions"""
from __future__ import print_function

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"


####---- Imports ----####
from pygcode import Line, GCodeRapidMove
import logging

logger = logging.getLogger(__name__) #pylint: disable=invalid-name

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
            logger.debug("Converting file to gcode on init")
            self.__convert_gcode_internal()

    def add_file(self, gcode_file):
        """Read in a file of Gcode"""
        logger.info("File added")
        self.file = gcode_file
        self.__convert_gcode_internal()

    def __convert_gcode_internal(self):
        """Convert gcode into format that can be easily manipulated"""
        logger.info("Converting file")
        for line in self.file:
            logger.debug("raw line: %sLine(line): %s", line, Line(line))
            self.gcode.append(Line(line))
        self.file.seek(0)

    def bounding_box_coords(self):
        """Take in file of gcode, return tuples of min/max bounding values"""
        if not self.file or not self.gcode:
            logger.error("Load file first")
            return None
        if (None, None) in self.extrema.values():
            logger.info("Calculating extrema coordinates")
            gcodes = [line.gcodes for line in self.gcode]
            logger.debug("gcodes: %s", gcodes)
            params = []
            for item in gcodes:
                logger.debug("item: %s", item)
                if len(item) > 0:
                    param_list = [x for x in item if x.word == "G01"]
                    logger.debug("param_list: %s", param_list)
                    try:
                        params.append(param_list[0].get_param_dict())
                    except IndexError:
                        logger.debug("Not a linear move")
                        pass
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
        """Return str G0 commands to bound gcode file"""
        if (None, None) in self.extrema.values():
            self.bounding_box_coords()
        gcode = []
        gcode.append(GCodeRapidMove(X=self.extrema["X"][0],
                                    Y=self.extrema["Y"][0])) #UL
        gcode.append(GCodeRapidMove(X=self.extrema["X"][0],
                                    Y=self.extrema["Y"][1])) #UR
        gcode.append(GCodeRapidMove(X=self.extrema["X"][1],
                                    Y=self.extrema["Y"][1])) #DR
        gcode.append(GCodeRapidMove(X=self.extrema["X"][1],
                                    Y=self.extrema["Y"][0])) #DL
        gcode.append(GCodeRapidMove(X=self.extrema["X"][0],
                                    Y=self.extrema["Y"][0])) #UL cycle
        # Convert from GCodeLinearMove class to string
        gcode_str = [str(line) for line in gcode]
        logger.debug("gcode: %s", gcode)
        logger.debug("gcode_str: %s", gcode_str)
        return gcode_str

    def mid_coords(self):
        """Return (x,y) of coordinates of middle of file"""
        if (None, None) in self.extrema.values():
            self.bounding_box_coords()
        if None in self.mids.values():
            logger.info("Calculating mid values")
            self.mids["X"] = sum(self.extrema["X"]) / 2.0
            self.mids["Y"] = sum(self.extrema["Y"]) / 2.0
        return (self.mids["X"], self.mids["Y"])

    def mid_gcode(self):
        """Return str G0 command to go to middle coordinates"""
        if None in self.mids.values():
            self.mid_coords()
        return [str(GCodeRapidMove(X=self.mids["X"], Y=self.mids["Y"]))]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    stress = GcodeFile(open("serial_stress_test.gcode", "r"))
    print(stress.bounding_box_coords())
    print(stress.box_gcode())
