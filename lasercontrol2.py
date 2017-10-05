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
import curses

import Adafruit_GPIO as GPIO
import Adafruit_PN532 as PN532


####---- Variables ----####
# BCM pins for various functions
## SPI
spi = dict(cs=8, mosi=10, miso=9, sclk=11)
## Relays and other outputs
out_pins = dict(laser=20, psu=21, grbl=27)
## Sensors and other inputs
in_pins = dict() # None currently

####---- Generic Functions ----####
def initialize_nfc_reader(CS=spi['cs'], MOSI=spi['mosi'], MISO=spi['miso'], SCLK=spi['sclk']):
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

def get_uid_noblock(reader):
    """Takes a reader object and returns the hex UID of a tag, even if it's None"""
    uid_binary = reader.read_passive_target()
    if uid_binary is None:
        uid_ascii = uid_binary
    else:
        uid_ascii = binascii.hexlify(uid_binary)
    return uid_ascii

def get_uid_block(reader):
    """Takes a reader object and returns the UID of a tag, stopping script until UID is returned"""
    uid = None
    while uid is None:
        uid = get_uid_noblock(reader)
        time.sleep(0.5) # Prevent script from taking too much CPU time
    return uid

def _dummy_verify_uid(uid):
    """Takes a UID, verifies that it matches a dummy value, and returns True/False

    This is just a way of being able to check the other functions without
    having to implement the API calls yet (esp. since the API doesn't even
    exist yet)"""
    if uid is not None:
        return True
    else:
        return False

def verify_uid(uid):
    """Takes a UID, returns True/False depending on user permission"""
    
    return _dummy_verify_uid(uid) # No API to use yet for users

def gpio_setup():
    """Set up GPIO for use, returns Adafruit_GPIO class instance.
    
    Not only gets the GPIO for the board, but also sets the appropriate pins
    for output and input."""
    board = GPIO.get_platform_gpio()
    for item,pin in out_pins.iteritems():
        print("Setting pin {} to OUT".format(pin))
        try:
            board.setup(pin,GPIO.OUT)
        except:
            print("Something went wrong with setting up '{}' ({})".format(item,pin))
    return board

def disable_relay(board, pin, disabled=True):
    """Take GPIO instance and OUT pin, disable (by default) relay. Returns pin state.

    disabled=False will enable the relay."""
    if disabled:
        board.output(pin,GPIO.HIGH)
    else:
        board.output(pin,GPIO.LOW)
    return board.input(pin)

####---- Text functions ----####
def text_horizontal_border(stdscr, line):
    stdscr.addstr(line, 0, "+------------------------------------------------------------------------------+")

def text_frame(stdscr, message_list):
    """Takes in list of message lines and add them to the curses window.

    Each item of the list should be an individual line no more than 76 chars.
    Each item will be printed on its own line."""
    for line,message in enumerate(message_list):
        stdscr.addstr(line + 1, 0, "| {}".format(message))
        stdscr.addstr(line + 1, 78, " |")

####---- Test print() ----####
#reader, version = initialize_nfc_reader()
#print("{}\n{}".format(reader, version))

#print(get_uid_block(reader))

#for uid in [None, True, False, 1234567, "user id str", binascii.unhexlify("deadbeef")]:
#    print("{}: {}".format(str(uid), verify_uid(uid)))

#board = gpio_setup()
#print(board)

#print(disable_relay(board, out_pins['laser'], False))
#print(disable_relay(board, out_pins['laser'], True))

def main(stdscr):
    stdscr.clear()
    introduction = ["This is a test",
                    "of the emergency",
                    "broadcast system."]
    text_horizontal_border(stdscr, 0)
    text_frame(stdscr, introduction)
    text_horizontal_border(stdscr, len(introduction)+1)
    stdscr.refresh()
    stdscr.getkey()

curses.wrapper(main)
