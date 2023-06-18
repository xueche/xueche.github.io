#!/usr/bin/python
# @lint-avoid-python-3-compatibility-imports
#
# biolatency    Summarize block device I/O latency as a histogram.
#       For Linux, uses BCC, eBPF.
#
# USAGE: biolatency [-h] [-T] [-Q] [-m] [-D] [-e] [interval] [count]
#
# Copyright (c) 2015 Brendan Gregg.
# Licensed under the Apache License, Version 2.0 (the "License")
#
# 20-Sep-2015   Brendan Gregg   Created this.

from __future__ import print_function
from bcc import BPF
from time import sleep, strftime
import argparse
import ctypes as ct
import os
import json
from collections import OrderedDict
import signal
from container_map_create import ContainerMapCreate 

# arguments
examples = """example:
    ./biosnoop                       # display every raw io request info
    ./biosnoop -m                    # measured in milliseconds
    ./biosnoop -t 10                 # set the execution duration to 10s
    ./biosnoop -d 8:16               # set the target block device(/dev/DEVNAME, DEVNAME or MAJ:MIN)
    ./biosnoop -T 10000              # dispaly raw info when the total io latnecy is greater than 10ms
    ./biosnoop -o /tmp/file          # dump the raw info to /tmp/file with json format
    ./biolatnecy -c $container_name  # only inspect the I/O submited by $container_name
"""
parser = argparse.ArgumentParser(
    description="snoop the io request lifecycle information",
    formatter_class=argparse.RawTextHelpFormatter,
    epilog=examples)
parser.add_argument("-m", "--milliseconds", action="store_true",
    help="measured in milliseconds")
parser.add_argument("-t", "--time", default=99999999, type=int,
    help="set the excution duation in seconds")
parser.add_argument("-d", "--dev", type=str,
    help="inspect the target device(/dev/DEVNAME, DEVNAME or MAJOR:MINOR)")
parser.add_argument("-T", "--threshold", type=int,
    help="display raw info when the total io latency is greater than this value")
parser.add_argument("-o", "--output", type=str,
    help="dump the raw info to the specified file with json format")
parser.add_argument("-c", "--container", type=str,
    help="set the container to be inspected")
parser.add_argument("--ebpf", action="store_true",
    help=argparse.SUPPRESS)

args = parser.parse_args()
debug = 0

