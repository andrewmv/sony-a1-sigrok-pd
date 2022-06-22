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
PW_ONE = 1400
PW_ZERO = 300

RC_INIT = 3

STATE_FIND_INIT = 0
STATE_READ_CMD = 2

class SamplerateError(Exception):
    pass

class Decoder(srd.Decoder):
    api_version = 3
    id = 'wynter'
    name = 'Wynter'
    longname = 'Wynter Air Conditioner Remote Control'
    desc = '38khz infrared'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = ['wynter']
    channels = (
        {'id': 'data', 'name': 'IR DATA', 'desc': 'Wynter IR'},
    )
    options = (
    )
    annotations = (
        ('bits', 'Bits'),
        ('command', 'Command'),
        ('payload', 'Payload')
    )
    annotation_rows = (
        ('bits', 'Bits', (0, )),
        ('data', 'Bytes', (1, )),
        ('payload', 'Payload', (2, )),
    )

    def __init__(self):
        self.samplerate = None
        self.bitcount = 0
        self.databyte = 0
        self.bit_end = [0, 0, 0, 0, 0, 0, 0, 0]
        self.bit_start = [0, 0, 0, 0, 0, 0, 0, 0]

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def start(self):
        self.out_python = self.register(srd.OUTPUT_PYTHON)
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.state = STATE_FIND_INIT
        self.bitcount = 0
        self.bytecount = 0

    def reset(self):
        self.state = STATE_FIND_INIT
        self.bitcount = 0        
        self.bytecount = 0

    def handle_pulse(self): 
        # Find rising edge
        self.wait({0: 'r'})
        edge_start = self.samplenum
        self.bit_start[self.bitcount] = edge_start
        if (self.bitcount == 0):
            self.byte_start = self.samplenum

        # Find falling edge
        self.wait({0: 'f'})
        edge_end  = self.samplenum
        self.bit_end[self.bitcount] = edge_end

        # Determine pulse width in microseconds
        pulse_width = ((edge_end - edge_start) / self.samplerate) * 1000 * 1000

        if (pulse_width > PW_INIT):
            self.put(edge_start, edge_end, self.out_ann, [0, ["INIT", "IN"]])
            self.bitcount = 0
            self.databyte = 0
            self.bytecount = 0
            return RC_INIT
        elif (pulse_width > PW_ONE):
            self.put(edge_start, edge_end, self.out_ann, [0, ["1"]])
            self.bitcount += 1
            return 1
        # elif (pulse_width > PW_ONE):
        #     self.put(edge_start, edge_end, self.out_ann, [0, ["1"]])
        #     self.bitcount += 1
        #     return 1
        else: 
            self.put(edge_start, edge_end, self.out_ann, [0, ["0"]])
            self.bitcount += 1
            return 0

    def decode(self):
        while True:
            bit = self.handle_pulse()
            if (bit == RC_INIT):
                # Reset the state machine whenever we see an initialzation pulse
                self.state = STATE_READ_CMD
            elif (self.state == STATE_READ_CMD):
                self.databyte = self.databyte | (bit << (self.bitcount - 1))
                if (self.bitcount >= 8):
                    byte_end = self.samplenum
                    self.put(self.byte_start, byte_end, self.out_ann, [1, ["0x{:02X}".format(self.databyte), "{:02X}".format(self.databyte)]])
                    self.payload_annotate(self.databyte)
                    self.bitcount = 0
                    self.databyte = 0
                    self.bytecount += 1

    def payload_annotate(self, databyte):
        if (self.bytecount == 0):
            self.put(self.byte_start, self.bit_end[7], self.out_ann, [2, ["Device:{:02X}".format(self.databyte), "D:{:02X}".format(self.databyte)]])
        if (self.bytecount == 1):
            fan_speed =   (databyte & 0b01110000) >> 4
            hvac_mode =   (databyte & 0b00001111) >> 0
            self.put(self.bit_start[1], self.bit_end[3], self.out_ann, [2, ["Fan:{:01X}".format(fan_speed), "{:01X}".format(fan_speed)]])
            self.put(self.bit_start[4], self.bit_end[7], self.out_ann, [2, ["HVAC:{:01X}".format(hvac_mode), "{:01X}".format(hvac_mode)]])
        if (self.bytecount == 2):
            timer =     (databyte & 0b11110000) >> 4
            pwr_state = (databyte & 0b00001000) >> 3
            fc_mode =   (databyte & 0b00000100) >> 2
            self.put(self.bit_start[0], self.bit_end[3], self.out_ann, [2, ["Timer:{:01X}".format(pwr_state), "T:{:01X}".format(pwr_state), "{:01X}".format(pwr_state)]])
            self.put(self.bit_start[4], self.bit_end[4], self.out_ann, [2, ["Power:{:b}".format(pwr_state), "Pwr:{:b}".format(pwr_state), "P:{:b}".format(pwr_state), "{:01X}".format(pwr_state)]])
            self.put(self.bit_start[5], self.bit_end[5], self.out_ann, [2, ["F/C:{:b}".format(fc_mode), "{:b}".format(fc_mode)]])
        if (self.bytecount == 3):
            self.put(self.byte_start, self.bit_end[7], self.out_ann, [2, ["Temperature:{:d}".format(self.databyte),"Temp:{:d}".format(self.databyte),"T:{:d}".format(self.databyte)]])
