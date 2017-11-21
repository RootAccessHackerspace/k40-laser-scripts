#!/usr/bin/env python2
# coding=UTF-8
"""Module to communicate with GRBL via serial"""
# pylint: disable=line-too-long

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"

# This script is heavily influenced by bCNC
# https://github.com/vlachoudis/bCNC

####---- Import ----####
import multiprocessing
from multiprocessing import Process, Queue
from Queue import Empty

import sys
import re
import logging
import time
import datetime
import serial

logger = multiprocessing.log_to_stderr() #pylint: disable=invalid-name
logger.setLevel(logging.DEBUG)

#from GrblCodes import ALARM_CODES, ERROR_CODES

# Global variables
SERIAL_TIMEOUT = 0.1 # seconds
SERIAL_POLL = 0.25 # seconds
G_POLL = 10 # seconds
RX_BUFFER_SIZE = 128 # bytes
OUTPUT_LOG_QUEUE = True # Whether to write the log queue to a file

class Sender(object):
    """Class that controls access to GRBL"""
    # pylint: disable=too-many-instance-attributes
    # If we get many more than 8 though...
    def __init__(self):
        self.log = Queue() # What is returned from GRBL
        self.queue = Queue() # What to send to GRBL
        self.serial = None
        self.process = None

        self.running = False
        self._stop = False # Set to True to stop current run
        self._pause = False # Is it currently paused?
        # The reason _stop and _pause represent different conditions is
        # because of the way GRBL handles stopping/pausing.
        # If GRBL is stopped, GRBL clears its queue, so we no longer have a
        # reliable method of continuation. So by setting _stop = True, we can
        # clear our queue as well as stop GRBL.
        # However, GRBL will immediately pause if sent "!" at any time. It can
        # be resumed from the exact same position by sending "~", so there is
        # only a need to tracking whether GRBL is paused or not, as the queue
        # will remain the same.
        self._sum_command_lens = 0

    def open_serial(self, device):
        """Open serial port"""
        self.log.put(("Opening", str(datetime.datetime.now())))
        self.serial = serial.serial_for_url(device,
                                            baudrate=115200,
                                            bytesize=serial.EIGHTBITS,
                                            parity=serial.PARITY_NONE,
                                            stopbits=serial.STOPBITS_ONE,
                                            timeout=SERIAL_TIMEOUT,
                                            xonxoff=False,
                                            rtscts=False)
        # Toggle DTR to reset the arduino
        try:
            self.serial.setDTR(0)
            time.sleep(1)
            self.serial.setDTR(1)
            time.sleep(1)
        except IOError:
            pass
        self.serial.write(b"\n\n")
        self.process = Process(target=self.serial_io)
        self.process.start()
        return True

    def close_serial(self):
        """Close serial port"""
        self.log.put(("Closing", str(datetime.datetime.now())))
        if self.serial is None:
            return
        try:
            self.stop_run()
        except BaseException:
            pass
        self.process = None
        try:
            self.serial.close()
        except BaseException:
            raise
        self.serial = None
        if OUTPUT_LOG_QUEUE:
            self.__write_log_queue()
        return True

    def stop_run(self):
        """Stop the current run of Gcode"""
        logger.debug("Called Sender.stop_run()")
        logger.debug("Calling self.pause()")
        #self.pause()
        logger.info("Stopping run")
        #self._stop = True
        logger.debug("Purging Grbl")
        self.purge_grbl()
        self.log.put(("Stopped", str(datetime.datetime.now())))

    def purge_grbl(self):
        """Purge the buffer of grbl"""
        logger.debug("Called Sender.purge_grbl()")
        logger.debug("Sending control-code pause")
        self.serial.write(b"!") # Immediately pause
        self.serial.flush()
        time.sleep(1)
        logger.debug("Calling self.soft_reset()")
        self.soft_reset()
        logger.debug("Calling self.unlock()")
        self.unlock()
        logger.debug("Calling run_ended()")
        self.run_ended()
        self.log.put(("Grbl purged", str(datetime.datetime.now())))

    def run_ended(self):
        """Called when run is finished"""
        logger.debug("Called Sender.run_ended()")
        if self.running:
            logger.debug("self.running == True when run_ended()")
            self.log.put(("Run ended", str(datetime.datetime.now())))
        logger.debug(("Run ended, pre", {"_pause": self._pause,
                                         "running": self.running,
                                        }
                     ))
        #self._pause = False
        #self.running = False
        logger.debug(("Run ended, post", {"_pause": self._pause,
                                          "running": self.running,
                                         }))

    def soft_reset(self):
        """Send GRBL reset command"""
        logger.debug("Called Sender.soft_reset()")
        if self.serial:
            self.serial.write(b"\030")
            logger.debug("Sent b'\030'")

    def unlock(self):
        """Send GRBL unlock command"""
        logger.debug("Called Sender.unlock()")
        self.send_gcode("$X")

    def home(self):
        """Send GRBL home command"""
        logger.debug("Called Sender.home()")
        self.send_gcode("$H")

    def send_gcode(self, command):
        """Send GRBL a Gcode/command line"""
        logger.debug("Called Sender.send_gcode() with %s", command)
        # Do nothing if not actually up
        logger.debug(("send_gcode", {"serial": self.serial,
                                     "running": self.running
                                    }))
        if self.serial: # and not self.running:
            logger.debug("self.serial == True")
            self.queue.put(command+"\n")

    def empty_queue(self):
        """Clear the queue"""
        logger.debug("Called Sender.empty_queue()")
        self.log.put(("Emptying Queue", self.queue.qsize()))
        while self.queue.qsize() > 0:
            logger.debug("Current qsize: %s", self.queue.qsize())
            try:
                self.queue.get_nowait()
            except Empty:
                logger.debug("Emptying Queue, qsize == 0")
                break

    def init_run(self):
        """Initialize a gcode run"""
        logger.debug("Called Sender.init_run()")
        logger.debug(("init_run, pre", {"_pause": self._pause,
                                        "running": self.running
                                       }))
        #self._pause = False
        #self.running = True
        logger.debug(("init_run, post", {"_pause": self._pause,
                                         "running": self.running
                                        }))
        logger.debug("Calling self.empty_queue()")
        self.empty_queue()
        self.log.put(("Initializing", str(datetime.datetime.now())))
        time.sleep(1) # Give everything a bit of time

    def pause(self):
        """Pause run"""
        logger.debug("Called Sender.pause()")
        logger.debug(("pause, pre", {"_serial": self.serial,
                                     "_pause": self._pause,
                                    }))
        if self.serial is None:
            return
        if self._pause:
            logger.debug("Calling self.resume() b/c _pause==True")
            self.resume()
        else:
            logger.debug("_pause==False, so pausing")
            self.log.put(("Pausing", str(datetime.datetime.now())))
            self.serial.write(b"!")
            self.serial.flush()
            self._pause = True
        logger.debug(("pause, post", {"_serial": self.serial,
                                      "_pause": self._pause,
                                     }))

    def resume(self):
        """Resume a run"""
        logger.debug("Called Sender.resume()")
        logger.debug(("resume, pre", {"_serial": self.serial,
                                      "_pause": self._pause,
                                     }))
        if self.serial is None:
            return
        self.log.put(("Resuming", str(datetime.datetime.now())))
        self.serial.write(b"~")
        self.serial.flush()
        self._pause = False
        logger.debug(("resume, post", {"_serial": self.serial,
                                       "_pause": self._pause,
                                      }))

    def serial_io(self):
        """Process to perform I/O on GRBL

        This is borrowed heavily from stream.py of the GRBL project"""
        logger.debug("serial_io started")
        line_count = 0
        error_count = 0
        gcode_count = 0
        char_line = []
        line = None

        while self.process:
            logger.debug(("serial_io pre DEBUG:",
                          {"line_count": line_count,
                           "error_Count": error_count,
                           "gcode_count": gcode_count,
                           "char_line": char_line,
                           "line": line,
                          }))
            try:
                line = self.queue.get_nowait()
            except Empty:
                line = None
            logger.debug(("serial_io dur DEBUG:", {"line": line}))
            if isinstance(line, tuple):
                line = None
            if line is not None:
                line = line.encode("ascii", "replace").strip()
                self.serial.write(line + "\n")
                while self.serial.in_waiting == 0:
                    # Wait for the "ok" hopefully
                    time.sleep(0.1)
                returned = self.serial.readline().strip()
                logger.debug(("serial_io dur DEBUG:", {"returned": returned}))
            logger.debug(("serial_io post DEBUG:",
                          {"line_count": line_count,
                           "error_Count": error_count,
                           "gcode_count": gcode_count,
                           "char_line": char_line,
                           "line": line,
                          }))


    def __write_log_queue(self):
        """Write the log queue to a file"""
        filename = "{}.log".format(str(datetime.datetime.now()))
        with open(filename, "w") as out_file:
            while self.log.qsize() > 0:
                try:
                    line = self.log.get_nowait()
                except BaseException:
                    pass
                out_line = "{}\n".format(line)
                out_file.write(out_line)