# define BPF program
bpf_text = """
#include <uapi/linux/ptrace.h>
#include <linux/blkdev.h>
#include <linux/blk_types.h>
#include <linux/cgroup-defs.h>
enum stages {
	GEN_BLK,
   	IO_SCHED,
	DISK_DRV,
	REQ_DONE,
	NR_STAGE,
};

typedef struct bio_info {
	u64 start_time;
	u32 pid;
	char comm[TASK_COMM_LEN];
	u64 cgrp_id;  //from kernel struct kernfs_node_id
} bio_info_t;

typedef struct req_info {
	u64 start_time;
	u64 lat[NR_STAGE];
	u64 size;
	u64 sector;
	struct bio_info bio_info;
	u32 bio_num;
	u64 flags;
} req_info_t;

typedef struct data {
	u64 cgrp_id;
	u64 total_lat; 
	u64 lat[NR_STAGE];
	u64 sector;
	u64 size;
	u32 flags;
	char disk_name[DISK_NAME_LEN];
	u32 partno;
	u32 pid;
	char comm[TASK_COMM_LEN];
	u32 bio_num;
} data_t;

BPF_HASH(bio_trace, struct bio *, bio_info_t);
BPF_HASH(req_trace, struct request *, req_info_t);
BPF_HASH(link_bio_req, struct request *, struct bio *);
BPF_PERF_OUTPUT(events);

int trace_bio_submit(struct pt_regs *ctx, struct bio *bio)
{
	bio_info_t bio_info = {};
	struct task_struct *t;
	struct cgroup_subsys_state *css = NULL;
	
	if (bpf_get_current_comm(&bio_info.comm, sizeof(bio_info.comm)) != 0) {
		bio_info.comm[0] = '?';
		bio_info.comm[1] = 0;
	}
	bio_info.pid = bpf_get_current_pid_tgid() >> 32;
	bio_info.start_time = bpf_ktime_get_ns();

	if (bio->bi_css) {
		bio_info.cgrp_id = bio->bi_css->cgroup->kn->id.id;
	}
	
	bio_trace.update(&bio, &bio_info);

	return 0;
}

/*if bio was mergerd or bio doesn't arrive block layer because of erros, */
/*the map of bio_trace was deleted here */
int trace_bio_endio(struct pt_regs *ctx, struct bio *bio)
{
	if (bio_trace.lookup(&bio))	
		bio_trace.delete(&bio);
	return 0;
}

int trace_bio_getreq(struct pt_regs *ctx, struct request *req, struct bio *bio)
{
	req_info_t req_info = {};
	bio_info_t *pbio_info;
	struct bio *bio_parent;
	u64 ts;
	
	pbio_info = bio_trace.lookup(&bio);
	if ( 0 == pbio_info) {
		/*check splited bio, the splited bio has no chance to merge*/
                bio_parent = bio->bi_private;
                if ((bio->bi_flags & (1 << BIO_CLONED)) &&
                    (bio_parent->bi_flags & (1 << BIO_CHAIN))) {
                        pbio_info = bio_trace.lookup(&bio_parent);
                        if (0 == pbio_info)
                                return 0;
                        //bpf_trace_printk("splited!!\\n");
                }
                else
                        return 0;
	}
	
	ts = bpf_ktime_get_ns();		
	req_info.lat[GEN_BLK] = ts - pbio_info->start_time;
	req_info.start_time = ts;
	req_info.bio_num++;
	/*some flags would be cleared later, so extract the flags here*/
	req_info.flags = req->cmd_flags;
	bpf_probe_read(&req_info.bio_info, sizeof(req_info.bio_info), pbio_info);

	/*cgroup info extracted in trace_submit_bio() may be invalid*/
	/*extract cgroup info again here*/
	if (pbio_info->cgrp_id == 0 && bio->bi_css) {
		req_info.bio_info.cgrp_id = bio->bi_css->cgroup->kn->id.id;
	}
	
	FILTER_CONTAINER

	req_trace.update(&req, &req_info);
	link_bio_req.update(&req, &bio);
	bio_trace.delete(&bio);
	
	return 0;
}

int trace_bio_merge(struct pt_regs *ctx, struct request *req, bool new_io)
{
	req_info_t *preq_info;

	/*the new bio had been traced in trace_bio_getreq*/
	if (new_io)
		return 0;
	
	preq_info = req_trace.lookup(&req);
	if (0 == preq_info)
		return 0;
	preq_info->bio_num++;

	return 0;	
}

int trace_ret_reqmerge(struct pt_regs *ctx)
{
        struct request *req = (struct request *)PT_REGS_RC(ctx);

        /*no merge*/
        if (NULL == req)
                return 0;

        if (req_trace.lookup(&req))
                req_trace.delete(&req);
        if (link_bio_req.lookup(&req))
                link_bio_req.delete(&req);

        return 0;
}

int trace_req_dispatch(struct pt_regs *ctx, struct request *req)
{
	req_info_t *preq_info;
	u64 ts;

	preq_info = req_trace.lookup(&req);
	if ( 0 == preq_info)
		return 0;
	
	ts = bpf_ktime_get_ns();
	preq_info->lat[IO_SCHED] = ts - preq_info->start_time;
	
	return 0;
}

int trace_req_complete(struct pt_regs *ctx, struct request *req)
{
	req_info_t *preq_info;
	u64 ts;

	preq_info = req_trace.lookup(&req);
	if ( 0 == preq_info)
		return 0;

	ts = bpf_ktime_get_ns();
	preq_info->lat[DISK_DRV] = 
			ts - preq_info->start_time - preq_info->lat[IO_SCHED];
	preq_info->size = req->__data_len;
	preq_info->sector = req->__sector;
	
	return 0;
}

int trace_req_done(struct pt_regs *ctx, struct request *req)
{
	req_info_t *preq_info;
	struct bio **bio;
	struct gendisk *rq_disk;
	data_t data = {};
	u64 ts, total_lat;

	preq_info = req_trace.lookup(&req);
	if ( 0 == preq_info)
		return 0;
	bio = link_bio_req.lookup(&req);
	if ( 0 == bio) {
		req_trace.delete(&req);
		return 0;
	}

	FILTER_DEV

	rq_disk = req->rq_disk;
	ts = bpf_ktime_get_ns();
	data.total_lat = (ts - preq_info->bio_info.start_time)/1000;
	
	FILTER_THRESHOLD

	data.lat[GEN_BLK]   = preq_info->lat[GEN_BLK]/1000;
	data.lat[IO_SCHED]  = preq_info->lat[IO_SCHED]/1000;
	data.lat[DISK_DRV]  = preq_info->lat[DISK_DRV]/1000;
	data.lat[REQ_DONE]  = (ts - preq_info->start_time - 
		preq_info->lat[IO_SCHED] - preq_info->lat[DISK_DRV])/1000;

	FACTOR

	data.cgrp_id = preq_info->bio_info.cgrp_id;
	data.pid = preq_info->bio_info.pid;
	bpf_probe_read(&data.comm, sizeof(data.comm), preq_info->bio_info.comm);
	data.sector = preq_info->sector; 
	data.size = preq_info->size;
	data.bio_num = preq_info->bio_num;
	data.flags = preq_info->flags;
	bpf_probe_read(&data.disk_name, sizeof(data.disk_name), rq_disk->disk_name);
	data.partno = req->part->partno;
	events.perf_submit(ctx, &data, sizeof(data));
		
	req_trace.delete(&req);
	link_bio_req.delete(&req);
	
	return 0;	
}
"""

