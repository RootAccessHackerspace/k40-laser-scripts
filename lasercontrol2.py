#!/usr/bin/env python2
# coding=UTF-8

"""
This script allows for a user to control the laser and PSU.

This script will grab the UID from an NFC tag, verify that the UID is granted
access to the laser, then let the user actually do so.
"""


####---- Imports ----####
from __future__ import print_function

import sys
import binascii
import time
import curses
import textwrap

import Adafruit_GPIO as GPIO
import Adafruit_PN532 as PN532


####---- Variables ----####
# BCM pins for various functions
## SPI
SPI = dict(cs=8, mosi=10, miso=9, sclk=11)
## Relays and other outputs
OUT_PINS = dict(laser=20, psu=21, grbl=27)
## Sensors and other inputs
IN_PINS = dict() # None currently

####---- Generic Functions ----####
def initialize_nfc_reader(cslv=SPI['cs'],
                          mosi=SPI['mosi'],
                          miso=SPI['miso'],
                          sclk=SPI['sclk']):
    """Take in pin assignments, return class instance and firmware version"""

    reader = PN532.PN532(cs=cslv, mosi=mosi, miso=miso, sclk=sclk)
    success = False
    while not success:
        try:
            reader.begin()
            success = True
        except RuntimeError:
            print("Failed to detect reader. "\
                  "Check pin assignments and connections.")
            time.sleep(2)

    # Make sure reader is functioning (_ is the IC)
    _, version, revision, support = reader.get_firmware_version()
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
    """Takes a reader object and returns the hex UID of a tag,
    even if it's None"""
    uid_binary = reader.read_passive_target()
    if uid_binary is None:
        uid_ascii = uid_binary
    else:
        uid_ascii = binascii.hexlify(uid_binary)
    return uid_ascii

def get_uid_block(reader):
    """Takes a reader object and returns the UID of a tag, stopping
    script until UID is returned"""
    uid = None
    while uid is None:
        uid = get_uid_noblock(reader)
        time.sleep(0.5) # Prevent script from taking too much CPU time
    return uid

def _dummy_verify_uid(uid):
    """Takes a UID, verifies that it matches a dummy value,
    and returns True/False

    This is just a way of being able to check the other functions without
    having to implement the API calls yet (esp. since the API doesn't even
    exist yet)"""
    return bool(uid)

def verify_uid(uid):
    """Takes a UID, returns True/False depending on user permission"""
    return _dummy_verify_uid(uid) # No API to use yet for users

def gpio_setup():
    """Set up GPIO for use, returns Adafruit_GPIO class instance.

    Not only gets the GPIO for the board, but also sets the appropriate pins
    for output and input."""
    board = GPIO.get_platform_gpio()
    for item, pin in OUT_PINS.iteritems():
        print("Setting pin {} to OUT".format(pin))
        try:
            board.setup(pin, GPIO.OUT)
        except NameError:
            message = "Invalid module defined for GPIO assignment"
            print(message)
        except ValueError:
            message = "Invalid pin value ({})".format(pin)
            print(message)
        except AttributeError:
            message = "Invalid GPIO assignment for {}".format(item)
            print(message)
    return board

def disable_relay(board, pin, disabled=True):
    """Take GPIO instance and OUT pin, disable (by default) relay.
    Returns pin state.

    disabled=False will enable the relay."""
    if disabled:
        board.output(pin, GPIO.HIGH)
    else:
        board.output(pin, GPIO.LOW)
    return board.input(pin)

####---- Text functions ----####
def error_message(stdscr, error):
    """(curses.window, message string) -> None

    This function should take in (essentially) an error message string
    and do a little "pop-up" style curses window with the error message.
    The user can then either dismiss the error or halt the program.
    """
    curses.curs_set(0)
    #x_cur, y_cur = stdscr.getyx() # Save these for later...
    curses.flash() # Visual bell, let's get started!
    # Create sub-window
    subscr = stdscr.subwin(10, 60, 5, 10)
    subscr.bkgd(" ", curses.A_REVERSE)
    subscr.box()
    subscr.refresh()

    # Display error text
    text_frame(error, subscr)
    subscr.refresh()
    # List options
    subscr.addstr(9, 12, "Continue")
    subscr.addstr(9, 41, "Quit (q)")
    subscr.refresh()

    response = subscr.getkey()
    if response == "q":
        raise KeyboardInterrupt
    else:
        subscr.erase()
        subscr.bkgd(" ", curses.color_pair(0))
        stdscr.refresh()

def verify_text_length(message_list, length=76):
    """Takes in a list of messages, returns True if all items are appropriate
    length, first item number and length otherwise"""
    failures = []
    for position, message in enumerate(message_list):
        message_length = len(message)
        if message_length > length:
            failures.append((position, message_length))

    if failures:
        return failures
    # No need for 'else' since it'll return no matter what
    return True

def text_horizontal_border(stdscr, line):
    """Create horizontal text border on line. DEPRECATED"""
    stdscr.hline(line, 0, "+", 80)
    stdscr.hline(line, 1, "-", 78) # Cover middle with '-'

def text_frame(message, stdscr, offset=0, mode=None):
    """Takes in string and add them to the curses window, wrap as neccessary."""

    for line_str in message.split("\n"):
        message_list = textwrap.wrap(line_str, 76)
        for line, text in enumerate(message_list):
            if mode:
                stdscr.addstr(offset + line + 1, 2, text, mode)
            else:
                stdscr.addstr(offset + line + 1, 2, text)
        if not message_list: # If the list is empty, add 1 manually
            offset += 1
        else:
            offset += len(message_list)




####---- Test print() ----####
#reader, version = initialize_nfc_reader()
#print("{}\n{}".format(reader, version))

#print(get_uid_block(reader))

#for uid in [None, True, False, 1234567,
#            "user id str", binascii.unhexlify("deadbeef")]:
#    print("{}: {}".format(str(uid), verify_uid(uid)))

#board = gpio_setup()
#print(board)

#print(disable_relay(board, out_pins['laser'], False))
#print(disable_relay(board, out_pins['laser'], True))

def main(stdscr):
    """Main function. Run in curses.wrapper()"""

    # Let's call this color pair "reverse"
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)

    intro = "This program will allow you to change the state of the " \
            "laser and PSU, and reset the GRBL board (if you really need " \
            "to).\n\nSearching for NFC tag...\n\n\n"

    stdscr.clear()
    stdscr.resize(20, 80)

    error_message(stdscr, "message")
    text_frame(intro, stdscr)
    stdscr.box()
    stdscr.refresh()
    error_message(stdscr, "continue?")

    reader, _ = initialize_nfc_reader()
    user_id = get_uid_block(reader)

    y_offset, _ = stdscr.getyx()
    nfc_id = "Your NFC UID is 0x{}".format(user_id)
    text_frame(nfc_id, stdscr, offset=y_offset)
    error_message(stdscr, "Let's do this thing, {}".format(user_id))

    y_offset, _ = stdscr.getyx()
    text_frame("\nPress any key to continue...", stdscr, offset=y_offset)
    stdscr.refresh()

    # Next: Verify UID (esp. that it belongs to the logged in user, then
    # attempt to turn on PSU and laser.
    # Make sure that the laser constantly requires the presence of the tag,
    # otherwise turn it off.

    stdscr.getkey()


if __name__ == '__main__':
    try:
        print("Starting up curses wrapper...")
        curses.wrapper(main)
        print("Shutting down after a hard day...")
    except KeyboardInterrupt:
        print("Shutting down...")
        try:
            sys.exit(0)
        except SystemExit:
            sys.exit(0)
