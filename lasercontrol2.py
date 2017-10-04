#!/usr/bin/env python2
# coding=UTF-8

"""
This script allows for a user to control the laser and PSU.

This script will grab the UID from an NFC tag, verify that the UID is granted
access to the laser, then let the user actually do so.
"""


####---- Imports ----####
from __future__ import print_function

import binascii

import Adafruit_GPIO as GPIO
import Adafruit_PN532 as PN532


####---- Variables ----####
# BCM pins for various functions
## SPI
CS = 8
MOSI = 10
MISO = 9
SCLK = 11
## Relays
LASER = 20
PSU = 21
## GRBL
GRBL = 27

####---- Generic Functions ----####
