/* scheduler_ipc.c - External scheduler IPC for distcc */

#include "config.h"
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "distcc.h"
#include "trace.h"
#include "hosts.h"
#include "scheduler_ipc.h"

static int build_hosts_line(char *buf, size_t buflen, struct dcc_hostdef *hosts) {
    size_t off = 0;
    for (struct dcc_hostdef *h = hosts; h; h = h->next) {
        int n = snprintf(buf + off, buflen - off, "%s:%d%s",
                         h->hostname ? h->hostname : "",
                         h->n_slots > 0 ? h->n_slots : 1,
                         h->next ? "," : "");
        if (n < 0 || (size_t)n >= buflen - off) return -1;
        off += (size_t)n;
    }
    return 0;
}

int dcc_scheduler_query_external(const char *endpoint,
                                 struct dcc_hostdef *hostlist,
                                 const char *input_file,
                                 struct dcc_hostdef **out_host) {
    int fd = -1;
    struct sockaddr_un addr;
    char req[2048];
    char hosts_line[1200];
    char resp[128];
    int ret = -1;

    if (!endpoint || !hostlist || !out_host)
        return -1;

    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(endpoint) >= sizeof(addr.sun_path)) {
        rs_log_warning("scheduler_ipc: endpoint too long: %s", endpoint);
        return -1;
    }
    strncpy(addr.sun_path, endpoint, sizeof(addr.sun_path)-1);

    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        rs_log_warning("scheduler_ipc: socket failed: %s", strerror(errno));
        return -1;
    }

    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        rs_trace("scheduler_ipc: connect failed to %s: %s", endpoint, strerror(errno));
        goto out;
    }

    if (build_hosts_line(hosts_line, sizeof(hosts_line), hostlist) != 0) {
        rs_log_warning("scheduler_ipc: build hosts line failed");
        goto out;
    }

    int n = snprintf(req, sizeof(req),
                     "PICK\nhosts=%s\nfile=%s\n\n",
                     hosts_line,
                     input_file ? input_file : "");
    if (n < 0 || n >= (int)sizeof(req)) {
        rs_log_warning("scheduler_ipc: request too long");
        goto out;
    }

    if (write(fd, req, (size_t)n) != (ssize_t)n) {
        rs_trace("scheduler_ipc: write failed: %s", strerror(errno));
        goto out;
    }

    ssize_t r = read(fd, resp, sizeof(resp)-1);
    if (r <= 0) {
        rs_trace("scheduler_ipc: empty response");
        goto out;
    }
    resp[r] = '\0';

    /* Expect: index=<int> */
    int idx = -1;
    char *p = strstr(resp, "index=");
    if (p) {
        idx = atoi(p + 6);
    }
    if (idx < 0) {
        rs_trace("scheduler_ipc: invalid response: %s", resp);
        goto out;
    }

    /* Walk to that index */
    int i = 0;
    struct dcc_hostdef *h = hostlist;
    while (h && i < idx) { h = h->next; i++; }
    if (!h) {
        rs_trace("scheduler_ipc: index out of range: %d", idx);
        goto out;
    }

    *out_host = h;
    ret = 0;

out:
    if (fd >= 0) close(fd);
    return ret;
}
