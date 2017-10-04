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
import time

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
def initialize_nfc_reader(CS=CS, MOSI=MOSI, MISO=MISO, SCLK=SCLK):
    """Take in pin assignments, return class instance and firmware version"""

    reader = PN532.PN532(cs=CS, mosi=MOSI, miso=MISO, sclk=SCLK)
    success = False
    while not success:
        try:
            reader.begin()
            success = True
        except RuntimeError:
            print("Failed to detect reader. Check pin assignments and connections.")
            time.sleep(2)

    # Make sure reader is functioning
    ic, version, revision, support = reader.get_firmware_version()
    if (version is None) or (revision is None):
        print("Something went wrong")
    
    # Configure reader to accept Mifare cards (and all cards, really)
    configured = False
    while not configured:
        try:
            reader.SAM_configuration()
            configured = True
        except RuntimeError:
            print("Something went wrong during configuration.")
            time.sleep(2)

    return reader, "{}.{}.{}".format(version, revision, support)



print(initialize_nfc_reader())
