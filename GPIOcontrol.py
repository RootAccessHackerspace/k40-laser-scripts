#!/usr/bin/env python3
"""All GPIO-related functions"""

import time
import logging

import wiringpi as GPIO

__author__ = "Dylan Armitage"
__email__ = "d.armitage89@gmail.com"
__license__ = "MIT"

logger = logging.getLogger(__name__)

# Variables
# Relays and other outputs
OUT_PINS = dict(laser=20, grbl=27)
# Sensors and other inputs
IN_PINS = dict()  # None currently


# Functions
def gpio_setup():
    """Set up GPIO for use, returns True/False if all setup successful

    Not only gets the GPIO for the board, but also sets the appropriate pins
    for output and input."""
    GPIO.wiringPiSetupGpio()  # BCM mode
    message = None
    try:
        for _, pin in OUT_PINS.items():
            logger.info("Configuring pin %d", pin)
            GPIO.pinMode(pin, GPIO.OUTPUT)
            GPIO.digitalWrite(pin, GPIO.HIGH)
    except BaseException as message:
        logger.exception("Failed to setup pins: {}".format(message))
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
