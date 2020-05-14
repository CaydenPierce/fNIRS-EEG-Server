"""
This is the exact same as base_station.py, except this one plots out the data for demo and testing purposes.

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

#plotting imports
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.figure
import matplotlib.image
import tkinter

#GLOBALS
#devices
myMuse = None
blueberry = None
muse_thread = None
bby_thread = None
stream = False #should we be pushing data out?

#plotting
eeg_buf = None
hemo_1__buf = None
hemo_2__buf = None
plotter = None
count = 0

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


#code to handle holding data in a circular buffer and plotting those circular buffers

class CircleBuf():
    """
    Wrapper over numpy array to dump streams to be animated.
    Can use as circular buffer via add_data, or manually set x & y.
    """
    def __init__(self, xstart=0, xstop=0, length=0, name=None):
        self.x = np.linspace(xstart, xstop, length)
        self.y = np.zeros(length)
        self.length = length
        self.name = name

    def add_data(self, data):
        self.y = np.insert(self.y, 0, data)[:self.length]


class BufferAnimation():
    """
    Animate any number of plots on a figure.
    Plots CircleBufs.
    Call draw() many times a second to animate.
    """
    def __init__(self, *buffers):
        self.buffers = buffers
        self.fig = matplotlib.figure.Figure()
        self.fig.set_facecolor((0.85, 0.85, 0.85))
        self.grid_spec = self.fig.add_gridspec(3, 1, hspace=0.5, wspace=0.4)

        # add more plots here
        ax_eeg = self.fig.add_subplot(self.grid_spec[0, 0])
        ax_fnirs_880 = self.fig.add_subplot(self.grid_spec[1, 0])
        ax_fnirs_940 = self.fig.add_subplot(self.grid_spec[2, 0])
        self.axeses = ax_eeg, ax_fnirs_880, ax_fnirs_940
        for axes in self.axeses:
            axes.set_fc((0.3, 0.3, 0.3, 1))

        # config matplotlib tk backend for animation
        self.root = tkinter.Tk()
        self.root.wm_title("Brain Data Dashboard")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=1)

    def draw(self):
        for i, axes in enumerate(self.axeses):
            axes.lines = []
            axes.plot(self.buffers[i].x, self.buffers[i].y, color=(1, 0.8, 0, 1))
            axes.set_title(self.buffers[i].name)

        self.canvas.draw()
        self.root.update()

    def end(self):
        self.root.destroy()

#handle Ctrl-C, killing program
def signal_handler(signal, frame):
    global myMuse, blueberry, stream, muse_thread, bby_thread, plotter
    stream = False
    print("Closing bluetooth connections, closing plot, and disconnecting...")
    plotter.end()
    myMuse.disconnect()
    blueberry.disconnect()
    muse_thread.join()
    bby_thread.join()
    time.sleep(3)
    print("Connections closed and garbage cleaned, exiting.")
    sys.exit(0)

#receive EEG data callback
def getMuseData(data, timestamps):
    for datum in data[0]:
        eeg_buf.add_data(datum)

#unpack fNIRS byte string
def unpack_fnirs(packet):
    aa = bitstring.Bits(bytes=packet)
    pattern = "uintbe:8,uintbe:8,intbe:32,intbe:32,intbe:32,intbe:8,intbe:8"
    res = aa.unpack(pattern)
    packet_index = res[0]
    hemo_1 = res[2]
    hemo_2 = res[3]
    return packet_index, hemo_1, hemo_2

#receive fNIRS data callback
def receive_notify(characteristic_handle, data):
    global plotter, hemo_1_buf, hemo_2_buf, eeg_buf, count
    if stream:
        packet_index, hemo_1, hemo_2 = unpack_fnirs(data)
        hemo_1_buf.add_data(hemo_1)
        hemo_2_buf.add_data(hemo_2)
        print("fNIRS -- Index: {}, 880nm: {}, 940nm: {}".format(packet_index, hemo_1, hemo_2))

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
    global myMuse, blueberry, stream, muse_thread, bby_thread, eeg_buf, hemo_1_buf, hemo_2_buf, plotter

    #setup plotting data structures
    eeg_buf = CircleBuf(0, 256, 2560, name='EEG')
    hemo_1_buf = CircleBuf(0, 5, 50, name='fNIRS, 880nm')
    hemo_2_buf = CircleBuf(0, 5, 50, name='fNIRS, 940nm')

    #setup plot
    plotter = BufferAnimation(eeg_buf, hemo_1_buf, hemo_2_buf)

    if len(sys.argv) < 3:
        print("Usage: python3 base_station.py <Muse MAC address> <Blueberry MAC address>")
        print("MAC args not specified, exiting...")
        sys.exit()
    
    #handle killing of program
    signal.signal(signal.SIGINT, signal_handler)

    #MAC address of the devices to connect
    muse_mac = sys.argv[1]
    bby_mac = sys.argv[2]

    #st
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
    bby_thread.start()
    muse_thread.start()
    stream = True #starting pushing out data stream
    time.sleep(3)

    #block here, because we have our two threads running in the background
    while True:
        time.sleep(1)
        plotter.draw()

if __name__ == "__main__":
    main()
