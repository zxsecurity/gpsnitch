# gpsnitch
gpsnitch is a tool to detect GPS spoofing attacks. This was presented at [Unrestcon 2016](https://unrestcon.org/)

## Requirements
1. A GPS Device that will talk to [GPSd](http://www.catb.org/gpsd/)
1. GPSd installed
1. Python
1. Python library [gps3](https://pypi.python.org/pypi/gps3/)

##Running
1. Configure the options in gpsnitch.cfg
1. Run gpsd `sudo gpsd /dev/ttyUSB0 -F /var/run/gpsd.sock`
1. Run the gpsnitch `./gpsnitch.py`