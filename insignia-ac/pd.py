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

PW_INIT = 3900
PW_ZERO = 1400
PW_ONE = 300

RC_INIT = 3

STATE_FIND_INIT = 0
STATE_READ_CMD = 2

class SamplerateError(Exception):
    pass

class Decoder(srd.Decoder):
    api_version = 3
    id = 'insignia'
    name = 'Insignia'
    longname = 'Insignia Air Conditioner Remote Control'
    desc = '38khz infrared'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = ['insignia']
    channels = (
        {'id': 'data', 'name': 'IR DATA', 'desc': 'Insignia IR'},
    )
    options = (
    )
    annotations = (
        ('bits', 'Bits'),
        ('command', 'Command'),
    )
    annotation_rows = (
        ('bits', 'Bits', (0, )),
        ('data', 'Data', (1, )),
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

    def reset(self):
        self.state = STATE_FIND_INIT
        self.bitcount = 0        

    def handle_pulse(self): 
        # Find rising edge
        self.wait({0: 'r'})
        edge_start = self.samplenum
        if (self.bitcount == 0):
            self.byte_start = self.samplenum

        # Find falling edge
        self.wait({0: 'f'})
        edge_end  = self.samplenum

        # Determine pulse width in microseconds
        pulse_width = ((edge_end - edge_start) / self.samplerate) * 1000 * 1000

        if (pulse_width > PW_INIT):
            self.put(edge_start, edge_end, self.out_ann, [0, ["INIT", "IN"]])
            self.bitcount = 0
            self.databyte = 0
            return RC_INIT
        elif (pulse_width > PW_ZERO):
            self.put(edge_start, edge_end, self.out_ann, [0, ["0"]])
            self.bitcount += 1
            return 0
        # elif (pulse_width > PW_ONE):
        #     self.put(edge_start, edge_end, self.out_ann, [0, ["1"]])
        #     self.bitcount += 1
        #     return 1
        else: 
            self.put(edge_start, edge_end, self.out_ann, [0, ["1"]])
            self.bitcount += 1
            return 1

    def decode(self):
        while True:
            bit = self.handle_pulse()
            if (bit == RC_INIT):
                # Reset the state machine whenever we see an initialzation pulse
                self.state = STATE_READ_CMD
            elif (self.state == STATE_READ_CMD):
                self.databyte = self.databyte | ((bit << (8 - self.bitcount)))
                if (self.bitcount >= 8):
                    byte_end = self.samplenum
                    self.put(self.byte_start, byte_end, self.out_ann, [1, ["0x{:02X}".format(self.databyte), "{:02X}".format(self.databyte)]])
                    self.bitcount = 0
                    self.databyte = 0
