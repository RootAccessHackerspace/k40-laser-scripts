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

from Sender import Sender

try:
    import Tkinter as tk
    import tkMessageBox as messagebox
except ImportError:
    import tkinter as tk
    import tkinter.messagebox as messagebox
import wiringpi as GPIO

####---- Variables ----####
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

# GRBL serial port
GRBL_SERIAL = "/dev/ttyAMA0"


####---- Classes ----####
class MainWindow(tk.Frame, Sender):
    """Main window"""
    # pylint: disable=too-many-ancestors
    def __init__(self, root, *args, **kwargs):
        ## Main window
        tk.Frame.__init__(self, root, *args, **kwargs)
        Sender.__init__(self)
        self.root = root
        self.root.geometry("400x200+0-5")
        self.root.resizable(width=False, height=False)
        self.grid()

        ## Sub-frame for just the GPIO controls
        self.gpio = ttk.Labelframe(self.root,
                                   text="GPIO Control",
                                   padding=5)
        self.gpio.grid(column=20, row=50, sticky="E", ipadx=5)
        ## Sub-frame for the GCode controls
        self.gcode = ttk.Labelframe(self.root,
                                    text="Gcode Control")
        self.gcode.grid(column=10, row=50, sticky="W", ipadx=5)
        ## Sub-frame for "status" controls
        self.conn = ttk.Frame(self.root)
        self.conn.grid(column=10, row=25, sticky="N")
        ### GPIO buttons
        self.gpio.button_auth = ttk.Button(self.gpio, text="Authorize")
        self.gpio.button_psu = ttk.Button(self.gpio, text="Power Supply")
        self.gpio.button_laser = ttk.Button(self.gpio, text="Laser")
        self.gpio.button_reset_hard = ttk.Button(self.gpio,
                                                 text="Hard Reset")
        #### Label for the state of the laser and PSU
        self.gpio.psu_label = tk.StringVar()
        self.gpio.label_psu = tk.Label(self.gpio,
                                       textvariable=self.gpio.psu_label)
        self.gpio.laser_label = tk.StringVar()
        self.gpio.label_laser = tk.Label(self.gpio,
                                         textvariable=self.gpio.laser_label)
        ### GCODE buttons
        self.gcode.image_play = tk.PhotoImage(file="button_play.gif")
        self.gcode.button_start = ttk.Button(self.gcode,
                                             text="Start",
                                             image=self.gcode.image_play,
                                             compound="top")
        self.gcode.image_pause = tk.PhotoImage(file="button_pause.gif")
        self.gcode.button_pause = ttk.Button(self.gcode,
                                             text="Pause",
                                             image=self.gcode.image_pause,
                                             compound="top")
        self.gcode.image_stop = tk.PhotoImage(file="button_stop.gif")
        self.gcode.button_stop = ttk.Button(self.gcode,
                                            text="Stop",
                                            image=self.gcode.image_stop,
                                            compound="top")
        ### Connection/Status buttons and label
        self.conn.label_status = tk.Label(self.conn, text="Status:")
        self.conn.status = tk.StringVar()
        self.conn.status_display = tk.Label(self.conn,
                                            textvariable=self.conn.status)
        self.conn.connect_b = tk.StringVar()
        self.conn.button_conn = ttk.Button(self.conn,
                                           textvariable=self.conn.connect_b)
        self.conn.button_home = ttk.Button(self.conn,
                                           text="Home")
        self.conn.button_reset_soft = ttk.Button(self.conn,
                                                 text="Soft Reset")
        self.conn.button_unlock = ttk.Button(self.conn,
                                             text="Unlock")

        self.__init_window()

    def __init_window(self):
        """Initialization of the GUI"""
        self.root.title("Laser Control")
        self.__create_buttons()

    def __create_buttons(self):
        """Make all buttons visible and set appropriate values"""
        # GPIO buttons
        self.gpio.button_auth.grid(row=10, column=10, sticky="W")
        self.gpio.button_auth.configure(command=self._authorize)

        self.gpio.button_psu.grid(row=20, column=10, sticky="W")
        self.gpio.button_psu.configure(command=(
            lambda: self._switch_pin('psu')))
        self.gpio.button_psu.state(["disabled"])
        self.gpio.label_psu.grid(row=20, column=20, sticky="W")

        self.gpio.button_laser.grid(row=30, column=10, sticky="W")
        self.gpio.button_laser.configure(command=(
            lambda: self._switch_pin('laser')))
        self.gpio.button_laser.state(["disabled"])
        self.gpio.label_laser.grid(row=30, column=20, sticky="W")

        self.gpio.button_reset_hard.grid(row=40, column=10, sticky="W")
        self.gpio.button_reset_hard.configure(command=(
            lambda: toggle_pin(OUT_PINS['grbl'])))
        self.gpio.button_reset_hard.state(["disabled"])

        # Gcode buttons
        self.gcode.button_start.grid(column=10, row=10)
        self.gcode.button_start.state(["disabled"])
        self.gcode.button_pause.grid(column=20, row=10)
        self.gcode.button_pause.state(["disabled"])
        self.gcode.button_stop.grid(column=30, row=10)
        self.gcode.button_stop.state(["disabled"])

        # Connection buttons
        self.conn.label_status.grid(column=30, row=5)
        self.conn.status_display.grid(column=31, row=5, columnspan=19)
        self.conn.status.set("Not Connected")
        self.conn.connect_b.set("Connect")
        self.conn.button_conn.configure(command=lambda: self.open(GRBL_SERIAL))
        self.conn.button_conn.grid(column=20, row=5)
        self.conn.button_conn.state(["disabled"])
        self.conn.button_home.grid(column=20, row=10)
        self.conn.button_home.state(["disabled"])
        self.conn.button_reset_soft.grid(column=30, row=10)
        self.conn.button_reset_soft.state(["disabled"])
        self.conn.button_unlock.grid(column=40, row=10)
        self.conn.button_unlock.state(["disabled"])

    def _switch_pin(self, item):
        pin = OUT_PINS[item]
        switch_pin(pin)
        self.gpio.laser_label.set(relay_state(OUT_PINS['laser']))
        self.gpio.psu_label.set(relay_state(OUT_PINS['psu']))

    def _authorize(self):
        """Authorize the user, allowing them to do other functions"""
        firmware, name = initialize_nfc_reader()
        if not firmware and not name:
            messagebox.showerror("Unable to Authorize",
                                 "The PN532 was unable to initialize")
        retry = True
        while retry:
            uid = get_uid_noblock()
            if not uid:
                retry = messagebox.askretrycancel("No UID found",
                                                  ("Could not find NFC tag."
                                                   "Try again?"))
            else:
                retry = False
        if uid:
            verified = verify_uid(uid)
            if not verified:
                messagebox.showerror("Not Authorized",
                                     ("You do not have authorization to "
                                      "use this device."))
        try:
            username = get_user_uid(uid)
            realname = get_user_realname()
        except BaseException, ex:
            messagebox.showerror("Error", ex)
        current_user = is_current_user(username)
        if not current_user:
            messagebox.showerror("Incorrect user",
                                 ("The provided NFC tag is not for the "
                                  "current user."))
        if current_user and uid and verified:
            try:
                board_setup = gpio_setup()
            except BaseException, ex:
                messagebox.showerror("GPIO Error", ex)
            if board_setup:
                _ = disable_relay(OUT_PINS['laser'])
                _ = disable_relay(OUT_PINS['psu'])
            # Let the GPIO buttons actually do something!
            self.gpio.button_psu.state(["!disabled"])
            self.gpio.psu_label.set(relay_state(OUT_PINS['psu']))
            self.gpio.button_laser.state(["!disabled"])
            self.gpio.laser_label.set(relay_state(OUT_PINS['laser']))
            self.gpio.button_reset_hard.state(["!disabled"])
            self.conn.button_conn.state(["!disabled"])
            messagebox.showinfo("Done",
                                "Everything is setup, {}".format(realname))
        else:
            messagebox.showerror("Error", "Something went wrong")

    def _activate_conn(self):
        """Enable the connection buttons"""
        self.conn.button_home.configure(command=self.home)
        self.conn.button_home.state(["!disabled"])
        self.conn.button_reset_soft.configure(command=Sender.soft_reset)
        self.conn.button_reset_soft.state(["!disabled"])
        self.conn.button_unlock.configure(command=Sender.unlock)
        self.conn.button_unlock.state(["!disabled"])

    def _deactivate_conn(self):
        """Enable the connection buttons"""
        self.conn.button_home.state(["disabled"])
        self.conn.button_reset_soft.state(["disabled"])
        self.conn.button_unlock.state(["disabled"])

    def open(self, device):
        """Open serial device"""
        try:
            status = Sender.open_serial(self, device)
            self._activate_conn()
            self.conn.button_conn.configure(command=self.close)
            self.conn.status.set("Connected")
            self.conn.connect_b.set("Disconnect")
            return status
        except BaseException:
            self.serial = None
            self.process = None
            messagebox.showerror("Error Opening serial", sys.exc_info()[1])
        return False

    def close(self):
        """Close serial device"""
        Sender.close_serial(self)
        self._deactivate_conn()
        self.conn.button_conn.configure(command=lambda: self.open(GRBL_SERIAL))
        self.conn.status.set("Not Connected")
        self.conn.connect_b.set("Connect")

    def home(self):
        return Sender.home(self)

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
            time.sleep(1)
    else:
        chip_firm, chip_name = None, None
    return (chip_firm, chip_name)

