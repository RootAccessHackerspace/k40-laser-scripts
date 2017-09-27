# K40 Laser Scripts

These files were created to make the use of the modified K40 laser cutter easier.
The K40 is in a mixed-permissions environment, where some people have usage rights and others do not.

## Current setup
The original control board was removed and replaced with the following equipment:
* Raspberry Pi 2 Model B
* [Protoneer RPi CNC Board](https://wiki.protoneer.co.nz/Raspberry_Pi_CNC)
* [Pololu DRV8825 stepper motor drivers](https://www.pololu.com/product/2133)
* [4 channel 5V relay module](https://smile.amazon.com/JBtek-Channel-Module-Arduino-Raspberry/dp/B00KTEN3TM/)
* [PN532 NFC/RFID module](https://smile.amazon.com/HiLetgo-Communication-Arduino-Raspberry-Android/dp/B01I1J17LC/)
* [DS18B20 waterproof temperature sensors](https://smile.amazon.com/DS18B20-Waterproof-Temperature-Sensors-Thermistor/dp/B01JKVRVNI/)
* More jumper cables than you could imagine

The RPi is connected to the CNC board via 12 jumper cables to allow access to the remaining GPIO pins.

The NFC module is part of the multi-factor authentication scheme.

The relay module controls whether power is available to the main PSU and whether the laser tube itself can be activated.

Just two temperature sensors are used: one goes into the water bucket to make sure the water does not get too hot, while the other goes to the laser tube itself to detect any faster temperature changes there.

## Security scheme
1. Every new user is verified by a current administrator as having succifient knowledge to run the laser safely.
2. The user choses a username and a password on the RPi.
3. The user is given an NFC tag and its ID is associated with their account.
   (This may change in the future to the user receiving an NFC tag when their become members of RAH.)
   Currently, [pam-nfc](https://github.com/nfc-tools/pam_nfc) is what we are using for NFC auth.
4. [Google Authenticator](https://github.com/google/google-authenticator-libpam) generates a TOTP for the user.

In order to login, the user must have, in addition to their username and password, their NFC tag and TOTP.
The same MFA tokens must also be presented again in order to turn on the power to the PSU/laser.

If the user requires SSH access, they must be in the ssh group and copy their public key into their `~/.ssh/authorized_keys` file via local methods.
Password authentication is turned off for SSH, requiring a public key and TOTP.

As `sudo` cannot grant superuser access without the NFC tag, regular users cannot turn on the laser while logged in via SSH unless they are also phsycally present.
Admins do have the ability to turn on the laser remotely, but they should be educated enough to know that that is an _extremely bad idea_.



**More descriptions and better organization to follow**
