/* scheduler.h - Header for pluggable scheduling algorithms
 *
 * Copyright (C) 2024 - Integrated scheduler for distcc
 */

#ifndef _DISTCC_SCHEDULER_H
#define _DISTCC_SCHEDULER_H

/* Forward declaration */
struct dcc_hostdef;

/* Initialize the scheduler */
void dcc_scheduler_init(void);

/* Select a host from the list using the configured algorithm
 * Returns NULL if default algorithm should be used */
struct dcc_hostdef* dcc_scheduler_select_host(struct dcc_hostdef *hostlist);

#endif /* _DISTCC_SCHEDULER_H */