## NFC UID get
def _dummy_get_uid():
    """() -> random 4 byte hex string"""
    return "%08x" % random.randrange(16**8)

def get_uid_noblock(dummy=False):
    """Uses libnfc via /usr/bin/nfc-list to return NFCID or None if not
    just a single NFC tag is found"""
    # Fetch dummy if needed, mostly for testing purposes
    if dummy:
        uid_ascii = _dummy_get_uid()
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
    """Takes in a UID string, returns string of username."""
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
            GPIO.pinMode(pin, GPIO.OUTPUT)
            GPIO.digitalWrite(pin, GPIO.HIGH)
    except BaseException, message:
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
        GPIO.digitalWrite(pin, GPIO.HIGH)
    else:
        GPIO.digitalWrite(pin, GPIO.LOW)
    return GPIO.digitalRead(pin)

def relay_state(pin):
    """Take in pin, return string state of the relay"""
    disabled = GPIO.digitalRead(pin)
    state = "off"
    if not disabled:
        state = "on"
    return state

def switch_pin(pin):
    """Take pin, switch pin state"""
    cur_state = GPIO.digitalRead(pin)
    new_state = not cur_state
    GPIO.digitalWrite(pin, new_state)

def toggle_pin(pin):
    """Take pinn, switch pin states for short period of time"""
    switch_pin(pin)
    time.sleep(0.25)
    switch_pin(pin)

####---- MAIN ----####
def main():
    """Main function"""
    root = tk.Tk()
    MainWindow(root)
    root.protocol("WM_DELETE_WINDOW", lambda: handler_gui(root))
    root.mainloop()

def shutdown():
    """Shutdown commands"""
    try:
        _ = disable_relay(OUT_PINS['laser'])
        _ = disable_relay(OUT_PINS['psu'])
    except AttributeError as ex:
        print("Something went wrong shutting down: {}".format(ex))
        print("The GPIO probably never even got initialized...")
    sys.exit(0)

def handler_cli(signum, frame):
    """Signal handler"""
    print("Signal {}".format(signum))
    _ = frame
    shutdown()

def handler_gui(root):
    """Signal handler for Tkinter"""
    message = ("Are you sure you want to quit?\n"
               "Authorization will be lost, and the power supply & "
               "laser will be turned off.")
    if messagebox.askokcancel("Quit", message):
        root.destroy()
        shutdown()

####---- BODY ----####
if __name__ == '__main__':
    signal.signal(signal.SIGHUP, handler_cli)
    signal.signal(signal.SIGINT, handler_cli)
    signal.signal(signal.SIGTERM, handler_cli)

    main()
