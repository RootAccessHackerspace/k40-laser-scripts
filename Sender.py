#!/usr/bin/env python2
# coding=UTF-8
"""Module to communicate with GRBL via serial"""


__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"

# This script is heavily influenced by bCNC
# https://github.com/vlachoudis/bCNC

####---- Import ----####
from multiprocessing import Process, Queue

import sys
import logging
import time
import datetime
import serial
import multiprocessing

logger = multiprocessing.log_to_stderr()
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
        self.log.put(("Opening", str(datetime.datetime.now())))
        return True

    def close_serial(self):
        """Close serial port"""
        if self.serial is None:
            return
        try:
            self.stop_run()
        except BaseException:
            pass
        self.log.put(("Closing", str(datetime.datetime.now())))
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
        self.pause()
        logger.info("RECEIVED 104")
        self._stop = True
        self.purge_grbl()
        self.log.put(("Stopped", str(datetime.datetime.now())))

    def purge_grbl(self):
        """Purge the buffer of grbl"""
        self.serial.write(b"!") # Immediately pause
        self.serial.flush()
        time.sleep(1)
        self.soft_reset()
        self.unlock()
        self.run_ended()

    def run_ended(self):
        """Called when run is finished"""
        if self.running:
            self.log.put(("Run ended", str(datetime.datetime.now())))

        self._pause = False
        self.running = False

    def soft_reset(self):
        """Send GRBL reset command"""
        if self.serial:
            self.serial.write(b"\030")

    def unlock(self):
        """Send GRBL unlock command"""
        self.send_gcode("$X")

    def home(self):
        """Send GRBL home command"""
        self.send_gcode("$H")

    def send_gcode(self, command):
        """Send GRBL a Gcode/command line"""
        # Do nothing if not actually up
        if self.serial and not self.running:
            self.queue.put(command+"\n")

    def empty_queue(self):
        """Clear the queue"""
        self.log.put(("Emptying Queue", self.queue.qsize()))
        while self.queue.qsize() > 0:
            try:
                self.queue.get_nowait()
            except BaseException:
                break

    def init_run(self):
        """Initialize a gcode run"""
        self._pause = False
        self.running = True
        self.empty_queue()
        self.log.put(("Initializing", str(datetime.datetime.now())))
        time.sleep(1) # Give everything a bit of time

    def pause(self):
        """Pause run"""
        if self.serial is None:
            return
        if self._pause:
            self.resume()
        else:
            self.log.put(("Pausing", str(datetime.datetime.now())))
            self.serial.write(b"!")
            self.serial.flush()
            self._pause = True

    def resume(self):
        """Resume a run"""
        if self.serial is None:
            return
        self.log.put(("Resuming", str(datetime.datetime.now())))
        self.serial.write(b"~")
        self.serial.flush()
        self._pause = False

    def serial_io(self):
        """Process to perform I/O on GRBL"""
        # pylint: disable=too-many-branches,too-many-statements
        # Probably should split this up...
        command_lens = [] # length of piplined commands
        command_pipe = [] # pipelined commands
        wait = False # wait for commands to complete, aka status change to Idle
        to_send = None # Next command to send
        status = False # wait for status report (<...> from ? command)
        t_report = t_state = time.time() # when ? or $G was sent last

        while self.process:
            #logger.debug("{}".format(str(datetime.datetime.now())))
            t_curr = time.time()
            if t_curr-t_report > SERIAL_POLL:
                self.serial.write(b"?")
                status = True
                t_report = t_curr

            logger.info(("HB",
                         {"to_send": to_send,
                          "wait": wait,
                          "self._pause": self._pause,
                          "self._stop": self._stop,
                          "queue.qsize()": self.queue.qsize(),
                          "command_lens": command_lens,
                          "command_pipe": command_pipe,
                          "status": status,
                          "t_report": t_report,
                          "t_state": t_state
                         }
                        )
                       )

            if (to_send is None # nothing to send
                    and not wait # and not waiting
                    and not self._pause # and not paused
                    and self.queue.qsize() > 0): # and stuff in the queue
                logger.debug({"to_send": to_send,
                              "wait": wait,
                              "_pause": self._pause,
                              "queue.qsize": self.queue.qsize()}
                            )
                try:
                    to_send = self.queue.get_nowait()
                    logger.debug(("to_send", to_send, str(datetime.datetime.now())))
                    if isinstance(to_send, tuple):
                        if to_send[0] == "WAIT":
                            logger.debug(("Waiting", str(datetime.datetime.now())))
                            wait = True
                        to_send = None
                    elif isinstance(to_send, (str, unicode)):
                        to_send += "\n"

                    if to_send is not None:
                        if isinstance(to_send, unicode):
                            to_send = to_send.encode("ascii", "replace")
                    command_pipe.append(to_send)
                    command_lens.append(len(to_send))
                except:
                    logger.debug("Pass!")
                    pass

            # Receive anything waiting
            if self.serial.inWaiting() or to_send is None:
                logger.debug({"serial.inWaiting()": self.serial.inWaiting(),
                              "to_send": to_send}
                            )
                try:
                    line = str(self.serial.readline()).strip()
                    logger.debug(("rawline", line, str(datetime.datetime.now())))
                except BaseException: # Queue is likely correupted, disconnect
                    self.log.put(("Received",
                                  str(sys.exc_info()[1]),
                                  str(datetime.datetime.now())))
                    self.empty_queue()
                    self.close_serial()
                    return
                if not line:
                    # Nothing actually received
                    logger.debug("not line == True")
                    pass
                elif line[0] == "<": # There's a status message!
                    if not status: # We weren't expecting one
                        self.log.put(("Received", line))
                    # Status was True then
                    status = False
                    fields = line[1:-1].split("|")
                    logger.info(fields)
                    # Machine is idle, continue!
                    logger.info({"wait": wait,
                                 "fields[0]": fields[0],
                                 "command_lens": command_lens,
                                 "not command_lens": not command_lens,
                                }
                               )
                    if wait and fields[0] in ("Idle", "Check") and not command_lens:
                        logger.info("wait == True, fields[0] == Idle or Check, not command_lens == True")
                        wait = False
                elif line[0] == "[":
                    self.log.put(("Received", line))
                elif "error:" in line or "ALARM:" in line:
                    self.log.put(("ERROR", line))
                    if command_lens:
                        del command_lens[0]
                    if command_pipe:
                        del command_pipe[0]
                    if self.running:
                        logger.info("RECEIVED 291")
                        self._stop = True
                elif line.find("ok") >= 0: # It was okay!
                    self.log.put(("OK", line))
                    if command_lens:
                        del command_lens[0]
                    if command_pipe:
                        del command_pipe[0]
                elif line[:4] == "Grbl": # Grbl was reset
                    #TODO: Why is this getting triggered? 
                    t_state = time.time()
                    self.log.put(("Received", line))
                    logger.debug("RECEIVED 302")
                    logger.debug(("line[:4]", line[:4]))
                    self._stop = True
                    # It would be pointless to keep the current queue
                    del command_lens[:]
                    del command_pipe[:]
            # Received a command to stop
            if self._stop:
                #TODO: Shouldn't this reset _stop to False?
                logger.info("RECEIVED 309")
                self.empty_queue()
                to_send = None
                self.log.put(("Cleared", ""))
            # If there's stuff to actually send...
            if (to_send is not None
                    and sum(command_lens) < RX_BUFFER_SIZE):
                self._sum_command_lens = sum(command_lens)
                self.serial.write(bytes(to_send))
                self.log.put(("Buffered", to_send))
                to_send = None
                if not self.running and t_curr-t_state > G_POLL:
                    to_send = b"$G\n"
                    command_pipe.append(to_send)
                    command_lens.append(len(to_send))
                    t_state = t_curr

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
