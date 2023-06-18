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
from container_map_create import ContainerMapCreate

# arguments
examples = """example:
    ./biolatency                       # summarize block I/O latency for each container and device as a histogram (default display interval is 2s)
    ./biolatency -m                    # measured in milliseconds
    ./biolatency -t 10                 # set the execution duration to 10s
    ./biolatnecy -i 5	               # set the display intrerval to 5s
    ./biolatency -d 8:16               # set the target block device (/dev/DEVNAME, DEVNAME or MAJ:MIN)
    ./biolatnecy -o 0                  # only inspect the read request
    ./biolatnecy -c $container_name    # only inspect the I/O submited by $container_name

"""
parser = argparse.ArgumentParser(
    description="Summarize block device I/O latency",
    formatter_class=argparse.RawTextHelpFormatter,
    epilog=examples)
parser.add_argument("-m", "--milliseconds", action="store_true",
    help="measured in milliseconds")
parser.add_argument("-t", "--time", default=99999999,type=int,
    help="set the excution duation in seconds")
parser.add_argument("-d", "--dev", type=str,
    help="set the target block device (/dev/DEVNAME, DEVNAME or MAJ:MIN)")
parser.add_argument("-i", "--interval", default=2, type=int,
    help="set the display interval")
parser.add_argument("-o", "--operation", type=int,
    help="set the operation of the inspect request(0:read or 1:write)")
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

typedef struct bio_info {
	u64 start_time;
	u64 cgrp_id;  //from kernel struct kernfs_node_id
} bio_info_t;

typedef struct req_info {
	bio_info_t bio_info;
} req_info_t;

typedef struct header_info {
	u64 cgrp_id;
	u64 partno;  //need be u64
	char disk_name[DISK_NAME_LEN];
} header_info_t;

typedef struct dist_key {
	header_info_t header;
	u64 slot;
} dist_key_t;

BPF_HASH(bio_trace, struct bio *, bio_info_t);
BPF_HASH(req_trace, struct request *, req_info_t);
BPF_HASH(link_bio_req, struct request *, struct bio *);
BPF_HISTOGRAM(dist, dist_key_t);

int trace_bio_submit(struct pt_regs *ctx, struct bio *bio)
{
	bio_info_t bio_info = {};
	struct task_struct *t;
	struct cgroup_subsys_state *css;
	
	FILTER_OP
	
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

	bpf_probe_read(&req_info.bio_info, sizeof(req_info.bio_info), pbio_info);

	/*cgroup info extracted in trace_submit_bio() may be invalid*/
	/*extract cgroup info again here*/
	if (pbio_info->cgrp_id == 0 && bio->bi_css) {
		req_info.bio_info.cgrp_id= bio->bi_css->cgroup->kn->id.id;
	}

	FILTER_CONTAINER

	req_trace.update(&req, &req_info);
	link_bio_req.update(&req, &bio);
	bio_trace.delete(&bio);
	
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

int trace_req_done(struct pt_regs *ctx, struct request *req)
{
	struct gendisk *rq_disk;
	struct bio **bio;
	req_info_t *preq_info;
	dist_key_t dist_key = {};
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
	total_lat = (ts - preq_info->bio_info.start_time)/1000;

	FACTOR
	


   	dist_key.header.cgrp_id = preq_info->bio_info.cgrp_id;
   	bpf_probe_read(&dist_key.header.disk_name, 
				sizeof(dist_key.header.disk_name), rq_disk->disk_name);
	dist_key.header.partno = req->part->partno;
	dist_key.slot = bpf_log2l(total_lat);
	dist.increment(dist_key);

	req_trace.delete(&req);
	link_bio_req.delete(&req);
	
	return 0;
}
"""
#find the map between container_id and containe_name
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

if args.operation == 0:
	bpf_text = bpf_text.replace('FILTER_OP', 
				'if ((bio->bi_opf & REQ_OP_MASK) != REQ_OP_READ) {return 0;}')
elif args.operation == 1:
	bpf_text = bpf_text.replace('FILTER_OP',
				'if ((bio->bi_opf & REQ_OP_MASK) != REQ_OP_WRITE) {return 0;}')
else:
	bpf_text = bpf_text.replace('FILTER_OP', ' ')
	
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
	bpf_text = bpf_text.replace('FACTOR', 'total_lat /= 1000;') 
	label = "msecs"
else:
	bpf_text = bpf_text.replace('FACTOR', ' ')
	label = "usecs"

if debug or args.ebpf:
    print(bpf_text)
    if args.ebpf:
        exit()

#load BPF program
b = BPF(text=bpf_text)
b.attach_kprobe(event="submit_bio", fn_name="trace_bio_submit")
b.attach_kprobe(event="blk_init_request_from_bio", fn_name="trace_bio_getreq")
b.attach_kretprobe(event="attempt_merge", fn_name="trace_ret_reqmerge")
b.attach_kprobe(event="blk_account_io_done", fn_name="trace_req_done")
b.attach_kprobe(event="bio_endio", fn_name="trace_bio_endio")
#b.trace_print()

#output
print("Tracing block device I/O... Hit Ctrl-C to end.")

exiting = 0
seconds = 0
dist = b["dist"]

def print_header(bucket):
	container = cgid_dict[str(bucket[0])] if cgid_dict.has_key(str(bucket[0])) else bucket[0]
	if bucket[1] == 0:
		return "container:%s disk:%s" %(container, bucket[2].decode())
	else:
		return "container:%s disk:%s%d" %(container, bucket[2].decode(), bucket[1])

while (1):
	try:
		sleep(int(args.interval))
		seconds += args.interval
	except KeyboardInterrupt:
		exiting = 1
	
	if args.time and seconds >= args.time:
		exiting = 1		

	print()
	print("%-16s" % strftime("%Y-%m-%d-%H:%M:%S"), end="")
	dist.print_log2_hist(label, "header", 
			bucket_fn=lambda k: (k.cgrp_id, k.partno, k.disk_name), 
			section_print_fn=print_header)
	dist.clear()
		
	if exiting:
		exit()
