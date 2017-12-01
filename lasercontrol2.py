#!/usr/bin/env python2
# coding=UTF-8

"""
This script allows for a user to control the laser and PSU.

This script will grab the UID from an NFC tag, verify that the UID is granted
access to the laser, then let the user actually do so.
"""
from __future__ import print_function, unicode_literals


__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"
__license__ = "MIT"

####---- Imports ----####
from subprocess import check_output

import sys
import os
import signal
import pwd
import time
import random
import crypt
import ttk
import logging
import logging.config

from threading import enumerate as thread_enum, active_count
from Queue import Empty
import yaml

from inotify.adapters import Inotify
from inotify.constants import IN_CLOSE_WRITE, IN_CREATE, IN_MODIFY

from Sender import Sender

try:
    import Tkinter as tk
    import tkMessageBox as messagebox
    import tkFileDialog as filedialog
except ImportError:
    import tkinter as tk
    import tkinter.messagebox as messagebox
    import tkinter.filedialog as filedialog
import pygubu
import wiringpi as GPIO


####---- Variables ----####
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
# BCM pins for various functions
## SPI
### For reference, should we ever go back to using a python SPI protocol
#SPI = dict(cs=8, mosi=10, miso=9, sclk=11)
## Relays and other outputs
OUT_PINS = dict(laser=20, psu=21, grbl=27)
## Sensors and other inputs
IN_PINS = dict() # None currently

# Directory where the gcode files will be stored from Visicut
GDIR = "/home/users/Public"
GCODE_EXT = (".gcode",
             ".gc",
             ".nc",
             ".cnc",
             ".cng",
            )

# GRBL serial port
GRBL_SERIAL = "/dev/ttyAMA0"


