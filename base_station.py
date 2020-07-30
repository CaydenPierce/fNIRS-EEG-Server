"""
Connect to and stream a pair of Blueberry fNIRS glasses and a Muse EEG headband at the same time.
"""

from bluepy.btle import DefaultDelegate, Peripheral
import time 
import sys
import signal
import muselsl
import os
import threading
import bitstring
import numpy as np

#globals
myMuse = None
blueberry = None
muse_thread = None
bby_thread = None
stream = False #should we be pushing data out?
eegSave = None
fnirsSave = None

#Blueberry glasses GATT server characteristics information
bbxService={"name": 'fnirs service',
            "uuid": '0f0e0d0c-0b0a-0908-0706-050403020100' }
bbxchars={
          "commandCharacteristic": {
              "name": 'write characteristic',
                  "uuid": '1f1e1d1c-1b1a-1918-1716-151413121110'
                    },
            "fnirsCharacteristic": {
                    "name": 'read fnirs data characteristic',
                        "uuid": '3f3e3d3c-3b3a-3938-3736-353433323130'
                          }
            }

#handle Ctrl-C, killing program
def signal_handler(signal, frame):
    global myMuse, blueberry, stream, muse_thread, bby_thread
    stream = False
    print("Closing bluetooth connections and disconnecting...")
    myMuse.disconnect()
    blueberry.disconnect()
    muse_thread.join()
    bby_thread.join()
    time.sleep(3)
    print("Connections closed and garbage cleaned, exiting.")
    sys.exit(0)

#receive EEG data callback
def getMuseData(data, timestamps):
    global eegSave
    curr_time = time.time()
    for i, e in enumerate(data[:-1]):
        eegSave.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(curr_time, i, e[0], e[1],e[2], e[3],e[4], e[5],e[6], e[7],e[8], e[9],e[10], e[11]))

#unpack fNIRS byte string
def unpack_fnirs(packet):
    aa = bitstring.Bits(bytes=packet)
    pattern = "uintbe:16,uintbe:32,uintbe:32,uintbe:32,uintbe:16"
    res = aa.unpack(pattern)
    packet_time = res[1]
    short_path = res[2]
    long_path = res[3]
    return packet_time, short_path, long_path

#receive fNIRS data callback
def receive_notify(characteristic_handle, data):
    global fnirsSave
    if stream:
        packet_index, short_path, long_path = unpack_fnirs(data)
        fnirsSave.write("{},{},{},{}\n".format(time.time(),packet_index,short_path,long_path))

#delegate for bluepy handling BLE connection
class PeripheralDelegate(DefaultDelegate):
    """
    Used by bluepy to receive notifys from BLE GATT Server.
    """
    def __init__(self, callback):
        DefaultDelegate.__init__(self)
        self.callback = callback
        self.listen = False
       
    def handleNotification(self, characteristic_handle, data):
        if self.listen:
            self.callback(characteristic_handle, data)

#subscribe to Blueberry notifications
def setupBlueberry(device): #sets characteristic so the glasses send us data
    setup_data = b"\x01\x00"
    notify = device.getCharacteristics(uuid=bbxchars["fnirsCharacteristic"]["uuid"])[0]
    notify_handle = notify.getHandle() + 1
    print(notify_handle)
    device.writeCharacteristic(notify_handle, setup_data, withResponse=True)

#main blocking loop for bluepy streaming from Blueberry
def bby_loop(device):
    global stream
    print("Streaming in from Blueberry...")
    while True:
        if not device.waitForNotifications(1):
            print('nothing received')
        time.sleep(0.001)
        #end thread if we are no longer streaming
        if stream == False:
            break

#main blocking loop for muselsl (pygatt) streaming from Muse
def muse_loop(device):
    global stream
    device.start()
    print("Streaming in from Muse...")
    while True:
        #end thread if we are no longer streaming
        if stream == False:
            break

def main():
    global myMuse, blueberry, stream, muse_thread, bby_thread,eegSave,fnirsSave
    if len(sys.argv) < 3:
        print("Usage: python3 base_station.py <Muse MAC address> <Blueberry MAC address>")
        print("MAC args not specified, exiting...")
        sys.exit()
    
    #handle killing of program
    signal.signal(signal.SIGINT, signal_handler)

    #MAC address of the devices to connect
    muse_mac = sys.argv[1]
    bby_mac = sys.argv[2]

    #files to save the data
    fnirsSave = open("./fnirs/{}_fnirs.csv".format(time.time()), "w+")
    fnirsSave.write("real_time,packet_time,short_path,long_path\n")
    eegSave = open("./eeg/{}_eeg.csv".format(time.time()), "w+")
    eegSave.write("real_time,e_num,0,1,2,3,4,5,6,7,8,9,10,11\n")

    #connect Muse 1.5, 2, or S
    myMuse = muselsl.muse.Muse("{}".format(muse_mac), callback_eeg=getMuseData)
    myMuse.connect()

    #connect, setup Blueberry glasses device
    print("Connecting to Blueberry: {}...".format(bby_mac))
    blueberry = Peripheral(bby_mac)
    peripheral_delegate = PeripheralDelegate(receive_notify)
    blueberry.setDelegate(peripheral_delegate)
    setupBlueberry(blueberry)
    peripheral_delegate.listen = True
    
    #start listening loops for Blueberry and muse
    bby_thread = threading.Thread(target=muse_loop, args=(myMuse,))
    muse_thread = threading.Thread(target=bby_loop, args=(blueberry,))
    stream = True #starting pushing out data stream
    bby_thread.start()
    muse_thread.start()

    #block here, because we have our two threads running in the background
    while True:
        pass

if __name__ == "__main__":
    main()
