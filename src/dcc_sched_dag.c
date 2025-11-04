// dcc_sched_dag.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "dcc_sched_dag.h"

#define MAX_TASKS       1024
#define MAX_SUCCESSORS    64

/* DAG storage */
static char *task_names[MAX_TASKS];
static int indegree_arr[MAX_TASKS];
static int succ_cnt[MAX_TASKS];
static int successors[MAX_TASKS][MAX_SUCCESSORS];
static int task_count = 0;

/* Host list from distcc */
static struct dcc_hostdef *global_hosts;
static int global_nhosts;

/* Find or add a task by name */
static int find_task(const char *name) {
    for (int i = 0; i < task_count; i++) {
        if (!strcmp(task_names[i], name))
            return i;
    }
    if (task_count >= MAX_TASKS)
        return -1;
    task_names[task_count] = strdup(name);
    indegree_arr[task_count] = 0;
    succ_cnt[task_count]   = 0;
    return task_count++;
}

/* Add directed edge src → dst in the DAG */
static void add_edge(const char *src, const char *dst) {
    int u = find_task(src);
    int v = find_task(dst);
    if (u < 0 || v < 0) return;
    if (succ_cnt[u] < MAX_SUCCESSORS) {
        successors[u][succ_cnt[u]++] = v;
        indegree_arr[v]++;
    }
}

/* Parse a minimal subset of .dot: lines like "  \"a\" -> \"b\";" */
static void parse_dot(const char *dotfile) {
    FILE *f = fopen(dotfile, "r");
    if (!f) return;
    char line[1024], s1[256], s2[256];
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, " \"%255[^\"]\" -> \"%255[^\"]\" ;", s1, s2) == 2) {
            add_edge(s1, s2);
        }
    }
    fclose(f);
}

int dcc_sched_init(const char *dagfile,
                   struct dcc_hostdef *hostlist,
                   int nhosts) {
    /* build the DAG from dot */
    parse_dot(dagfile);
    global_hosts = hostlist;
    global_nhosts = nhosts;
    return 0;
}

int dcc_hostlist_pick_host_dag(struct dcc_hostdef **ret) {
    /* Simple least-load: pick host with smallest n_running */
    struct dcc_hostdef *best = NULL;
    int best_load = INT_MAX;
    for (struct dcc_hostdef *h = global_hosts; h; h = h->next) {
        if (h->n_slots > 0 && h->n_running < best_load) {
            best_load = h->n_running;
            best = h;
        }
    }
    if (!best) return -1;
    *ret = best;
    return 0;
}

void dcc_sched_mark_done(const char *filename) {
    /* decrement indegree of successors */
    int u = find_task(filename);
    if (u < 0) return;
    for (int i = 0; i < succ_cnt[u]; i++) {
        int v = successors[u][i];
        if (--indegree_arr[v] == 0) {
            /* ready: in a full implementation, push v onto a ready queue */
        }
    }
}