####---- Classes ----####
class MainWindow(Sender):
    """Main window"""
    # pylint: disable=too-many-ancestors,too-many-instance-attributes
    def __init__(self):
        ## Sender methods
        Sender.__init__(self)
        ## Main window
        self.builder = builder = pygubu.Builder()
        builder.add_from_file(os.path.join(CURRENT_DIR, "MainWindow.ui"))
        self.mainwindow = builder.get_object("mainwindow")
        self.mainwindow.protocol("WM_DELETE_WINDOW", self.__shutdown)
        builder.connect_callbacks(self)
        ## Variables & Buttons
        self.var = {}
        variable_list = ["status",
                         "connect_b",
                         "psu_label",
                         "laser_label",
                         "filename",
                         "file_found",
                         "file_scan_auto",
                         "pos_x",
                         "pos_y",
                         "pos_z",
                         "progress_bar",
                        ]
        for var in variable_list:
            try:
                self.var[var] = builder.get_variable(var)
            except BaseException as ex:
                logger.warning("Variable not defined: %s", var)
        self.var["status"].set("Not Authorized")
        self.var["connect_b"].set("Connect")
        self.var["file_scan_auto"].set(1)
        self.monitor = Inotify()
        self.monitor.add_watch(GDIR, IN_CLOSE_WRITE)
        self.buttons = {}
        button_list = ["button_conn",
                       "button_home",
                       "button_soft_reset",
                       "button_unlock",
                       "button_reset_hard",
                       "check_psu",
                       "check_laser",
                       "button_start",
                       "button_pause",
                       "button_stop",
                       "file_scan",
                      ]
        for button in button_list:
            try:
                self.buttons[button] = builder.get_object(button)
            except BaseException as ex:
                logger.warning("Button not defined: %s", button)
        # All done
        logger.info("Window started")

    def _authorize(self):
        """Authorize the user, allowing them to do other functions"""
        firmware, name = initialize_nfc_reader()
        if not firmware and not name:
            messagebox.showerror("Unable to Authorize",
                                 "The PN532 was unable to initialize")
        retry = 3
        while retry:
            uid = get_uid_noblock()
            if not uid:
                # True/False are 1/0, so it works
                again = messagebox.askretrycancel("No UID found",
                                                  ("Could not find NFC tag."
                                                   "Try again?"))
                if again:
                    retry -= 1
                else:
                    return
            else:
                retry = 0
        if uid:
            verified = verify_uid(uid)
            if not verified:
                messagebox.showerror("Not Authorized",
                                     ("You do not have authorization to "
                                      "use this device."))
            try:
                username = get_user_uid(uid)
                realname = get_user_realname()
            except BaseException as ex:
                messagebox.showerror("Error:", ex)
            current_user = is_current_user(username)
            if not current_user:
                messagebox.showerror("Incorrect user",
                                     ("The provided NFC tag is not for the "
                                      "current user."))
            if current_user and uid and verified:
                try:
                    board_setup = gpio_setup()
                except BaseException as ex:
                    messagebox.showerror("GPIO Error:", ex)
                if board_setup:
                    _ = disable_relay(OUT_PINS['laser'])
                    _ = disable_relay(OUT_PINS['psu'])
                else:
                    messagebox.showerror("Failed", "Board not setup")
                    return
                # Let the buttons actually do something!
                self._activate_buttons()
                self._relay_states()
                logger.info("user %s authorized", username)
                self.var["status"].set("Authorized, not connected")
                messagebox.showinfo("Done",
                                    "Everything is setup, {}".format(realname))
            else:
                messagebox.showerror("Error", "Something went wrong")

    def _activate_buttons(self):
        """Enable the buttons"""
        for button in self.buttons.iterkeys():
            logger.debug("Enabling %s", button)
            try:
                self.buttons[button].state(["!disabled"])
            except ValueError:
                logger.exception("Failed to enable %s", button)
        logger.info("Buttons enabled")

    def _deactivate_buttons(self):
        """Enable the buttons"""
        for button in self.buttons.iterkeys():
            logger.debug("Disabling %s", button)
            try:
                self.buttons[button].state(["disabled"])
            except ValueError:
                logger.exception("Failed to disable %s", button)
        logger.info("Buttons disabled")

    def _relay_states(self):
        """Update the variables of the relay states"""
        self.var["laser_label"].set(relay_state(OUT_PINS['laser']))
        self.var["psu_label"].set(relay_state(OUT_PINS['psu']))

    def _switch_psu(self):
        self._switch_pin('psu')
        self._relay_states()

    def _switch_laser(self):
        self._switch_pin('laser')
        self._relay_states()

    def _switch_pin(self, item):
        """Change pin state & set laser/psu StringVar's"""
        logger.debug("Changing pin for %s", item)
        pin = OUT_PINS[item]
        switch_pin(pin)

    def _hard_reset(self):
        toggle_pin(OUT_PINS["grbl"])

    def _file_scanning(self):
        """Scan directory for files that have been recently written"""
        to_scan = self.var["file_scan_auto"].get()
        event = self.monitor.event_gen().next()
        if to_scan:
            logger.debug("Checking for created file...")
            if event is not None:
                filename = event[3]
                event_type = event[2]
                logger.debug("File creation detected: %s", filename)
                extension = os.path.splitext(filename)[1]
                if extension in GCODE_EXT: #and not loading:
                    logger.info("Auto-loading %s", filename)
                    self.var["file_found"].set("")
                    self._read_file(os.path.join(GDIR, filename))
        else:
            logger.debug("Not checking for files.")
        self.mainwindow.after(1000, self._file_scanning)

    def _select_filepath(self):
        """Use tkfiledialog to select the appropriate file"""
        valid_files = [("GCODE", ("*.gc",
                                  "*.gcode",
                                  "*.nc",
                                  "*.cnc",
                                  "*.ncg",
                                  "*.txt"),
                       ),
                       ("GCODE text", "*.txt"),
                       ("All", "*")
                      ]
        initial_dir = GDIR
        filepath = filedialog.askopenfilename(filetypes=valid_files,
                                              initialdir=initial_dir)
        self._read_file(filepath)

    def _read_file(self, filepath):
        """Take filepath, set filename StringVar"""
        self.var["filename"].set(os.path.basename(filepath))
        logger.debug("Reading %s into list", filepath)
        with open(filepath, 'rU') as gcode_file:
            self.file = []
            for line in gcode_file:
                logger.debug("Appending %s to self.file", line)
                self.file.append(line)
            logger.debug("self.file length: %d", len(self.file))

    def _open(self, device=GRBL_SERIAL):
        """Open serial device"""
        try:
            status = self._open_serial(device)
            logger.info("Opened serial: %s", status)
            self.buttons["button_conn"].configure(command=self._close)
            self.var["connect_b"].set("Disconnect")
            return status
        except BaseException:
            self.serial = None
            self.thread = None
            messagebox.showerror("Error Opening serial", sys.exc_info()[1])
            logger.exception("Failed to open serial")
        return False

    def _close(self):
        """Close serial device"""
        logger.info("Closing serial")
        self._close_serial()
        self.buttons["button_conn"].configure(command=lambda: self._open(GRBL_SERIAL))
        self.var["status"].set("Not Connected")
        self.var["connect_b"].set("Connect")

    def _update_status(self):
        msg = self.log
        self.var["status"].set(msg)
        if ("ALARM" or "ERROR") in msg:
            response, code, message = self.error.get_nowait()
            message = "{}\nSoft Reset and Unlock to continue".format(message)
            messagebox.showerror("{} {}".format(response, code),
                                 message)
        if isinstance(self.pos, tuple):
            self.var["pos_x"].set(self.pos[0])
            self.var["pos_y"].set(self.pos[1])
            self.var["pos_z"].set(self.pos[2])
        self.var["progress_bar"].set(self.progress)
        self.mainwindow.after(250, self._update_status)

    def _run(self):
        """Send gcode file to the laser"""
        logger.info("run() called")
        if self.serial is None:
            messagebox.showerror("Serial Error", "GRBL is not connected")
            logger.error("Serial device not set!")
            return
        self._init_run()
        logger.info("Lines to send: %d", len(self.file))
        self.max_size = float(len(self.file))
        for line in self.file:
            if line is not None:
                logger.debug("Queued line: %s", line)
                self.queue.put(line)
        self.queue.put(("DONE",))

    def __shutdown(self):
        message = """Are you sure you want to close?
        Note: Auth will be lost.
        """
        if messagebox.askokcancel("Quit?", message):
            self.monitor.remove_watch(GDIR)
            self.mainwindow.update_idletasks()
            self._close()
            self.mainwindow.destroy()
            shutdown()

    def run(self):
        self.mainwindow.after(0, self._update_status)
        self.mainwindow.after(0, self._file_scanning)
        self.mainwindow.mainloop()


