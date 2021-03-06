#!/usr/bin/env python2
# coding=UTF-8
"""Module to communicate with GRBL via serial"""
# pylint: disable=line-too-long

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"

# This script is heavily influenced by bCNC
# https://github.com/vlachoudis/bCNC

####---- Import ----####
from collections import deque
from threading import Thread
from Queue import Queue, Empty

import re
import logging
import time
import datetime
import serial

logger = logging.getLogger(__name__) #pylint: disable=invalid-name

from GrblCodes import ALARM_CODES, ERROR_CODES

# Global variables
SERIAL_TIMEOUT = 0.1 # seconds
SERIAL_POLL = 0.25 # seconds
G_POLL = 10 # seconds
RX_BUFFER_SIZE = 128 # bytes
OUTPUT_LOG_QUEUE = False # Whether to write the log queue to a file

# RegEx
SPLITPOS = re.compile(r"[:,]")

class Sender(object):
    """Class that controls access to GRBL"""
    # pylint: disable=too-many-instance-attributes
    # If we get many more than 8 though...
    def __init__(self):
        #self.log = Queue() # What is returned from GRBL
        self.log = ""
        self.queue = Queue() # What to send to GRBL
        self.error = Queue() # Lengthy error messages
        self.pos = None # Will be (x,y,z) of machine position
        self.serial = None
        self.thread = None
        self.progress = 0.0
        self.max_size = 0.0

        self.running = False
        self._stop = False # Set to True to stop current run
        self._paused = False # Is it currently paused?
        # The reason _stop and _paused represent different conditions is
        # because of the way GRBL handles stopping/pausing.
        # If GRBL is stopped, GRBL clears its queue, so we no longer have a
        # reliable method of continuation. So by setting _stop = True, we can
        # clear our queue as well as stop GRBL.
        # However, GRBL will immediately pause if sent "!" at any time. It can
        # be resumed from the exact same position by sending "~", so there is
        # only a need to tracking whether GRBL is paused or not, as the queue
        # will remain the same.
        self._sum_command_lens = 0

    def _open_serial(self, device):
        """Open serial port"""
        logger.info("Opening serial device")
        self.serial = serial.serial_for_url(device,
                                            baudrate=115200,
                                            bytesize=serial.EIGHTBITS,
                                            parity=serial.PARITY_NONE,
                                            stopbits=serial.STOPBITS_ONE,
                                            timeout=SERIAL_TIMEOUT,
                                            xonxoff=False,
                                            rtscts=False)
        logger.debug("Serial: %s", self.serial)
        # Toggle DTR to reset the arduino
        try:
            self.serial.setDTR(0)
            time.sleep(1)
            self.serial.setDTR(1)
            time.sleep(1)
        except IOError:
            logger.debug("IOError on setDTR(), but not important")
            pass
        self.serial.write(b"\n\n")
        self.thread = Thread(target=self._serial_io, name="SerialIOThread")
        self.thread.start()
        logger.info("I/O thread started: %s", self.thread.name)
        return True

    def _close_serial(self):
        """Close serial port"""
        logger.info("Closing serial device")
        if self.serial is None:
            return
        try:
            self._stop_run()
        except BaseException:
            pass
        logger.info("Stopping thread %s", self.thread.name)
        self.thread = None
        time.sleep(1)
        try:
            self.serial.close()
        except BaseException:
            logger.exception("Error closing serial")
        self.serial = None
        if OUTPUT_LOG_QUEUE:
            self.__write_log_queue()
        return True

    def _stop_run(self):
        """Stop the current run of Gcode"""
        logger.debug("Called Sender._stop_run()")
        logger.info("Stopping run")
        #self._stop = True
        logger.debug("Purging Grbl")
        self._purge_grbl()
        logger.debug("Clearing queue")
        self._empty_queue()
        self.progress = 0.0
        self.max_size = 0.0
        logger.info("Run Stopped")

    def _purge_grbl(self):
        """Purge the buffer of grbl"""
        logger.debug("Called Sender._purge_grbl()")
        logger.debug("Calling self._soft_reset()")
        self._soft_reset()
        logger.debug("Calling self._unlock()")
        self._unlock()
        logger.debug("Calling _run_ended()")
        self._run_ended()
        logger.info("Grbl purged")

    def _run_ended(self):
        """Called when run is finished"""
        logger.debug("Called Sender._run_ended()")
        if self.running:
            logger.debug("self.running == True when _run_ended()")
            logger.info("Run ended")
            self.running = False
        self.progress = 0.0

    def _soft_reset(self):
        """Send GRBL reset command"""
        logger.debug("Called Sender._soft_reset()")
        if self.serial:
            self.serial.write(b"\x18")
            logger.debug("Sent b'\x18'")

    def _unlock(self):
        """Send GRBL unlock command"""
        logger.debug("Called Sender._unlock()")
        self._send_gcode("$X")
        time.sleep(0.25)
        self.serial.write(b"\n\n")
        self.progress = 0.0
        self.max_size = 0.0

    def _home(self):
        """Send GRBL home command"""
        logger.debug("Called Sender._home()")
        self._send_gcode("$H")
        self.progress = 0.0
        self.max_size = 0.0

    def jog(self, x=0, y=0, speed=5000):
        """Send a jog command to Grbl"""
        jog_list = ["$J=", "G21", "G91"]
        jog_list.append("X{}".format(x))
        jog_list.append("Y{}".format(y))
        jog_list.append("F{}".format(speed))
        jog_cmd = "".join(jog_list)
        logger.info("Jogging X%s Y%s @ F%s", x, y, speed)
        self._send_gcode(jog_cmd)

    def jog_cancel(self):
        """Cancel jog command"""
        logger.info("Cancelling jog")
        self.serial.write(b"\x85")

    def _send_gcode(self, command):
        """Send GRBL a Gcode/command line"""
        logger.debug("Called Sender._send_gcode() with %s", command)
        # Do nothing if not actually up
        logger.debug(("send_gcode", {"serial": self.serial,
                                     "running": self.running
                                    }))
        if self.serial: # and not self.running:
            logger.debug("self.serial == True")
            self.queue.put(command+"\n")

    def _empty_queue(self):
        """Clear the queue"""
        logger.debug("Called Sender._empty_queue()")
        logger.info("Emptying Queue size %d", self.queue.qsize())
        while self.queue.qsize() > 0:
            logger.debug("Current qsize: %s", self.queue.qsize())
            try:
                self.queue.get_nowait()
            except Empty:
                logger.debug("Emptying Queue, qsize == 0")
                break

    def _init_run(self):
        """Initialize a gcode run"""
        logger.debug("Called Sender._init_run()")
        logger.debug(("init_run, pre", {"_pause": self._paused,
                                        "running": self.running
                                       }))
        #self._pause = False
        self.running = True
        logger.debug(("init_run, post", {"_pause": self._paused,
                                         "running": self.running
                                        }))
        logger.debug("Calling self._empty_queue()")
        self._empty_queue()
        logger.info("Initializing run")
        self.max_size = 0.0
        self.progress = 0.0
        time.sleep(1) # Give everything a bit of time

    def _pause(self):
        """Pause run"""
        logger.debug("Called Sender._pause()")
        logger.debug(("pause, pre", {"_serial": self.serial,
                                     "_pause": self._paused,
                                    }))
        if self.serial is None:
            return
        if self._paused:
            logger.debug("Calling self._resume() b/c _paused==True")
            self._resume()
        else:
            logger.debug("_paused==False, so pausing")
            logger.info("Pausing run")
            self.serial.write(b"!")
            self.serial.flush()
            self._paused = True
        logger.debug(("pause, post", {"_serial": self.serial,
                                      "_pause": self._paused,
                                     }))

    def _resume(self):
        """Resume a run"""
        logger.debug("Called Sender._resume()")
        logger.debug(("resume, pre", {"_serial": self.serial,
                                      "_pause": self._paused,
                                     }))
        if self.serial is None:
            return
        logger.info("Resuming run")
        self.serial.write(b"~")
        self.serial.flush()
        self._paused = False
        logger.debug(("resume, post", {"_serial": self.serial,
                                       "_pause": self._paused,
                                      }))

    def _toggle_checkmode(self):
        """Toggle the 'check gcode mode' of Grbl"""
        self._send_gcode("$C")

    def __parse_alarm(self, alarm):
        """Logs alarm or error with its short message"""
        try:
            msg, code = alarm.split(":")
        except ValueError:
            logger.exception("Error on '%s'", alarm)
        code = int(code)
        if msg == "ALARM":
            short_msg, long_msg = ALARM_CODES[code]
        elif msg == "ERROR":
            short_msg, long_msg = ERROR_CODES[code]
        self.error.put((msg, code, long_msg))
        #self.log.put("{} {}".format(alarm, short_msg))
        self.log = "{} {}".format(alarm, short_msg)

    def __parse_position(self, field):
        """Sets self.pos tuple with machine position"""
        position = SPLITPOS.split(field)
        self.pos = tuple(float(f) for f in position[1:])
        logger.debug("Position: %s", self.pos)

    def __process_messages(self, message):
        """Master message processing"""
        if message.find("<") == 0:
            logger.debug("Status message received: %s", message)
            status_msg = message[1:-1]
            status_fields = status_msg.split("|")
            #self.log.put(status_fields[0])
            self.log = status_fields[0]
            if "error" in status_fields[0].lower():
                logger.error("Grbl Error: %s", message)
            elif "alarm" in status_fields[0].lower():
                logger.error("Grbl Alarm: %s", message)
            for field in status_fields[1:]:
                if "MPos:" in field:
                    self.__parse_position(field)
        elif any(item in message.upper() for item in ["ALARM", "ERROR"]):
            self.__parse_alarm(message.upper())
        elif "MSG" in message:
            recv_msg = message[1:-1]
            logger.info("Grbl %s", recv_msg)
            msg_fields = recv_msg.split(":")
            if "Pgm End" in msg_fields[1]:
                self._run_ended()
        else:
            logger.error("Unexpected output: %s", message)


    def _serial_io(self):
        """Process to perform I/O on GRBL

        This is borrowed heavily from stream.py of the GRBL project"""
        # pylint: disable=too-many-statements,too-many-branches
        # TODO: reduce number of statements
        # TODO: reduce number of branches (somehow...)
        logger.debug("serial_io started")
        line_count = 0
        error_count = 0
        gcode_count = 0
        char_line = deque()
        sent_line = deque()
        line = None
        done = False
        t_poll = time.time()

        while self.thread: # pylint: disable=too-many-nested-blocks
            # TODO: reduce number of nested blocks
            t_curr = time.time()
            # Poll status if enough time has passed
            if t_curr-t_poll > SERIAL_POLL:
                self.serial.write("?")
                t_poll = t_curr
            # Get other commands from queue
            try:
                line = self.queue.get_nowait()
            except Empty:
                line = None
            logger.debug(("serial_io dur DEBUG:", {"line": line}))
            if isinstance(line, tuple):
                if line[0] == "DONE":
                    done = True
                line = None
            if line is not None:
                line_count += 1
                if self.max_size > 0:
                    self.progress = line_count / self.max_size
                # Reformat line to be ASCII and remove all spaces, comments
                # and newline characters. We want each line to be as short as
                # possible.
                line = line.encode("ascii", "replace").strip()
                line_block = re.sub(r"\s|\(.*?\)", "", line).upper()
                # Track number of characters in the Grbl buffer
                char_line.append(len(line_block)+1)
                sent_line.append(line_block)
                while (sum(char_line) >= RX_BUFFER_SIZE-1
                       or self.serial.in_waiting > 0):
                    out_temp = self.serial.readline().strip()
                    if len(out_temp) > 0:
                        if out_temp.find("ok") >= 0:
                            gcode_count += 1
                            # The following try-except block seems to be mostly
                            # because sending "$H\n" (aka, homing) to Grbl
                            # triggers Grbl to send back two "ok".
                            try:
                                logger.debug("Removing most recent command")
                                char_line.popleft()
                                sent_line.popleft()
                            except IndexError:
                                logger.debug("char_line already empty")
                        else:
                            self.__process_messages(out_temp)
                self.serial.write(line_block + "\n")
            else:
                out_temp = self.serial.readline().strip()
                if len(out_temp) > 0:
                    if out_temp.find("ok") >= 0:
                        gcode_count += 1
                        try:
                            logger.debug("Removing most recent command")
                            char_line.popleft()
                            sent_line.popleft
                        except IndexError:
                            logger.debug("char_line already empty")
                    else:
                        self.__process_messages(out_temp)
                if done and (line_count == gcode_count or not self.running):
                    self.max_size = 0.0
                    self.progress = 0.0
                    done = False
                    line_count = 0
        logger.info("Closing down serial_io")


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
