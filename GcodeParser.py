#!/usr/bin/env python
# coding=UTF-8
"""Module containing Gcode parsing functions"""
from __future__ import print_function

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"


####---- Imports ----####
import re
import logging

logger = logging.getLogger(__name__) #pylint: disable=invalid-name

# RegEx
WHITESPACE = re.compile(r"""
                        \s       # whitespace
                        |\(.*?\) # or anything inside parentheses
                        """, (re.VERBOSE | re.IGNORECASE))
RAPID = re.compile(r"""
                   G0?1        # G1 or G01
                   ([X|Y]      # X or Y...
                   \d+\.?\d+)  # followed by a number...
                   ([X|Y]      # and another X or Y...
                    \d+\.?\d+) # followed by a number...
                   """, (re.VERBOSE | re.IGNORECASE))

class GcodeFile(object):
    """A file of gcode"""
    def __init__(self, gcode_file=None):
        self.file = gcode_file
        self.flat_xy_gen = None
        self.gcode = None
        self.extrema = dict(X=[float("inf"), 0], Y=[float("inf"), 0],
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
        self.gcode = self.__convert_gcode_internal()

    def __convert_gcode_internal(self):
        """Convert gcode into format that can be easily manipulated"""
        logger.info("Converting file to internal format")
        with open(self.file, "rU") as gcode_file:
            logger.info("Reading %s", self.file)
            gcode = [WHITESPACE.sub("", line) for line in gcode_file]
            groups = (RAPID.match(line).groups()
                      for line in gcode
                      if bool(RAPID.match(line))
                     )
            self.flat_xy_gen = (xory for tup in groups for xory in tup)
            logger.debug("Generators created")
            self._calc_extrema_coords()
            self._calc_mid_coords()
            return gcode


    def _calc_extrema_coords(self):
        """Calculate min/max bounding values"""
        logger.info("Calculating extrema coordinates")
        for item in self.flat_xy_gen:
            num = float(item[1:])
            coord = item[0]
            if coord == "X":
                if num < self.extrema["X"][0]:
                    self.extrema["X"][0] = num
                if num > self.extrema["X"][1]:
                    self.extrema["X"][1] = num
            elif coord == "Y":
                if num < self.extrema["Y"][0]:
                    self.extrema["Y"][0] = num
                if num > self.extrema["Y"][1]:
                    self.extrema["Y"][1] = num
            else:
                logger.warning("Coordinate not for X or Y")
        self.extrema["UL"] = (self.extrema["X"][0],
                              self.extrema["Y"][0])
        self.extrema["DR"] = (self.extrema["X"][1],
                              self.extrema["Y"][1])
        logger.debug("Extrema: %s", self.extrema)

    def bounding_box_coords(self):
        """Take in file of gcode, return tuples of min/max bounding values"""
        if not self.file:
            logger.error("Load file first")
        if (None, None) in self.extrema.values():
            self.__convert_gcode_internal()
        logger.info("Corner extrema: %s & %s",
                    self.extrema["UL"], self.extrema["DR"])
        return (self.extrema["UL"], self.extrema["DR"])

    def box_gcode(self):
        """Return str G0 commands to bound gcode file"""
        if (None, None) in self.extrema.values():
            self.bounding_box_coords()
        gcode = ["G90", "G21"]
        logger.info("Using X/Y values of %s/%s",
                    self.extrema["X"], self.extrema["Y"])
        gcode.append("G0X{x}Y{y}".format(x=self.extrema["UL"][0],
                                         y=self.extrema["UL"][1]))
        gcode.append("G0X{x}Y{y}".format(x=self.extrema["DR"][0],
                                         y=self.extrema["UL"][1]))
        gcode.append("G0X{x}Y{y}".format(x=self.extrema["DR"][0],
                                         y=self.extrema["DR"][1]))
        gcode.append("G0X{x}Y{y}".format(x=self.extrema["UL"][0],
                                         y=self.extrema["DR"][1]))
        gcode.append("G0X{x}Y{y}".format(x=self.extrema["UL"][0],
                                         y=self.extrema["UL"][1]))
        logger.debug("gcode: %s", gcode)
        return gcode

    def _calc_mid_coords(self):
        """Calculate coordinates for middle of workpiece"""
        logger.info("Calculating mid values")
        if (None, None) in self.extrema.values():
            self.__convert_gcode_internal()
        self.mids["X"] = sum(self.extrema["X"]) / 2.0
        self.mids["Y"] = sum(self.extrema["Y"]) / 2.0

    def mid_coords(self):
        """Return (x,y) of coordinates of middle of file"""
        if (None, None) in self.extrema.values():
            self.__convert_gcode_internal()
        if None in self.mids.values():
            self._calc_mid_coords()
        return (self.mids["X"], self.mids["Y"])

    def corner_gcode(self, corner):
        """Return str G0 commands to go to corners of workpiece"""
        gcode = ["G21", "G90"]
        if corner == "ul":
            gcode.append("G0X{x}Y{y}".format(x=self.extrema["X"][0],
                                             y=self.extrema["Y"][0]))
        elif corner == "ur":
            gcode.append("G0X{x}Y{y}".format(x=self.extrema["X"][1],
                                             y=self.extrema["Y"][0]))
        elif corner == "dr":
            gcode.append("G0X{x}Y{y}".format(x=self.extrema["X"][1],
                                             y=self.extrema["Y"][1]))
        elif corner == "dl":
            gcode.append("G0X{x}Y{y}".format(x=self.extrema["X"][0],
                                             y=self.extrema["Y"][1]))
        elif corner == "c":
            gcode.append("G0X{x}Y{y}".format(x=self.mids["X"],
                                             y=self.mids["Y"]))
        else:
            gcode.append("G0X0Y0")
        return gcode


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    stress = GcodeFile("serial_stress_test.gcode") # pylint: disable=invalid-name
    print(stress.bounding_box_coords())
    print(stress.box_gcode())