####---- Generic Functions ----####
### NFC-related
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

### GPIO-related
def gpio_setup():
    """Set up GPIO for use, returns True/False if all setup successful

    Not only gets the GPIO for the board, but also sets the appropriate pins
    for output and input."""
    GPIO.wiringPiSetupGpio() # BCM mode
    message = None
    try:
        for _, pin in OUT_PINS.iteritems():
            logger.info("Configuring pin %d", pin)
            GPIO.pinMode(pin, GPIO.OUTPUT)
            GPIO.digitalWrite(pin, GPIO.HIGH)
    except BaseException as message:
        logger.exception("Failed to setup pins")
        raise
    if message:
        board = False
    else:
        board = True
    return board

def disable_relay(pin, disabled=True):
    """Take OUT pin, disable (by default) relay. Returns pin state.

    disabled=False will enable the relay."""
    if disabled:
        logger.debug("Disabling pin %d", pin)
        GPIO.digitalWrite(pin, GPIO.HIGH)
    else:
        logger.debug("Enabling pin %d", pin)
        GPIO.digitalWrite(pin, GPIO.LOW)
    return GPIO.digitalRead(pin)

def relay_state(pin):
    """Take in pin, return string state of the relay"""
    logger.debug("relay_state() for pin %s", pin)
    disabled = GPIO.digitalRead(pin)
    logger.debug("Pin %s disabled: %s", pin, disabled)
    state = "off"
    if not disabled:
        state = "on"
    logger.debug("Relay state for pin %s is %s", pin, state)
    return state

def switch_pin(pin):
    """Take pin, switch pin state"""
    logger.info("Switching pin %d", pin)
    cur_state = GPIO.digitalRead(pin)
    new_state = not cur_state
    GPIO.digitalWrite(pin, new_state)

def toggle_pin(pin):
    """Take pinn, switch pin states for short period of time"""
    logger.info("Toggling pin %d", pin)
    switch_pin(pin)
    time.sleep(0.25)
    switch_pin(pin)
    logger.debug("Pin %d toggled", pin)

####---- MAIN ----####
def main():
    """Main function"""
    root = MainWindow()
    root.run()

def shutdown():
    """Shutdown commands"""
    logger.debug("shutdown() called")
    try:
        _ = disable_relay(OUT_PINS['laser'])
        _ = disable_relay(OUT_PINS['psu'])
    except AttributeError as ex:
        logger.exception("Error shutting down GPIO")
        print("Something went wrong shutting down: {}".format(ex))
        print("The GPIO probably never even got initialized...")
    logger.info("%d thread(s) still alive: %s", active_count(), thread_enum())
    if active_count() > 1:
        logger.critical("CANNOT SHUTDOWN PROPERLY")

def handler_cli(signum, frame):
    """Signal handler"""
    logger.debug("handler_cli() called")
    print("Signal {}".format(signum))
    _ = frame
    shutdown()

def setup_logging(default_path='logging.yaml',
                  default_level=logging.INFO
                 ):
    """Setup logging configuration"""

    path = default_path
    if os.path.exists(path):
        with open(path, "rt") as conf_file:
            config = yaml.safe_load(conf_file.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

####---- BODY ----####
setup_logging()
logger = logging.getLogger(__name__) # pylint: disable=invalid-name
if __name__ == '__main__':
    signal.signal(signal.SIGHUP, handler_cli)
    signal.signal(signal.SIGINT, handler_cli)
    signal.signal(signal.SIGTERM, handler_cli)
    logger.debug("CLI signal handlers set up")

    main()
