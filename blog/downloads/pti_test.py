#!/usr/bin/env python3

# Copyright (c) 2018, VMware
# Author: Nadav Amit
#
# This program is free software; you can redistribute it and/or modify it
# under the terms and conditions of the GNU General Public License,
# version 2, as published by the Free Software Foundation.
#
# This program is distributed in the hope it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# Measure a workload using the topdown performance model:
# estimate on which part of the CPU pipeline it bottlenecks.
#
# Must find ocperf in python module path. add to paths below if needed.
# Handles a variety of perf and kernel versions, but older ones have various
# limitations.


#
# Usage:
#
# 1. Add [qemu-path]/scripts/qmp to PYTHONPATH or copy qmp.py locally.
# 2. Add '-qmp unix:qmp-sock,server,nowait' to your qemu command-line that runs
#    the VM and boot it.
# 3. Run some userspace processes, which actually spend time in userspace in
#    your VM. Ensure they actually consume CPU cycles. Note that only core 0
#    will be checked.
# 4. Run the script, providing '--socket [path-to-qmp-socket]'
#

import socket
import os
import operator
from qmp import QEMUMonitorProtocol
import time
import sys
import time
import re
import struct
import ctypes
import argparse

PAGE_SIZE = 4096
PAGE_SHIFT = 12
PAGE_SIZE_STRING = ['4k', '2M', '1G']

c_uint64 = ctypes.c_uint64

class PTE_bits( ctypes.LittleEndianStructure ):
    _fields_ = [
                ("present", c_uint64, 1 ),
                ("write",   c_uint64, 1 ),
                ("user",    c_uint64, 1 ),
                ("pwt",     c_uint64, 1 ),
                ("pcd",     c_uint64, 1 ),
                ("access",  c_uint64, 1 ),
                ("dirty",   c_uint64, 1 ),
                ("page_size",c_uint64, 1 ),
                ("g",       c_uint64, 1 ),
                ("ignore",  c_uint64, 3 ),
                ("pfn",     c_uint64, 40 ),
                ("ignore2", c_uint64, 11 ),
                ("exec_disable", c_uint64, 1)
               ]

class PTE( ctypes.Union ):
    _anonymous_ = ("bit",)
    _fields_ = [
            ("bit",     PTE_bits ),
            ("val",     c_uint64 )
           ]

class PageTable:
    def __init__(ptes, level):
        self.ptes = ptes
        self.level = level

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

class Registers:
    def __init__(self, string):
        self.string = string

    def cpl(self):
        m = re.search('(?<=CPL=)\d', self.string)
        return int(m.group(0))

    def cr3(self):
        m = re.search('(?<=CR3=)[\da-f]*', self.string)
        return int(m.group(0), 16)