#find map between container_id and container_name
container_map = ContainerMapCreate()
cgid_dict = container_map._create_container_map()
#print(cgid_dict)

#code substitutions
if args.dev:
	try:
		major = int(args.dev.split(':')[0])
		minor = int(args.dev.split(':')[1])
	except Exception:
		if '/' in args.dev:
			stat = os.stat(args.dev)
		else:
			stat = os.stat('/dev/' + args.dev)
		major = int(os.major(stat.st_rdev))
		minor = int(os.minor(stat.st_rdev))

	bpf_text = bpf_text.replace('FILTER_DEV', 
				'struct device *dev = &req->part->__dev;' +			 
				'if ((dev->devt >> MINORBITS) != %d ||' % major +
				'(dev->devt & MINORMASK) != %d)' %minor +
				'{req_trace.delete(&req); link_bio_req.delete(&req); return 0;}')
else:
	bpf_text =  bpf_text.replace('FILTER_DEV', ' ')

if args.threshold:
	bpf_text = bpf_text.replace('FILTER_THRESHOLD',
				'if (data.total_lat <= %d)' %(args.threshold) +
				'{req_trace.delete(&req); link_bio_req.delete(&req); return 0;}')
else:
	bpf_text = bpf_text.replace('FILTER_THRESHOLD', ' ')

if args.container:
	cgid = 0
	for k,v in cgid_dict.items():				          
		if args.container == v:
			cgid = int(k)
			bpf_text = bpf_text.replace('FILTER_CONTAINER',
					'if (req_info.bio_info.cgrp_id != %d)' %cgid +
					'{ bio_trace.delete(&bio); return 0; }')
	if cgid == 0:
		bpf_text = bpf_text.replace('FILTER_CONTAINER', ' ')
else:
	bpf_text = bpf_text.replace('FILTER_CONTAINER', ' ')

if args.milliseconds:
	bpf_text = bpf_text.replace('FACTOR', 
				'data.total_lat     /= 1000;' + 
				'data.lat[GEN_BLK]  /= 1000;' + 
				'data.lat[IO_SCHED] /= 1000;' +
				'data.lat[DISK_DRV] /= 1000;' +
				'data.lat[REQ_DONE] /= 1000;')
	label = "(ms)"
else:
	bpf_text = bpf_text.replace('FACTOR', ' ')
	label = "(us)"

if debug or args.ebpf:
	print(bpf_text)
	if args.ebpf:
		exit()

#load BPF program
b = BPF(text=bpf_text)
b.attach_kprobe(event="submit_bio", fn_name="trace_bio_submit")
b.attach_kprobe(event="blk_init_request_from_bio", fn_name="trace_bio_getreq")
b.attach_kprobe(event="blk_account_io_start", fn_name="trace_bio_merge")
b.attach_kretprobe(event="attempt_merge", fn_name="trace_ret_reqmerge")
if BPF.get_kprobe_functions(b'blk_start_request'):
	b.attach_kprobe(event="blk_start_request", fn_name="trace_req_dispatch")
b.attach_kprobe(event="blk_mq_start_request", fn_name="trace_req_dispatch")
b.attach_kprobe(event="blk_account_io_completion", fn_name="trace_req_complete")
b.attach_kprobe(event="blk_account_io_done", fn_name="trace_req_done")
b.attach_kprobe(event="bio_endio", fn_name="trace_bio_endio")
#b.trace_print()

