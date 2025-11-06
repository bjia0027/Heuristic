#include "distcc_plugin.h"

extern int plugin_lock_host(const char *, const struct dcc_hostdef *, int, int, int *);

int algo_round_robin(struct dcc_hostdef *hostlist, int n_hosts,
                     struct dcc_hostdef **buildhost, int *cpu_lock_fd)
{
    if (!hostlist || n_hosts == 0) {
        return EXIT_NO_HOSTS;
    }
    
    /* 加锁获取共享状态 */
    scheduler_state_t *state = shared_state_lock();
    if (!state) {
        PLUGIN_LOG("RR: failed to lock state, falling back to random");
        return algo_random(hostlist, n_hosts, buildhost, cpu_lock_fd);
    }
    
    /* 读取并更新游标 */
    int cursor = state->rr_cursor;
    int target_idx = cursor % n_hosts;
    state->rr_cursor = cursor + 1;
    
    /* 解锁（尽早释放）*/
    shared_state_unlock();
    
    /* 选择目标主机 */
    struct dcc_hostdef *selected = hostlist;
    for (int i = 0; i < target_idx; i++) {
        if (!selected->next) break;
        selected = selected->next;
    }
    
    PLUGIN_DEBUG("RR: cursor=%d, selected host %s (index %d/%d)",
                 cursor, selected->hostname, target_idx, n_hosts);
    
    /* 尝试锁定该主机的任一可用槽位 */
    for (int slot = 0; slot < selected->n_slots; slot++) {
        int ret = plugin_lock_host("cpu", selected, slot, 0, cpu_lock_fd);
        
        if (ret == 0) {
            *buildhost = selected;
            PLUGIN_DEBUG("RR: locked host %s slot %d", selected->hostname, slot);
            return 0;
        } else if (ret != EXIT_BUSY) {
            return ret;
        }
    }
    
    /* 选中的主机满了，尝试其他主机 */
    PLUGIN_DEBUG("RR: selected host %s is busy, trying others", selected->hostname);
    
    for (struct dcc_hostdef *h = hostlist; h; h = h->next) {
        if (h == selected) continue;
        
        for (int slot = 0; slot < h->n_slots; slot++) {
            int ret = plugin_lock_host("cpu", h, slot, 0, cpu_lock_fd);
            
            if (ret == 0) {
                *buildhost = h;
                PLUGIN_DEBUG("RR: fallback locked host %s slot %d", h->hostname, slot);
                return 0;
            } else if (ret != EXIT_BUSY) {
                return ret;
            }
        }
    }
    
    return EXIT_BUSY;
}
