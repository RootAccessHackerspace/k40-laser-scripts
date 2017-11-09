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
import time
import datetime
import serial


#from GrblCodes import ALARM_CODES, ERROR_CODES

# Global variables
SERIAL_TIMEOUT = 0.1 # seconds
SERIAL_POLL = 0.25 # seconds
G_POLL = 10 # seconds
RX_BUFFER_SIZE = 128 # bytes

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
            t_curr = time.time()
            if t_curr-t_report > SERIAL_POLL:
                self.serial.write(b"?")
                status = True
                t_report = t_curr

            if (to_send is None # nothing to send
                    and not wait # and not waiting
                    and not self._pause # and not paused
                    and self.queue.qsize() > 0): # and stuff in the queue
                to_send = self.queue.get_nowait()
                if isinstance(to_send, tuple):
                    if to_send[0] == "WAIT":
                        wait = True
                    to_send = None
                elif isinstance(to_send, (str, unicode)):
                    to_send += "\n"

                if to_send is not None:
                    if isinstance(to_send, unicode):
                        to_send = to_send.encode("ascii", "replace")
                command_pipe.append(to_send)
                command_lens.append(len(to_send))

            # Receive anything waiting
            if self.serial.inWaiting() or to_send is None:
                try:
                    line = str(self.serial.readline()).strip()
                except BaseException: # Queue is likely correupted, disconnect
                    self.log.put(("Received",
                                  str(sys.exc_info()[1]),
                                  datetime.datetime()))
                    self.empty_queue()
                    self.close_serial()
                    return
                if not line:
                    # Nothing actually received
                    pass
                elif line[0] == "<": # There's a status message!
                    if not status: # We weren't expecting one
                        self.log.put(("Received", line))
                    # Status was True then
                    status = False
                    fields = line[1:-1].split("|")
                    # Machine is idle, continue!
                    if wait and fields[0] in ("Idle", "Check"):
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
                        self._stop = True
                elif line.find("ok") >= 0: # It was okay!
                    self.log.put(("OK", line))
                    if command_lens:
                        del command_lens[0]
                    if command_pipe:
                        del command_pipe[0]
                elif line[:4] == "Grbl": # Grbl was reset
                    t_state = time.time()
                    self.log.put(("Received", line))
                    self._stop = True
                    # It would be pointless to keep the current queue
                    del command_lens[:]
                    del command_pipe[:]
            # Received a command to stop
            if self._stop:
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
        return True

    def close_serial(self):
        """Close serial port"""
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
        return True

    def stop_run(self):
        """Stop the current run of Gcode"""
        self.pause()
        self._stop = True
        self.purge_grbl()

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
            self.log.put(("Run ended", datetime.datetime.now()))

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
            if isinstance(command, tuple):
                self.queue.put(command)
            else:
                self.queue.put(command+"\n")

    def empty_queue(self):
        """Clear the queue"""
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
        time.sleep(1) # Give everything a bit of time

    def pause(self):
        """Pause run"""
        if self.serial is None:
            return
        if self._pause:
            self.resume()
        else:
            self.serial.write(b"!")
            self.serial.flush()
            self._pause = True

    def resume(self):
        """Resume a run"""
        if self.serial is None:
            return
        self.serial.write(b"~")
        self.serial.flush()
        self._pause = False
