#!/usr/bin/python
from __future__ import print_function, division
from bcc import BPF
import argparse
from socket import inet_ntop, ntohs, AF_INET
from struct import pack
import ctypes as ct
import time
from time import sleep
import os
import sys

CLOCK_MONOTONIC = 1 # see <linux/time.h>

class Timespec(ct.Structure):
	""" c struct timespec """ 
	_fields_ = [
		('tv_sec', ct.c_long),
		('tv_nsec', ct.c_long)
	]

librt = ct.CDLL('librt.so.1', use_errno=True)
clock_gettime = librt.clock_gettime
clock_gettime.argtypes = [ct.c_int, ct.POINTER(Timespec)]

def get_monotonic_time_ns():
	""" monotonic time by ns """ 
	t = Timespec()
    	if clock_gettime(CLOCK_MONOTONIC, ct.pointer(t)) != 0:
		errno_ = ct.get_errno()
	    	raise OSError(errno_, os.strerror(errno_))
	return t.tv_sec * 1E9 + t.tv_nsec

class Data_ipv4(ct.Structure):
    _fields_ = [
        ("cgroup_id", ct.c_ulonglong),
        ("establish_time", ct.c_ulonglong),
        ("close_time", ct.c_ulonglong),
        ("saddr", ct.c_uint),
        ("daddr", ct.c_uint),
	("lport", ct.c_uint),
	("dport", ct.c_uint)
    ]

event_data = []
def store_ipv4_event(cpu, data, size):
	event = ct.cast(data, ct.POINTER(Data_ipv4)).contents
	boot_time = get_monotonic_time_ns()
	cur_time = time.time()
	if event.close_time != 0:
		close_time = int(0.5 + cur_time + (boot_time - event.close_time) / 1E9)
		establish_time = 0
	else:
		close_time = 0
		establish_time = int(0.5 + cur_time + (boot_time - event.establish_time) / 1E9)	

	sockinfo = {}
	sockinfo["cgroup_id"] = str(event.cgroup_id)
	sockinfo["saddr"] = inet_ntop(AF_INET, pack("I", event.saddr))
	sockinfo["daddr"] = inet_ntop(AF_INET, pack("I", event.daddr))
	sockinfo["lport"] = str(event.lport)
	sockinfo["dport"] = str(event.dport)
	sockinfo["establish_time"] = establish_time
	sockinfo["close_time"] = close_time
	#sockinfo["establish_time"] = event.establish_time
	#sockinfo["close_time"] = event.close_time
	size_bytes = sys.getsizeof(event_data)
	#beyond 1G, clear
	if size_bytes > 2**30:  
		del event_data[:]
	
	event_data.append(sockinfo)

    
class TcpEvent(object):
	
	def __init__(self):
		self.bcc_obj = None
		file_path = os.path.join(os.path.dirname(__file__), "tcplife.c")
		if not os.path.isfile(file_path):
			raise TypeError(file_path + "dose not exist")
		file_obj = open(file_path)
		try:
			self.bpf_text = file_obj.read()
		finally:
			file_obj.close()
		self.event_data = []
	
	def start(self, delta=0, traffic=0, page_num=64):
		if delta > 0:
			self.bpf_text = self.bpf_text.replace('FILTER_DELTA',
					'(delta < %d)' % delta)
		else:
			self.bpf_text = self.bpf_text.replace('FILTER_DELTA', '0')

		if traffic > 0:
			self.bpf_text = self.bpf_text.replace('FILTER_TRAFFIC',
       					 '(rx_b + tx_b) < %d' % traffic)

		else:
    			self.bpf_text = self.bpf_text.replace('FILTER_TRAFFIC', '0')

		self.bcc_obj = BPF(text=self.bpf_text)
		self.bcc_obj["ipv4_events"].open_perf_buffer(store_ipv4_event, page_cnt=page_num)
		
	def poll_data(self):
		if self.bcc_obj != None:
			self.bcc_obj.perf_buffer_poll()
		else:
			print("bcc_obj is none, call start first")
		
	def stop(self):
		if self.bcc_obj != None:
			self.bcc_obj.cleanup()
		else:
			print("bcc_obj is none!")

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description="Trace the lifespan of TCP sessions and summarize",
   			 formatter_class=argparse.RawDescriptionHelpFormatter) 
	parser.add_argument("-d", "--delta_threshold", type=int,
    					help="filter short session (seconds)")
	parser.add_argument("-t","--traffic_threshold", type=int,
    					help="filter small flow session (kbytes)")
	parser.add_argument("-D","--debug", action="store_true",
    					help="show the bpf_text")
	
	args = parser.parse_args()
	
	tcplife = TcpEvent()
	if args.debug:
		print(tcplife.bpf_text)
		exit(0)
	
	tcplife.start(args.delta_threshold, args.traffic_threshold)
	while(1):
		tcplife.poll_data()
		if event_data:
			print(event_data[0])
			event_data.pop(0)
		

