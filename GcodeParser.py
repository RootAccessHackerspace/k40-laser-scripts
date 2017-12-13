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
    def __init__(self, gcode_file=None):
        self.file = gcode_file
        self.gcode = []
        self.extrema = dict(X=(None, None), Y=(None, None),
                            UL=(None, None), DR=(None, None),
                           )
        self.mids = dict(X=None, Y=None)
        if self.file and not self.gcode:
            logger.debug("Converting file to gcode on init")
            self.add_file(gcode_file)
        logger.info("GcodeFile initialized!")

    def add_file(self, gcode_file):
        """Read in a file of Gcode"""
        logger.info("File added")
        self.file = gcode_file
        self.__convert_gcode_internal()

    def __convert_gcode_internal(self):
        """Convert gcode into format that can be easily manipulated"""
        logger.info("Converting file to internal format")
        with open(self.file, "rU") as gcode_file:
            logger.info("Reading %s", self.file)
            for line in gcode_file:
                logger.debug("raw line: %sLine(line): %s", line, Line(line))
                self.gcode.append(Line(line))

    def _calc_extrema_coords(self):
        """Calculate min/max bounding values"""
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
        logger.debug("Extrema: %s", self.extrema)

    def bounding_box_coords(self):
        """Take in file of gcode, return tuples of min/max bounding values"""
        if not self.file:
            logger.error("Load file first")
            return None
        elif not self.gcode:
            self.__convert_gcode_internal()
        if (None, None) in self.extrema.values():
            self._calc_extrema_coords()
        logger.info("Corner extrema: %s & %s", self.extrema["UL"], self.extrema["DR"])
        return (self.extrema["UL"], self.extrema["DR"])

    def box_gcode(self):
        """Return str G0 commands to bound gcode file"""
        if (None, None) in self.extrema.values():
            self.bounding_box_coords()
        gcode = []
        logger.info("Using X/Y values of %s/%s", self.extrema["X"], self.extrema["Y"])
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
        logger.info("Rapid moves: %s", gcode_str)
        return gcode_str

    def _calc_mid_coords(self):
        """Calculate coordinates for middle of workpiece"""
        logger.info("Calculating mid values")
        if (None, None) in self.extrema.values():
            self._calc_extrema_coords()
        self.mids["X"] = sum(self.extrema["X"]) / 2.0
        self.mids["Y"] = sum(self.extrema["Y"]) / 2.0

    def mid_coords(self):
        """Return (x,y) of coordinates of middle of file"""
        if (None, None) in self.extrema.values():
            self._calc_extrema_coords()
        if None in self.mids.values():
            self._calc_mid_coords()
        return (self.mids["X"], self.mids["Y"])

    def mid_gcode(self):
        """Return str G0 command to go to middle coordinates"""
        if None in self.mids.values():
            self._calc_mid_coords()
        return [str(GCodeRapidMove(X=self.mids["X"], Y=self.mids["Y"]))]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    stress = GcodeFile(open("serial_stress_test.gcode", "r"))
    print(stress.bounding_box_coords())
    print(stress.box_gcode())
