/* scheduler_ipc.h - External scheduler IPC for distcc */

#ifndef _DISTCC_SCHEDULER_IPC_H
#define _DISTCC_SCHEDULER_IPC_H

struct dcc_hostdef;

/* Query external scheduler daemon for a host choice.
 * Returns 0 on success and sets *out_host to a member of hostlist.
 * Returns non-zero on error; caller should fallback to internal heuristics. */
int dcc_scheduler_query_external(const char *endpoint,
                                 struct dcc_hostdef *hostlist,
                                 const char *input_file,
                                 struct dcc_hostdef **out_host);

#endif /* _DISTCC_SCHEDULER_IPC_H */
