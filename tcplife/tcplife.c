#include <uapi/linux/ptrace.h>
#ifndef KBUILD_MODNAME
#define KBUILD_MODNAME "foo"
#endif
#include <linux/tcp.h>
#include <linux/sched.h>
#include <linux/cgroup-defs.h>
#include <linux/kernfs.h>
#include <net/sock.h>
#include <bcc/proto.h>

struct ipv4_data_t {
    u64 cgroup_id;   	/*container id*/
    u64 establish_time; /*seconds,starts at system boot time*/
    u64 close_time;     /*seconds,starts at system boot time*/
    u32 saddr;          /* source address */
    u32 daddr;          /* dest address */
    u32 lport;          /* local port */
    u32 dport;          /* dest port*/
};
BPF_PERF_OUTPUT(ipv4_events);

struct cgroup_info {
    bool established;
    u64 cgroup_id;
    u64 ts;
};
BPF_HASH(whoami, struct sock *, struct cgroup_info);

/**
* XXX: The following is temporary code for older kernels, Linux 4.14 and
* older. It uses kprobes to instrument tcp_set_state(). On Linux 4.16 and
* later, the sock:inet_sock_set_state tracepoint should be used instead, as
* is done by the code that follows this. In the distant future (2021?), this
* kprobe code can be removed. This is why there is so much code
* duplication: to make removal easier.
**/
int kprobe__tcp_set_state(struct pt_regs *ctx, struct sock *sk, int state)
{
    if (state == TCP_SYN_SENT) {
        struct task_struct *task;
        struct cgroup_subsys_state * css;
		struct  cgroup_info cg_info;
        u64 cgroup_id;

        task = (struct task_struct *)bpf_get_current_task();
        css = (struct cgroup_subsys_state *)task->sched_task_group;
        cgroup_id = css->cgroup->kn->id.id;
	memset(&cg_info, 0, sizeof(cg_info));
	cg_info.ts = 0;
	cg_info.established = false;
	cg_info.cgroup_id = cgroup_id;

        whoami.update(&sk, &cg_info);
        return 0;
    }

    struct ipv4_data_t ipv4_data;
    u16 lport = sk->__sk_common.skc_num;
    u16 dport = sk->__sk_common.skc_dport;
    u8 prev_state = sk->__sk_common.skc_state;
    dport = ntohs(dport);

    if (state == TCP_ESTABLISHED) {
        if (prev_state == TCP_SYN_SENT) {
            /* filter for loopback session */
            u64 addr = sk->__sk_common.skc_daddr;
            if (addr == 0x0100007F) {
                whoami.delete(&sk);
                return 0;
            }
			
	    struct  cgroup_info *cg_info_p = NULL, cg_info;

	    cg_info_p = whoami.lookup(&sk);
	    if (!cg_info_p)
		    return 0;

       	    u64 ts = bpf_ktime_get_ns();
            memset(&cg_info, 0, sizeof(cg_info));
	    cg_info.ts = ts;
	    cg_info.cgroup_id = cg_info_p->cgroup_id;
	    cg_info.established = true;
       	    whoami.delete(&sk);
       	    whoami.update(&sk, &cg_info);
			
            ipv4_data.saddr = sk->__sk_common.skc_rcv_saddr;
            ipv4_data.daddr = sk->__sk_common.skc_daddr;
            ipv4_data.cgroup_id = cg_info.cgroup_id; 
            ipv4_data.lport = (u32)lport;
	    ipv4_data.dport = (u32)dport;
            ipv4_data.establish_time = ts;
	    ipv4_data.close_time = 0;
            ipv4_events.perf_submit(ctx, &ipv4_data, sizeof(ipv4_data));
    	}
    }
   
    if (state != TCP_CLOSE)
        return 0;

    /* calculate lifespan */
    struct cgroup_info *cg_info_p = NULL;
    u64 close_time, establish_time, delta, cgroup_id;
    
    cg_info_p = whoami.lookup(&sk);
    if (cg_info_p == 0 || !cg_info_p->established) {
        whoami.delete(&sk);     // may not exist
        return 0;
    }

    close_time = bpf_ktime_get_ns();
    establish_time = cg_info_p->ts;
    cgroup_id = cg_info_p->cgroup_id;
    delta = (close_time - establish_time) / 1000000000;
    
    /* filter short session */
    if (FILTER_DELTA) {
        whoami.delete(&sk);
        return 0;
    }
    
    /* filter small flow session */
    /* get throughput stats. see tcp_get_info() */
    u64 rx_b = 0, tx_b = 0;
    struct tcp_sock *tp = (struct tcp_sock *)sk;
    rx_b = tp->bytes_received/1024;
    tx_b = tp->bytes_acked/1024;
    if (FILTER_TRAFFIC) {
        whoami.delete(&sk);
        return 0;
    }

    u16 family = sk->__sk_common.skc_family;

    if (family == AF_INET) {
    	/* filter for loopback session */
        u64 addr = sk->__sk_common.skc_daddr;
	    if (addr == 0x0100007F) {
        	whoami.delete(&sk);     
        	return 0;               
    	}
       
  	ipv4_data.saddr = sk->__sk_common.skc_rcv_saddr;	
        ipv4_data.daddr = sk->__sk_common.skc_daddr;
        ipv4_data.cgroup_id = cgroup_id; 
        ipv4_data.lport = (u32)lport;
	ipv4_data.dport = (u32)dport;
        ipv4_data.establish_time = establish_time ;
        ipv4_data.close_time = close_time;
        ipv4_events.perf_submit(ctx, &ipv4_data, sizeof(ipv4_data));
    }
    
    whoami.delete(&sk);

    return 0;
}