#see blk_fill_rwbs()
req_opf = {
	0: "R_",    #Read
	1: "W_",    #Write
	2: "F_",    #Flush
	3: "D_",    #Discard
	5: "S_",    #SecureErase
	6: "Z_",    #ZoneReset
	7: "Ws_",   #WriteSame
	9: "Wz_"    #WriteZeros
}
REQ_OP_BITS = 8
REQ_OP_MASK = ((1 << REQ_OP_BITS) - 1)
REQ_SYNC = 1 << (REQ_OP_BITS + 3)
REQ_META = 1 << (REQ_OP_BITS + 4)
REQ_PRIO = 1 << (REQ_OP_BITS + 5)
REQ_NOMERGE = 1 << (REQ_OP_BITS + 6)
REQ_IDLE = 1 << (REQ_OP_BITS + 7)
REQ_FUA = 1 << (REQ_OP_BITS + 9)
REQ_PREFLUSH = 1 << (REQ_OP_BITS + 10)
REQ_RAHEAD = 1 << (REQ_OP_BITS + 11)
REQ_BACKGROUND = 1 << (REQ_OP_BITS + 12)
REQ_NOWAIT = 1 << (REQ_OP_BITS + 14)
def flags_print(flags):
	desc = ""
	# operation
	if flags & REQ_OP_MASK in req_opf:
		 desc = req_opf[flags & REQ_OP_MASK]
	else:
		 desc = "Unknown"
	# flags
	if flags & REQ_SYNC:
		desc = desc + "S"
	if flags & REQ_META:
		desc = desc + "M"
	if flags & REQ_FUA:
        	desc = desc + "F"
	if flags & REQ_PRIO:
        	desc = desc + "P"
	if flags & REQ_NOMERGE:
        	desc = desc + "Nm"
	if flags & REQ_IDLE:
		desc = desc + "I"
	if flags & REQ_PREFLUSH:
		desc = desc + "Pf"
	if flags & REQ_RAHEAD:
		desc = desc + "R"
	if flags & REQ_BACKGROUND:
		desc = desc + "B"
	if flags & REQ_NOWAIT:
		desc = desc + "Nw"

	return desc

TASK_COMM_LEN = 16
DISK_NAME_LEN = 32
NR_STAGE = 4
class Data(ct.Structure):
	_fields_ = [
		("cgrp_id", ct.c_ulonglong),
		("total_lat", ct.c_ulonglong),
		("lat", ct.c_ulonglong * NR_STAGE),
		("sector", ct.c_ulonglong),
		("size", ct.c_ulonglong),
		("flags", ct.c_uint),
		("disk_name", ct.c_char * DISK_NAME_LEN),
		("partno", ct.c_uint),
		("pid", ct.c_uint),
		("comm", ct.c_char * TASK_COMM_LEN),
		("bio_num", ct.c_uint)
	]

results = []
def record_abnormal_info(event):
	abnormal_info = OrderedDict()
	lat_info = OrderedDict()
	abnormal_info["checktime"] = strftime("%Y-%m-%d-%H:%M:%S") 
	abnormal_info["diskname"] = event.disk_name.decode() + (str(event.partno) if event.partno else "")
	abnormal_info["container"] = cgid_dict[str(event.cgrp_id)] if cgid_dict.has_key(str(event.cgrp_id)) else event.cgrp_id
	abnormal_info["comm"] = event.comm.decode();
	abnormal_info["pid"] = event.pid
	abnormal_info["op"] = flags_print(event.flags)
	abnormal_info["bio_num"] = event.bio_num
	abnormal_info["sector"] = event.sector
	abnormal_info["size"] = event.size
	abnormal_info["total_lat"+label] = event.total_lat
	lat_info = {"GEN_BLK"+label: event.lat[0],
		    "IO_SCHED"+label: event.lat[1],
		    "DISK_DRV"+label: event.lat[2],
		    "REQ_DONE"+label: event.lat[3]
		   }
	abnormal_info["detail_lat"] = lat_info
	with open(args.output, 'a+') as w_f:
		json.dump(abnormal_info, w_f, indent=4, separators=(',', ':'))
		w_f.write("\n")

