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
import sys
import os
import signal
import logging
import logging.config

from threading import enumerate as thread_enum, active_count
import yaml

from Sender import Sender
from NFCcontrol import initialize_nfc_reader, get_uid_noblock, verify_uid
from NFCcontrol import get_user_uid, get_user_realname, is_current_user
from GPIOcontrol import gpio_setup, disable_relay, relay_state
from GPIOcontrol import switch_pin, toggle_pin
from GcodeParser import GcodeFile
# Variable imports
from GPIOcontrol import OUT_PINS

try:
    import tkMessageBox as messagebox
    import tkFileDialog as filedialog
except ImportError:
    import tkinter.messagebox as messagebox
    import tkinter.filedialog as filedialog
import pygubu


####---- Variables ----####
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
# BCM pins for various functions
## SPI
### For reference, should we ever go back to using a python SPI protocol
#SPI = dict(cs=8, mosi=10, miso=9, sclk=11)

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
    # pylint: disable=too-many-ancestors,too-many-instance-attributes,too-few-public-methods
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
        self.file = []
        self.gcodefile = None
        self.var = {}
        variable_list = ["status",
                         "connect_b",
                         "psu_label",
                         "laser_label",
                         "filename",
                         "file_found",
                         "pos_x",
                         "pos_y",
                         "pos_z",
                         "progress_bar",
                        ]
        for var in variable_list:
            try:
                self.var[var] = builder.get_variable(var)
            except BaseException:
                logger.warning("Variable not defined: %s", var)
        self.var["status"].set("Not Authorized")
        self.var["connect_b"].set("Connect")
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
                       "move_ul",
                       "move_ur",
                       "move_dr",
                       "move_dl",
                       "move_c",
                       "button_box",
                       "button_testfire",
                      ]
        for button in button_list:
            try:
                self.buttons[button] = builder.get_object(button)
            except BaseException:
                logger.warning("Button not defined: %s", button)
        self.objects = {}
        other_objects = ["spinbox_power_level",
                        ]
        for obj in other_objects:
            try:
                self.objects[obj] = builder.get_object(obj)
            except BaseException:
                logger.warning("Object not defined: %s", obj)
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
        self.gcodefile = GcodeFile(filepath)
        self.file = self.gcodefile.gcode

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

    def _move(self, direction):
        """Send appropriate Gcode to move the laser according to direction"""
        logger.info("Moving %s", direction)
        if not self.file:
            messagebox.showerror("File", "File must be loaded first")
            return
        else:
            self.gcodefile.bounding_box_coords()
        if self.serial:
            if direction == "ul":
                pass
            if direction == "dl":
                pass
            if direction == "dr":
                pass
            if direction == "ur":
                pass
            if direction == "c":
                pass
            if direction == "box":
                for command in self.gcodefile.box_gcode():
                    self._send_gcode(command)
        else:
            messagebox.showerror("Device", "Please connect first")


    def _move_ul(self):
        self._move("ul")

    def _move_dl(self):
        self._move("dl")

    def _move_dr(self):
        self._move("dr")

    def _move_ur(self):
        self._move("ur")

    def _move_c(self):
        self._move("c")

    def _move_box(self):
        self._move("box")

    def _test_fire(self):
        percent = int(self.objects["spinbox_power_level"].get())
        level = float(percent)/100 * 500
        logger.info("Test firing @ %d percent of 500 (S%f)", percent, level)
        fire_list = ["M3 S{}".format(level),
                     "G1 Z-1 F600",
                     "M5",
                     "G0 Z0",
                    ]
        for command in fire_list:
            self._send_gcode(command)

    def __shutdown(self):
        message = """Are you sure you want to close?
        Note: Auth will be lost.
        """
        if messagebox.askokcancel("Quit?", message):
            self.mainwindow.update_idletasks()
            self._close()
            self.mainwindow.destroy()
            shutdown()

    def run(self):
        """Mainloop run method"""
        self.mainwindow.after(0, self._update_status)
        self.mainwindow.mainloop()

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