class Target:
    socket = None
    dump_filename="/tmp/dump"
    address_width = 46
    top_memory = (1 << 40)

    def __init__(self, socket):
        self.socket = socket

    def pause(self):
        self.srv.cmd_obj({'execute': 'stop'})

    def cont(self):
        self.srv.cmd_obj({'execute': 'cont'})

    def connect(self):
        try:
            self.srv = QEMUMonitorProtocol(self.socket)
            self.srv.connect()
        except:
            print('Error opening qmp socket. Please provide socket path using the --socket option')
            os._exit(1)

    def wait_for_cpl(self, needed_cpl, tries):
        for i in range(0, tries):
            self.pause()
            r = self.srv.cmd_obj({'execute': 'human-monitor-command',
                'arguments': { 'command-line': 'info registers',
                'cpu-index': 0}})

            regs = Registers(r['return'])
            cpl = regs.cpl()
            if cpl == needed_cpl:
                break
            self.cont()
            time.sleep(0.5)

        return cpl == needed_cpl

    def check(self, dump):
        r = self.srv.cmd_obj({'execute': 'human-monitor-command',
            'arguments': { 'command-line': 'info registers',
            'cpu-index': 0}})

        regs = Registers(r['return'])
        cr3 = regs.cr3()
        pfn = cr3 >> PAGE_SHIFT

        to_scan = [{'level':3, 'vpn':0, 'pfn':pfn, 'x':1, 'w':1, 'u':1}]
        scanned = set()
        page_tables = set()
        user_frames = set()
        kernel_frames = set()
        writable_frames = set()
        executable_frames = set()
        global_frames = set()

        vaddr = 0
        while (to_scan):
            entry = to_scan.pop(0)
            vpn = entry['vpn']
            level = entry['level']
            pt_x = entry['x']
            pt_w = entry['w']
            pt_u = entry['u']

            pt_addr = entry['pfn'] << PAGE_SHIFT
            r = self.srv.cmd_obj({'execute': 'pmemsave', 'arguments': {
                'filename': self.dump_filename, 'val': pt_addr, 'size': PAGE_SIZE}})

            with open(self.dump_filename, "rb") as f:
                for i in range(0, 512):
                    pte_bytes = f.read(8)
                    pte_val = int.from_bytes(pte_bytes, byteorder='little')
                    pte = PTE()
                    pte.val = pte_val
                    pfn = pte.pfn
                    real_pfn = pfn & ((1 << (self.address_width - PAGE_SHIFT)) - 1)
                    x = pt_x & ~pte.exec_disable
                    w = pt_w & pte.write
                    u = pt_u & pte.user

                    vaddr = vpn << PAGE_SHIFT
                    if (vaddr & (1 << 47)):
                        vaddr |= 0xffff000000000000

                    if real_pfn == 0:
                        vpn += 1 << (9 * level)
                        continue

                    if pte.present:
                        if entry['level'] != 0 and pte.page_size == 0:
                            dup_check_entry = (pfn, level-1, x, w, u)

                            if dup_check_entry not in scanned:
                                to_scan.append({'level':level-1, 'vpn':vpn, 'pfn':pfn, 'u':u, 'w':w, 'x':x})
                                page_tables.add(real_pfn)
                                scanned.add(dup_check_entry)
                        else:
                            if pte.present and dump and not u:
                                 print("VADDR={0} LEVEL={1} PTE={2} PFN={3} U={4} X={5} W={6} G={7}".format(format(vaddr, "16X"),
                                        PAGE_SIZE_STRING[level], format(pte.val, "016X"), format(real_pfn, "x"), u, x, w, pte.g))

                            for i in range (0, 1 << (9 * level)):
                                pfn_i = real_pfn + i
                                if pte.present:
                                    if not u: 
                                        kernel_frames.add(pfn_i)
                                    else:
                                        user_frames.add(pfn_i)
                                    if pte.g:
                                        global_frames.add(pfn_i)
                                    if w:
                                        writable_frames.add(pfn_i)
                                    if x:
                                        executable_frames.add(pfn_i)
                    else:
                        # zero the lower bits, to take care of PAT specifically
                        pfn &= ~((1 << (9 * level)) - 1)
                        phys = pfn << PAGE_SHIFT
                        if phys < self.top_memory and phys != 0:
                            print("L1TF hazard: VADDR={0} PFN={1} LEVEL={2} USER={3}".format(format(vaddr, "16X"),
                                format(pfn, "16X"), level, pte.user))
                    vpn += 1 << (9 * level)

        print("\n")
        kernel_acessible_pt = kernel_frames.intersection(page_tables)
        user_acessible_pt = user_frames.intersection(page_tables)
        kernel_user_alias = kernel_frames.intersection(user_frames)
        writable_pt = writable_frames.intersection(page_tables)
        kernel_wx = writable_frames.intersection(executable_frames).intersection(kernel_frames)
        global_kernel_frames = global_frames.intersection(kernel_frames)
        global_user_frames = global_frames.intersection(user_frames)
        print("kernel frames: {0}".format(len(kernel_frames)))
        print("page tables accessible by the user: {0}".format(len(user_acessible_pt)))
        print("page tables accessible by the kernel: {0}".format(len(kernel_acessible_pt)))
        print("writable page tables: {0}".format(len(kernel_acessible_pt)))
        print("page tables: {0}".format(len(page_tables)))
        print("global kernel frames: {0}".format(len(global_kernel_frames)))
        print("kernel w+x: {0}".format(len(kernel_wx)))
        print("kernel/user aliases: {0}".format(len(kernel_user_alias)))

    def close(self):
        self.srv.close()

def main(argv=None):
    socket="./qmp-sock"

    parser = argparse.ArgumentParser(
            description='''Provides data on kernel entries in user page-tables.''',
            epilog='''Run qemu with -qmp unix:qmp-sock,server,nowait and provide
            the full path using the --socket option if the script is not execute
            in the same path.''')
    parser.add_argument('--socket', help='path to qmp socket')
    parser.add_argument('--pause', help='pause after sampling', action='store_true')
    parser.add_argument('--dump', help='dump supervisor mapped pages', action='store_true')
    args = parser.parse_args()
    if args.socket is not None:
        socket = args.socket

    target = Target(socket)
    try:
        target.connect()

        print("\n")
        if target.wait_for_cpl(3, 10):
            target.check(args.dump)
            if not args.pause:
                target.cont()
        else:
            print("Failed to sample the kernel while running in CPL3")

        target.close()
    except KeyboardInterrupt:
        target.close()
    except:
        print("Unexpected error: {0}".format(sys.exc_info()[0]))

if __name__ == "__main__":
    sys.exit(main())

