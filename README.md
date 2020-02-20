# K40 Laser Scripts

These files were created to make the use of the modified K40 laser cutter easier.

## Current setup
The original control board was removed and replaced with the following equipment:
* Raspberry Pi 3
* [Protoneer RPi CNC Board](https://wiki.protoneer.co.nz/Raspberry_Pi_CNC)
* [Pololu DRV8825 stepper motor drivers](https://www.pololu.com/product/2133)
* [4 channel 5V relay module](https://smile.amazon.com/JBtek-Channel-Module-Arduino-Raspberry/dp/B00KTEN3TM/)
* [DS18B20 waterproof temperature sensors](https://smile.amazon.com/DS18B20-Waterproof-Temperature-Sensors-Thermistor/dp/B01JKVRVNI/)
* More jumper cables than you could imagine

The RPi is connected to the CNC board via 12 jumper cables to allow access to the remaining GPIO pins.

The relay module controls whether the laser tube itself can be activated.

Just two temperature sensors are used: one goes into the water bucket to make sure the water does not get too hot, while the other goes to the laser tube itself to detect any faster temperature changes there.

**More descriptions and better organization to follow**
