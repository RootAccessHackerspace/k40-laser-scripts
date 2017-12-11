#!/usr/bin/env python2
"""All GPIO-related functions"""

####---- Imports ----####
import os
import crypt
import random
import pwd
import time
import logging

from subprocess import check_output

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"
__license__ = "MIT"


####---- Global Declaration ----####
logger = logging.getLogger(__name__) #pylint: disable=invalid-name


####---- Functions ----####
def initialize_nfc_reader():
    """Verify that correct board is present, return firmware ver & name.

    The function name is leftover from the initial function which used
    Adafruit_PN532 to get the NFC data."""
    for _ in range(3):
        # Do this 3 times, because sometimes the board doesn't
        # wake up fast enough...
        raw_lines = check_output(["/usr/bin/nfc-scan-device", "-v"])
        raw_lines = raw_lines.split("\n")
        try:
            chip_line = [line for line in raw_lines if "chip:" in line][0]
            chip_name = chip_line.split(" ")[1]
            chip_firm = chip_line.split(" ")[2]
            break
        except IndexError:
            logger.debug("PN532 board not awake yet...")
            time.sleep(1)
    else:
        chip_firm, chip_name = None, None
    return (chip_firm, chip_name)

## NFC UID get
def dummy_get_uid():
    """() -> random 4 byte hex string"""
    return "%08x" % random.randrange(16**8)

def get_uid_noblock(dummy=False):
    """Uses libnfc via /usr/bin/nfc-list to return NFCID or None if not
    just a single NFC tag is found"""
    # Fetch dummy if needed, mostly for testing purposes
    if dummy:
        uid_ascii = dummy_get_uid()
    else:
        # Only search for ISO14443A tags, and be verbose about it
        raw_output = check_output(["/usr/bin/nfc-list",
                                   "-t", "1",
                                   "-v"])
        iso_found = [line for line in raw_output.split("\n")
                     if "ISO14443A" in line]
        num_found = iso_found[0].split()[0]
        # Check for only one tag present
        if num_found != "1":
            logger.info("Incorrect number of tags: %s", num_found)
            uid_ascii = None
        else:
            nfcid_line = [line for line in raw_output.split("\n")
                          if "NFCID" in line]
            # The UID will be after the colon
            raw_uid = nfcid_line[0].split(":")[1]
            uid_list = raw_uid.split()
            uid_ascii = "".join([x for x in uid_list])
    return uid_ascii

def get_uid_block(dummy=False):
    """Returns the UID of a tag, stopping script until UID is returned"""
    uid = None
    while uid is None:
        uid = get_uid_noblock(dummy) # Just pass the dummy argument
        time.sleep(0.5) # Prevent script from taking too much CPU time
    return uid

## NFC UID verify
def dummy_verify_uid(uid):
    """Takes a UID, verifies that it matches a dummy value,
    and returns True/False

    This is just a way of being able to check the other functions without
    having to implement the API calls yet (esp. since the API doesn't even
    exist yet)"""
    return bool(uid)

def verify_uid(uid):
    """Takes a UID, returns True/False depending on user permission"""
    return dummy_verify_uid(uid) # No API to use yet for users

def get_user_uid(uid, cuid_file="/etc/pam_nfc.conf", dummy=False):
    """Takes in a UID string, returns string of username."""
    if not dummy:
        if os.getuid() != 0:
            logger.error("User does not have proper permission")
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
    cur_nam = os.getenv("SUDO_USER")
    gecos = pwd.getpwnam(cur_nam)[4]
    real_name = gecos.split(",")[0]
    return real_name
