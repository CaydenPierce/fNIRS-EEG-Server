# EEG + fNIRS Bluetooth Low Energy Server

Stream in both EEG and fNIRS data to the same device at the same time. The devices streaming in are [Blueberry glasses](https://blueberryx.com/) and [Muse](https://choosemuse.com/) 1.5, 2, or S.

## Support

Tested to work in Ubuntu 18.04. [Bluepy](https://github.com/IanHarvey/bluepy) is the backend for the connection to the Blueberry glasses, so it likely won't work in a non-Linux OS. Porting to another system should just require using a Python BLE library that works in your OS. Reach out if you need a hand porting to your system.

## Code

base_station.py connects to both devices (Blueberry and Muse) and starts streaming in data.  

live_plot.py does the same as base_station.py and also live plot the data once / second.

## Setup  

```
mkdir fnirs eeg
pip3 install -r requirements.txt
cd muse-lsl
python3 setup.py install
```

# Credits  

Thanks to Jeremy Stairs for some plotting+buffering code: <https://github.com/stairs1/tune-hci>
