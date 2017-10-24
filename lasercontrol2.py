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
import os
import pwd
import binascii
import time
import curses
import textwrap
import random
import crypt

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
# For the GPIO
BOARD = None

####---- Generic Functions ----####
### NFC-related
def initialize_nfc_reader(stdscr,
                          cslv=SPI['cs'],
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
            msg = "Failed to detect reader. " \
                    "Check pin assignments and connections"
            error_message(stdscr, msg)

    # Make sure reader is functioning (_ is the IC)
    _, version, revision, support = reader.get_firmware_version()
    if (version is None) or (revision is None):
        error_message(stdscr, "Something went wrong")

    # Configure reader to accept Mifare cards (and all cards, really)
    configured = False
    while not configured:
        try:
            reader.SAM_configuration()
            configured = True
        except RuntimeError:
            error_message(stdscr, "Something went wrong during configuration.")

    return reader, "{}.{}.{}".format(version, revision, support)

## NFC UID get
def _dummy_get_uid():
    """() -> random 4 byte hex string"""
    return "%08x" % random.randrange(16**8)

def get_uid_noblock(reader, dummy=False):
    """Takes a reader object and returns the hex UID of a tag,
    even if it's None"""
    # Fetch dummy if needed, mostly for testing purposes
    if dummy:
        uid_ascii = _dummy_get_uid()
        return uid_ascii
    else:
        uid_binary = reader.read_passive_target()
    # uid_binary is None if dummy, but that doesn't affect us overall
    if uid_binary is None:
        uid_ascii = uid_binary
    else:
        uid_ascii = binascii.hexlify(uid_binary)
    return uid_ascii

def get_uid_block(reader, dummy=False):
    """Takes a reader object and returns the UID of a tag, stopping
    script until UID is returned"""
    uid = None
    while uid is None:
        uid = get_uid_noblock(reader, dummy) # Just pass the dummy argument
        time.sleep(0.5) # Prevent script from taking too much CPU time
    return uid

## NFC UID verify
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

def get_user_uid(uid, cuid_file="/etc/pam_nfc.conf", dummy=False):
    """Takes in a UID string, returns string of user name."""
    if not dummy:
        if os.getuid() != 0:
            raise OSError("Check your priviledge")
    cuidexist = os.path.isfile(cuid_file)
    if not cuidexist:
        raise IOError("Not a valid password file")

    with open(cuid_file, "r") as cryptuids:
        crypteduid = crypt.crypt(uid, 'RC')
        username = None
        for line in cryptuids:
            if crypteduid in line:
                username = line.split(" ")[0]
    return username

def is_current_user(username):
    """Takes in a username, returns whether logged-in user"""
    return username == os.environ['SUDO_USER']

def get_user_realname():
    """Returns a string of the current user's real name"""
    cur_uid = os.getuid()
    gecos = pwd.getpwuid(cur_uid)[4]
    real_name = gecos.split(",")[0]
    return real_name

### GPIO-related
def gpio_setup(stdscr, quiet=True):
    """Set up GPIO for use, returns Adafruit_GPIO class instance.

    Not only gets the GPIO for the board, but also sets the appropriate pins
    for output and input."""
    board = GPIO.get_platform_gpio()
    for item, pin in OUT_PINS.iteritems():
        if not quiet:
            error_message(stdscr, "Setting pin {} to OUT".format(pin))
        # Actually try now
        try:
            board.setup(pin, GPIO.OUT)
        except NameError:
            message = "Invalid module defined for GPIO assignment"
            error_message(stdscr, message)
        except ValueError:
            message = "Invalid pin value ({})".format(pin)
            error_message(stdscr, message)
        except AttributeError:
            message = "Invalid GPIO assignment for {}".format(item)
            error_message(stdscr, message)
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

def switch_pin(board, pin):
    """Take GPIO instance and pin, switch pin state"""
    cur_state = board.input(pin)
    new_state = not cur_state
    board.output(pin, new_state)

def toggle_pin(board, pin):
    """Take GPIO instance and pin, switch pin states for short period of time"""
    switch_pin(board, pin)
    time.sleep(0.25)
    switch_pin(board, pin)

####---- Text functions ----####
def error_message(stdscr, error):
    """(curses.window, message string) -> None

    This function should take in (essentially) an error message string
    and do a little "pop-up" style curses window with the error message.
    The user can then either dismiss the error or halt the program.
    """
    curses.curs_set(0)
    # Create sub-window
    subscr = stdscr.subwin(10, 60, 5, 10)
    subscr.bkgd(" ", curses.A_REVERSE)
    subscr.box()
    subscr.refresh()
    # Display error text
    text_frame(error, subscr)
    subscr.refresh()
    # List options
    subscr.addstr(9, 9, "Continue (any)")
    subscr.addstr(9, 41, "Quit (q)")
    subscr.refresh()

    response = subscr.getkey()
    if response == "q":
        raise KeyboardInterrupt
    else:
        subscr.erase()
        subscr.bkgd(" ", curses.color_pair(0))
        subscr.refresh()

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

def machine_status(stdscr, y_offset):
    """Prints machine state, returns dictionary of number assignments"""
    # Calculate the center of where each item will go
    # Don't forget this this is essentially a fencepost problem
    slices = len(OUT_PINS) + 1
    x_max = stdscr.getmaxyx()[1]
    x_location = [x*x_max/slices for x in range(1, slices+1)]
    pin_disabled = [BOARD.input(pin) for pin in OUT_PINS.itervalues()]
    # Print pin name and a number below it
    enumerated_items = dict(enumerate(OUT_PINS))
    for place, item in enumerated_items.iteritems():
        start_x = x_location[place] - len(item)/2 - 1
        stdscr.addstr(y_offset,
                      start_x,
                      item,
                      curses.color_pair(2+pin_disabled[place]))
        stdscr.addstr(y_offset+1, x_location[place]-2, "({})".format(place))
    return enumerated_items

####---- MAIN ----####
def main(stdscr):
    """Main function. Run in curses.wrapper()"""

    global BOARD
    intro = "This program will allow you to change the state of the " \
            "laser and PSU, and reset the GRBL board (to act as a reset " \
            "button).\n\nSearching for NFC tag...\n\n\n"

    # Success/failure color pairs
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)

    stdscr.clear()
    stdscr.resize(20, 80) # 20 rows, 80 cols
    curses.curs_set(0) # Cursor should be invsisible

    # Initialize reader and GPIO pins
    reader, _ = initialize_nfc_reader(stdscr)
    BOARD = gpio_setup(stdscr)
    _ = disable_relay(BOARD, OUT_PINS['laser'])
    _ = disable_relay(BOARD, OUT_PINS['psu'])

    # Welcome, welcome, one and all...
    text_frame(intro, stdscr)
    stdscr.box()
    stdscr.refresh()

    y_offset, _ = stdscr.getyx()
    while True:
        user_id = get_uid_block(reader, dummy=False)
        nfc_id = "Your NFC UID is 0x{}, correct? [y/n]".format(user_id)
        text_frame(nfc_id, stdscr, offset=y_offset)
        stdscr.refresh()
        response = stdscr.getkey()
        if response == "y":
            break

    # Next: Verify UID (esp. that it belongs to the logged in user, then
    # attempt to turn on PSU and laser.
    # Make sure that the laser constantly requires the presence of the tag,
    # otherwise turn it off.

    y_offset, _ = stdscr.getyx()
    while True:
        # We don't except the user to ever have to press "n", since that
        # would imply that there is something wrong with get_user_uid().
        # TO DO: There might actually be something wrong with get_user_uid(),
        # if two users have the same NFC tag. Although this may not be an
        # actual problem, and just something that arises during testing.
        username = get_user_uid(user_id)
        user_string = "You are user {}, correct? [y/n]".format(username)
        text_frame(user_string, stdscr, y_offset)
        stdscr.refresh()
        response = stdscr.getkey()
        if response == "y":
            if not is_current_user(username):
                raise SystemExit("Invalid user+key")
            break
    # Make sure that they aren't using someone else's NFC tag
    user_string = "{} ({})".format(get_user_realname(), username)
    y_offset, _ = stdscr.getyx()
    user_verified = verify_uid(user_id)
    if user_verified:
        text_frame(user_string, stdscr, -1, mode=curses.color_pair(2))
    else:
        raise SystemExit("Not authorized user")
    text_frame("Let's get the laser going!", stdscr, y_offset)
    stdscr.refresh()

    while True:
        assignments = machine_status(stdscr, 15)
        stdscr.refresh()
        response = stdscr.getkey()
        try:
            int_resp = int(response)
            item = assignments[int_resp]
            if item == 'grbl':
                toggle_pin(BOARD, OUT_PINS[item])
            else:
                switch_pin(BOARD, OUT_PINS[item])
        except ValueError:
            pass
        except KeyError:
            pass
        stdscr.refresh()

    stdscr.getkey()

def shutdown():
    """Shutdown commands"""
    _ = disable_relay(BOARD, OUT_PINS['laser'])
    _ = disable_relay(BOARD, OUT_PINS['psu'])
    sys.exit(0)


####---- BODY ----####
if __name__ == '__main__':
    try:
        print("Starting up curses wrapper...")
        curses.wrapper(main)
        print("Shutting down after a hard day...")
        shutdown()
    except KeyboardInterrupt:
        print("Shutting down...")
        shutdown()
    except SystemExit as ex:
        print(ex)
        shutdown()
