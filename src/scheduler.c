/* scheduler.c - Pluggable scheduling algorithms for distcc
 *
 * Copyright (C) 2024 - Integrated scheduler for distcc
 *
 * This provides Random, Round-Robin, and HEFT scheduling algorithms
 * that can be selected via the DISTCC_SCHEDULER environment variable.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <unistd.h>
#include "distcc.h"
#include "trace.h"
#include "hosts.h"
#include "lock.h"
#include "scheduler.h"
#include "scheduler_ipc.h"

/* Scheduler algorithm type */
typedef enum {
    SCHED_DEFAULT,   /* Original distcc algorithm */
    SCHED_RANDOM,    /* Random selection */
    SCHED_RR,        /* Round-robin */
    SCHED_HEFT       /* HEFT (Heterogeneous Earliest Finish Time) */
} scheduler_algo_t;

/* Global scheduler state */
static scheduler_algo_t g_scheduler_algo = SCHED_DEFAULT;
static double g_host_efts[64] = {0};  /* Max 64 hosts */
static int g_scheduler_initialized = 0;

/* Initialize the scheduler */
void dcc_scheduler_init(void) {
    const char *algo;
    
    if (g_scheduler_initialized)
        return;
    
    algo = getenv("DISTCC_SCHEDULER");
    if (!algo || strcmp(algo, "default") == 0) {
        g_scheduler_algo = SCHED_DEFAULT;
        rs_trace("scheduler: using DEFAULT algorithm");
    } else if (strcmp(algo, "random") == 0) {
        g_scheduler_algo = SCHED_RANDOM;
        srand(time(NULL) ^ getpid());
        rs_trace("scheduler: using RANDOM algorithm");
    } else if (strcmp(algo, "rr") == 0) {
        g_scheduler_algo = SCHED_RR;
        rs_trace("scheduler: using ROUND-ROBIN algorithm");
    } else if (strcmp(algo, "heft") == 0) {
        g_scheduler_algo = SCHED_HEFT;
        rs_trace("scheduler: using HEFT algorithm");
    } else {
        rs_log_warning("unknown DISTCC_SCHEDULER '%s', using default", algo);
        g_scheduler_algo = SCHED_DEFAULT;
    }
    
    g_scheduler_initialized = 1;
}

/* Count hosts in list */
static int count_hosts(struct dcc_hostdef *hostlist) {
    int count = 0;
    struct dcc_hostdef *h;
    for (h = hostlist; h; h = h->next)
        count++;
    return count;
}

/* Get current time in seconds */
static double get_current_time(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + tv.tv_usec / 1000000.0;
}

/* Estimate compile time based on input file size */
static double estimate_compile_time(const char *input_file) {
    struct stat st;
    
    if (!input_file || stat(input_file, &st) != 0)
        return 1.0;  /* Default 1 second */
    
    /* Simple linear model: ~0.01ms per byte */
    return st.st_size * 0.00001;
}

/* Random scheduler */
static struct dcc_hostdef* sched_random(struct dcc_hostdef *hostlist, int n_hosts) {
    int target;
    int i;
    struct dcc_hostdef *h;
    
    if (n_hosts == 0)
        return NULL;
    
    target = rand() % n_hosts;
    
    h = hostlist;
    for (i = 0; i < target && h; i++)
        h = h->next;
    
    rs_trace("scheduler: random selected host %d/%d: %s",
             target, n_hosts, h ? h->hostname : "NULL");
    
    return h;
}

/* Round-robin scheduler */
static struct dcc_hostdef* sched_round_robin(struct dcc_hostdef *hostlist, int n_hosts) {
    static const char *rr_state_file = NULL;
    int target;
    int i;
    struct dcc_hostdef *h;
    FILE *fp;
    int counter = 0;
    
    if (n_hosts == 0)
        return NULL;
    