def store_event_data(cpu, data, size):
	event = ct.cast(data, ct.POINTER(Data)).contents
	disk_name = event.disk_name.decode() + (str(event.partno) if event.partno else "")
	container = cgid_dict[str(event.cgrp_id)] if cgid_dict.has_key(str(event.cgrp_id)) else event.cgrp_id
	
	lat_info = OrderedDict()
	container_info = OrderedDict()
	element = OrderedDict()
	append_cgrp = 0
	append_disk = 0

	for val in results:
		if val and val["diskname"] == disk_name:
			element = val
	if element.has_key("diskname"):
		element["total_ios"] += 1
		element["total_lat"+label] += event.total_lat	
	else:	
		element["diskname"] = disk_name
		element["total_ios"] = 1
		element["total_lat"+label] = event.total_lat
		element["container_info"] = [] 
		append_disk = 1 

	for val in element["container_info"]:
		if val and val["container"] == container:
			container_info = val
	if container_info.has_key("container"):
		container_info["ios"] += 1	
		container_info["lat"+label] +=  event.total_lat	
	else:	
		container_info["container"] = container
		container_info["ios"] = 1	
		container_info["lat"+label] = event.total_lat	
		append_cgrp = 1	

	if container_info.has_key("lat_info"+label):
		lat_info = container_info["lat_info"+label]
		i = 0
		for key in lat_info:
			val = lat_info[key]
			val["min"] = event.lat[i] if event.lat[i] < val["min"] else val["min"]
			val["max"] = event.lat[i] if event.lat[i] > val["max"] else val["max"]
			val["total"] +=  event.lat[i]
			i += 1
	else:
		lat_info["GEN_BLK"+label] = {"min": event.lat[0], "max": event.lat[0], "total": event.lat[0]}
		lat_info["IO_SCHED"+label] = {"min": event.lat[1], "max": event.lat[1], "total": event.lat[1]}
		lat_info["DISK_DRV"+label] = {"min": event.lat[2], "max": event.lat[2], "total": event.lat[2]}
		lat_info["REQ_DONE"+label] = {"min": event.lat[3], "max": event.lat[3], "total": event.lat[3]}
		container_info["lat_info"+label] = lat_info
 	
	if append_cgrp:
		element["container_info"].append(container_info)
	if append_disk:
		results.append(element)

	if args.threshold:
		record_abnormal_info(event)

def print_event_json(results):
	with open(args.output, 'a+') as w_f:
		date = strftime("%Y-%m-%d-%H:%M:%S")
		w_f.write(date);
		w_f.write("###Summary info###:\n")
		for val in results:
			json.dump(val, w_f, indent=4, separators=(',', ':'))
			w_f.write("\n")
		w_f.close()
#output
print("Tracing block device I/O... Hit Ctrl-C to end.")
#header
if args.output == None:
	print("start_time:%-16s" % strftime("%Y-%m-%d-%H:%M:%S"))
	print("%-9s %-12s %-16s %-6s %-10s %-4s %-13s %-6s %-8s %-8s %-8s %-8s %-8s"
	 	 %("DISK", "CONTAINER", "COMM", "PID", "OP", "NUM", "SECTOR", "SIZE", 
		"BLK"+label, "SCHE"+label, "DRV"+label, "DONE"+label, "TOTAL"+label))

def print_event(cpu, data, size):
	event = ct.cast(data, ct.POINTER(Data)).contents
	flag = flags_print(event.flags)
	disk_name = event.disk_name.decode() + (str(event.partno) if event.partno else "")
	if cgid_dict.has_key(str(event.cgrp_id)):
		container = cgid_dict[str(event.cgrp_id)][0:12]
	else:
		container = event.cgrp_id
	print("%-9s %-12s %-16s %-6s %-10s %-4s %-13s %-6s %-8Ld %-8Ld %-8Ld %-8Ld %-8Ld" 
		% (disk_name, container, event.comm.decode(),
		  event.pid, flag, event.bio_num, event.sector, event.size, event.lat[0],
		  event.lat[1], event.lat[2], event.lat[3],
		  event.total_lat))

# loop with callback to print_event
if args.output:
	b["events"].open_perf_buffer(store_event_data, page_cnt=4096)
else:
	b["events"].open_perf_buffer(print_event, page_cnt=512)

exiting = 0
seconds = 0

if args.output:
	def sig_handler(sig, frame):
		global exiting,results
		print_event_json(results)
		exiting = 1	
else:
	def sig_handler(sig, frame):
		global exiting
		print("end_time:%-16s" % strftime("%Y-%m-%d-%H:%M:%S"))
		exiting = 1
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
	signal.signal(sig, sig_handler)

while (1):
	sleep(1)
	seconds += 1
	
	b.perf_buffer_poll()

	if args.time and seconds >= args.time:
		if args.output:
			print_event_json(results)
		else:
			print("end_time:%-16s" % strftime("%Y-%m-%d-%H:%M:%S"))
		exiting = 1
	
	if exiting:
		exit()
