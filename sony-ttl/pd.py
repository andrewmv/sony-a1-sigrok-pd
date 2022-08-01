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

## Timing - all values in microseconds

MOSI_INIT_US = 70       # Averages 90
MISO_INIT_US = 140      # Averages 160
BIT_US = 12             # 8 is highest recorded
INIT_TIMEOUT_US = 800   # 545 is highest recorded

## States

STATE_FIND_INIT = 0
STATE_FIND_FIRST_BYTE = 1
STATE_FIND_NEXT_BYTE = 2
STATE_FIND_BIT = 3

DIR_INIT = 0
DIR_MOSI = 1
DIR_MISO = 2

## Pulse classifications
PULSE_BOGUS = 0
PULSE_MOSI_INIT = 1
PULSE_MISO_INIT = 2
PULSE_BIT = 3

class SamplerateError(Exception):
    pass

class Decoder(srd.Decoder):
    api_version = 3
    id = 'sonyttl'
    name = 'Sony TTL'
    longname = 'Sony TTL Flash Syncronization'
    desc = '125khz directionally mulitplexed SPI'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = ['Sony TTL']
    channels = (
        {'id': 'data', 'name': 'DATA', 'desc': 'Muxed MOSI/MISO'},
        {'id': 'clock', 'name': 'CLK', 'desc': 'Serial data clock'},
    )
    options = (
    )
    annotations = (
        ('MISO packet', 'In'),
        ('MOSI packet', 'Out'),
        ('start', 'Start'),
        ('bits', 'Bits'),
        ('octets', 'Bytes')
    )
    annotation_rows = (
        ('direction', 'I/O', (0, 1, )),
        ('bits', 'Bits', (2, 3, )),
        ('octets', 'Bytes', (4, )),
    )

    def __init__(self):
        self.samplerate = None
        self.bitcount = 0
        self.bit_end = [0, 0, 0, 0, 0, 0, 0, 0]
        self.bit_start = [0, 0, 0, 0, 0, 0, 0, 0]
        self.byte_start = 0
        self.byte_end = 0
        self.packet_start = 0
        self.octet = 0x00
        self.lastbit = 0
        self.bytecount = 0
        self.current_miso_packet = bytearray()
        self.current_mosi_packet = bytearray()
        self.last_miso_packet = bytearray()
        self.last_mosi_packet = bytearray()

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def start(self):
        self.out_python = self.register(srd.OUTPUT_PYTHON)
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.state = STATE_FIND_INIT
        self.direction = DIR_INIT
        self.bitcount = 0
        self.octet = 0x00
        self.current_miso_packet = bytearray()
        self.current_mosi_packet = bytearray()
        self.last_miso_packet = bytearray()
        self.last_mosi_packet = bytearray()

    def reset(self):
        self.state = STATE_FIND_INIT
        self.direction = DIR_INIT
        self.bitcount = 0        
        self.octet = 0x00
        self.bytecount = 0
        self.current_miso_packet = bytearray()
        self.current_mosi_packet = bytearray()
        self.last_miso_packet = bytearray()
        self.last_mosi_packet = bytearray()

    def handle_pulse(self): 
        # Find rising clock edge
        self.wait({1: 'r'})
        edge_start = self.samplenum
        if (self.state == STATE_FIND_BIT):
            self.bit_start[self.bitcount] = edge_start
            if (self.bitcount > 0):
                self.bit_end[self.bitcount - 1] = edge_start
                b = "0"
                if self.lastbit:
                    b = "1"
                self.put(self.bit_start[self.bitcount - 1], edge_start, self.out_ann, [3, [b, ]])

        # Find falling clock edge
        data, clock = self.wait({1: 'f'})
        self.lastbit = data
        edge_end  = self.samplenum

        # Determine pulse width in microseconds
        pulse_width = ((edge_end - edge_start) / self.samplerate) * 1000 * 1000

        if (pulse_width > INIT_TIMEOUT_US):
            self.reset()
            return PULSE_BOGUS
        elif (pulse_width > MOSI_INIT_US):
            self.close_byte_report()
            if (self.byte_end != 0):
                if (self.direction == DIR_MISO):
                    self.put(self.packet_start, self.byte_end, self.out_ann, [0, ["MISO Packet: {} bytes".format(str(self.bytecount)), "MISO", ]])
                elif (self.direction == DIR_MOSI):
                    self.put(self.packet_start, self.byte_end, self.out_ann, [1, ["MOSI Packet: {} bytes".format(str(self.bytecount)), "MOSI", ]])

        if (pulse_width > MISO_INIT_US):
            self.packet_start = edge_start
            self.direction = DIR_MISO
            self.state = STATE_FIND_BIT
            self.bitcount = 0
            self.bytecount = 0
            self.put(edge_start, edge_end, self.out_ann, [2, ["MISO Init", "In", "S"]])
            return PULSE_MISO_INIT
        elif (pulse_width > MOSI_INIT_US):
            self.packet_start = edge_start
            self.direction = DIR_MOSI
            self.state = STATE_FIND_BIT
            self.bitcount = 0
            self.bytecount = 0
            self.put(edge_start, edge_end, self.out_ann, [2, ["MOSI Init", "Out", "S"]])
            return PULSE_MOSI_INIT
        else:   # Bit pulse 
            bitannotation = '0'
            if data:
                bitannotation = '1'
                self.octet = self.octet | (128 >> self.bitcount)

            if (self.state == STATE_FIND_BIT):
                if (self.bitcount == 7):
                    self.byte_end = edge_end
                    self.bit_end[7] = edge_end
                    self.put(self.bit_start[7], edge_end, self.out_ann, [3, [bitannotation, ]])
                    self.put(self.byte_start, self.byte_end, self.out_ann, [4, ["Byte:{:02X}".format(self.octet), "{:02X}".format(self.octet)]])
                    self.push_byte_to_report(self.octet)
                    self.bitcount = 0
                    self.octet = 0x00
                    self.bytecount += 1
                else:
                    if (self.bitcount == 0):
                        self.byte_start = edge_start
                    self.bitcount += 1
            return PULSE_BIT

    def decode(self):
        while True:
            pulse_type = self.handle_pulse()

    def push_byte_to_report(self, b):
        if (self.direction == DIR_MISO):
            self.current_miso_packet.append(b)
        elif (self.direction == DIR_MOSI):
            self.current_mosi_packet.append(b)

    def close_byte_report(self):
        if (self.direction == DIR_MISO):
            if (self.current_miso_packet != self.last_miso_packet):
                print("<<< ", end="")
                self.print_byte_report(self.current_miso_packet)
                self.last_miso_packet = self.current_miso_packet
            self.current_miso_packet = bytearray()
        elif (self.direction == DIR_MOSI):
            if (self.current_mosi_packet != self.last_mosi_packet):
                print(">>> ", end="")
                self.print_byte_report(self.current_mosi_packet)
                self.last_mosi_packet = self.current_mosi_packet
            self.current_mosi_packet = bytearray()

    def print_byte_report(self, b):
        for i in b:
            print("{:02x} ".format(i), end = "")
        print("")
