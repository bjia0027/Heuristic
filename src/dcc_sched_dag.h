// dcc_sched_dag.h
#ifndef DCC_SCHED_DAG_H
#define DCC_SCHED_DAG_H

#include "hosts.h"

/**
 * Initialize the DAG‐aware scheduler.
 * @param dagfile    path to a Graphviz “.dot” file describing .cpp → .o dependencies
 * @param hostlist   linked list of hosts from dcc_get_hostlist()
 * @param nhosts     number of hosts in hostlist
 * @return 0 on success, non‐zero on error (fallback to default scheduler)
 */
int dcc_sched_init(const char *dagfile,
                   struct dcc_hostdef *hostlist,
                   int nhosts);

/**
 * Pick a host based on the DAG‐aware least‐load heuristic.
 * @param ret        out: the selected hostdef pointer
 * @return 0 on success, non‐zero to indicate “no host” (fallback)
 */
int dcc_hostlist_pick_host_dag(struct dcc_hostdef **ret);

/**
 * Notify the scheduler that one source file has finished compiling,
 * so its successors in the DAG can become ready.
 * @param filename   the .cpp filename that just completed
 */
void dcc_sched_mark_done(const char *filename);

#endif // DCC_SCHED_DAG_H