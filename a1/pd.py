##
## Copyright (C) 2021 Andrew Villeneuve <andrewmv@gmail.com>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.

import sigrokdecode as srd

PW_INIT = 2300
PW_ONE = 1100
PW_ZERO = 500

RC_INIT = 3

STATE_FIND_INIT = 0
STATE_READ_ADDR = 1
STATE_READ_CMD = 2

class SamplerateError(Exception):
    pass

class Decoder(srd.Decoder):
    api_version = 3
    id = 'a1'
    name = 'Sony A1'
    longname = 'Sony A1/A1ii Audio Control Bus'
    desc = '5V steady-high multi-master multi-slave serial bus'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = ['a1']
    channels = (
        {'id': 'data', 'name': 'A1 DATA', 'desc': 'A1 Control Data'},
    )
    options = (
    )
    annotations = (
        ('bits', 'Bits'),
        ('address', 'Device Address'),
        ('command', 'Command'),
    )
    annotation_rows = (
        ('bits', 'Bits', (0, )),
        ('data', 'Address/Data', (1, 2)),
    )

    def __init__(self):
        self.samplerate = None
        self.bitcount = 0
        self.databyte = 0

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def start(self):
        self.out_python = self.register(srd.OUTPUT_PYTHON)
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.state = STATE_FIND_INIT
        self.bitcount = 0

    def handle_bit(self): 
        # Find falling edge
        self.wait({0: 'f'})
        edge_start = self.samplenum
        if (self.bitcount == 0):
            self.byte_start = self.samplenum

        # Find rising edge
        self.wait({0: 'r'})
        edge_end  = self.samplenum

        # Determine pulse width in microseconds
        pulse_width = ((edge_end - edge_start) / self.samplerate) * 1000 * 1000

        if (pulse_width > PW_INIT):
            self.put(edge_start, edge_end, self.out_ann, [0, ["INIT", "IN"]])
            self.state = STATE_READ_ADDR
            self.bitcount = 0
            self.databyte = 0
            return RC_INIT
        elif (pulse_width > PW_ONE):
            self.put(edge_start, edge_end, self.out_ann, [0, ["1"]])
            self.bitcount += 1
            return 1
        else:
            self.put(edge_start, edge_end, self.out_ann, [0, ["0"]])
            self.bitcount += 1
            return 0

    def decode(self):
        while True:
            bit = self.handle_bit()
            if (self.state == STATE_READ_ADDR):
                self.databyte = self.databyte | ((bit << (8 - self.bitcount)))
                if (self.bitcount >= 8):
                    byte_end = self.samplenum
                    self.put(self.byte_start, byte_end, self.out_ann, [1, ["Address: 0x{:X}".format(self.databyte), "ADDR: 0x{:X}".format(self.databyte), "0x{:X}".format(self.databyte), "{:X}".format(self.databyte)]])
                    self.state = STATE_READ_CMD
                    self.bitcount = 0
            elif (self.state == STATE_READ_CMD):
                self.databyte = self.databyte | ((bit << (8 - self.bitcount)))
                if (self.bitcount >= 8):
                    byte_end = self.samplenum
                    self.put(self.byte_start, byte_end, self.out_ann, [2, ["Command: 0x{:X}".format(self.databyte), "CMD: 0x{:X}".format(self.databyte), "0x{:X}".format(self.databyte), "{:X}".format(self.databyte)]])
                    self.bitcount = 0
