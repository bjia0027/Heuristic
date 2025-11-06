#include "distcc_plugin.h"

extern int plugin_lock_host(const char *, const struct dcc_hostdef *, int, int, int *);

int algo_random(struct dcc_hostdef *hostlist, int n_hosts,
                struct dcc_hostdef **buildhost, int *cpu_lock_fd)
{
    if (!hostlist || n_hosts == 0) {
        return EXIT_NO_HOSTS;
    }
    
    /* 使用时间和进程ID作为随机种子 */
    static int seeded = 0;
    if (!seeded) {
        srand(time(NULL) ^ getpid());
        seeded = 1;
    }
    
    /* 随机选择一个主机索引 */
    int target_idx = rand() % n_hosts;
    
    struct dcc_hostdef *selected = hostlist;
    for (int i = 0; i < target_idx; i++) {
        if (!selected->next) break;
        selected = selected->next;
    }
    
    PLUGIN_DEBUG("Random: selected host %s (index %d/%d)",
                 selected->hostname, target_idx, n_hosts);
    
    /* 尝试锁定该主机的任一可用槽位 */
    for (int slot = 0; slot < selected->n_slots; slot++) {
        int ret = plugin_lock_host("cpu", selected, slot, 0, cpu_lock_fd);
        
        if (ret == 0) {
            *buildhost = selected;
            PLUGIN_DEBUG("Random: locked host %s slot %d", selected->hostname, slot);
            return 0;
        } else if (ret != EXIT_BUSY) {
            PLUGIN_LOG("Random: lock error %d on %s:%d", ret, selected->hostname, slot);
            return ret;
        }
    }
    
    /* 选中的主机所有槽位都忙，尝试其他主机 */
    PLUGIN_DEBUG("Random: selected host %s is fully busy, trying others", selected->hostname);
    
    for (struct dcc_hostdef *h = hostlist; h; h = h->next) {
        if (h == selected) continue; // 跳过已尝试的
        
        for (int slot = 0; slot < h->n_slots; slot++) {
            int ret = plugin_lock_host("cpu", h, slot, 0, cpu_lock_fd);
            
            if (ret == 0) {
                *buildhost = h;
                PLUGIN_DEBUG("Random: fallback locked host %s slot %d", h->hostname, slot);
                return 0;
            } else if (ret != EXIT_BUSY) {
                return ret;
            }
        }
    }
    
    PLUGIN_LOG("Random: all hosts busy");
    return EXIT_BUSY;
}