    /* Get state file path (only once) */
    if (!rr_state_file) {
        const char *home = getenv("HOME");
        static char state_path[512];
        if (home) {
            snprintf(state_path, sizeof(state_path), "%s/.distcc_rr_state", home);
            rr_state_file = state_path;
        }
    }
    
    /* Read counter from file */
    if (rr_state_file && (fp = fopen(rr_state_file, "r")) != NULL) {
        if (fscanf(fp, "%d", &counter) != 1)
            counter = 0;
        fclose(fp);
    }
    
    target = counter % n_hosts;
    
    /* Write incremented counter back */
    if (rr_state_file && (fp = fopen(rr_state_file, "w")) != NULL) {
        fprintf(fp, "%d\n", counter + 1);
        fclose(fp);
    }
    
    h = hostlist;
    for (i = 0; i < target && h; i++)
        h = h->next;
    
    rs_trace("scheduler: round-robin selected host %d/%d (counter=%d): %s",
             target, n_hosts, counter, h ? h->hostname : "NULL");
    
    return h;
}

/* HEFT scheduler */
static struct dcc_hostdef* sched_heft(struct dcc_hostdef *hostlist, int n_hosts) {
    struct dcc_hostdef *h;
    struct dcc_hostdef *best_host = NULL;
    int best_idx = -1;
    double min_eft = 1e15;  /* Use very large initial value */
    double current_time;
    double estimated_time;
    const char *input_file;
    int i;
    
    if (n_hosts == 0)
        return NULL;
    
    current_time = get_current_time();
    input_file = getenv("DISTCC_INPUT_FILE");
    estimated_time = estimate_compile_time(input_file);
    
    /* Find host with minimum EFT */
    h = hostlist;
    for (i = 0; i < n_hosts && i < 64 && h; i++) {
        double start_time;
        double eft;
        int slots;
        
        start_time = (g_host_efts[i] > current_time) ? g_host_efts[i] : current_time;
        slots = h->n_slots > 0 ? h->n_slots : 1;
        eft = start_time + estimated_time / slots;
        
        rs_trace("scheduler: HEFT host %s slots=%d eft_old=%.3f eft_new=%.3f",
                 h->hostname, slots, g_host_efts[i], eft);
        
        if (eft < min_eft) {
            min_eft = eft;
            best_host = h;
            best_idx = i;
        }
        
        h = h->next;
    }
    
    /* Update EFT for selected host */
    if (best_idx >= 0 && best_idx < 64) {
        g_host_efts[best_idx] = min_eft;
    }
    
    rs_trace("scheduler: HEFT selected host %s (eft=%.3f, est_time=%.3f)",
             best_host ? best_host->hostname : "NULL", min_eft, estimated_time);
    
    return best_host;
}

/* Main scheduler function - select a host from the list */
struct dcc_hostdef* dcc_scheduler_select_host(struct dcc_hostdef *hostlist) {
    int n_hosts;
    const char *endpoint;
    struct dcc_hostdef *ext_host = NULL;
    
    if (!g_scheduler_initialized)
        dcc_scheduler_init();
    
    if (g_scheduler_algo == SCHED_DEFAULT)
        return NULL;  /* Use original algorithm */
    
    /* If external scheduler endpoint is configured, query it first. */
    endpoint = getenv("DISTCC_SCHEDULER_ENDPOINT");
    if (endpoint && dcc_scheduler_query_external(endpoint, hostlist,
                                                 getenv("DISTCC_INPUT_FILE"),
                                                 &ext_host) == 0) {
        rs_trace("scheduler: external daemon chose host %s", ext_host->hostname);
        return ext_host;
    }

    n_hosts = count_hosts(hostlist);
    
    switch (g_scheduler_algo) {
        case SCHED_RANDOM:
            return sched_random(hostlist, n_hosts);
        case SCHED_RR:
            return sched_round_robin(hostlist, n_hosts);
        case SCHED_HEFT:
            return sched_heft(hostlist, n_hosts);
        default:
            return NULL;
    }
}
