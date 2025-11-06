#include "distcc_plugin.h"
#include <sys/stat.h>
#include <sys/time.h>

extern int plugin_lock_host(const char *, const struct dcc_hostdef *, int, int, int *);

double get_current_time(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + tv.tv_usec / 1000000.0;
}

int algo_heft(struct dcc_hostdef *hostlist, int n_hosts,
              struct dcc_hostdef **buildhost, int *cpu_lock_fd,
              const char *input_file)
{
    if (!hostlist || n_hosts == 0) {
        return EXIT_NO_HOSTS;
    }
    
    /* 估计编译时长 */
    double estimated_time = 1.0;
    size_t file_size = 0;
    
    if (input_file) {
        struct stat st;
        if (stat(input_file, &st) == 0) {
            file_size = st.st_size;
            estimated_time = compile_cache_estimate(input_file, file_size);
            PLUGIN_DEBUG("HEFT: estimated time for %s (size=%zu) = %.3f s",
                         input_file, file_size, estimated_time);
        }
    }
    
    /* 加锁获取共享状态 */
    scheduler_state_t *state = shared_state_lock();
    if (!state) {
        PLUGIN_LOG("HEFT: failed to lock state, falling back");
        return algo_random(hostlist, n_hosts, buildhost, cpu_lock_fd);
    }
    
    /* 初始化状态（首次） */
    if (!state->initialized) {
        for (int i = 0; i < 64; i++) {
            state->host_efts[i] = 0.0;
        }
        state->initialized = 1;
    }
    
    /* 计算每个主机的 EFT */
    double current_time = get_current_time();
    struct dcc_hostdef *best_host = NULL;
    int best_idx = -1;
    double min_eft = 1e9;
    
    struct dcc_hostdef *h = hostlist;
    for (int i = 0; i < n_hosts && i < 64; i++, h = h->next) {
        if (!h) break;
        
        double start_time = (state->host_efts[i] > current_time) ? 
                           state->host_efts[i] : current_time;
        
        /* EFT = start + duration / slots */
        double eft = start_time + estimated_time / (h->n_slots > 0 ? h->n_slots : 1);
        
        PLUGIN_DEBUG("HEFT: host %s slots=%d eft_old=%.3f eft_new=%.3f",
                     h->hostname, h->n_slots, state->host_efts[i], eft);
        
        if (eft < min_eft) {
            min_eft = eft;
            best_host = h;
            best_idx = i;
        }
    }
    
    /* 更新选中主机的 EFT */
    if (best_idx >= 0 && best_idx < 64) {
        state->host_efts[best_idx] = min_eft;
    }
    
    /* 解锁 */
    shared_state_unlock();
    
    if (!best_host) {
        return EXIT_NO_HOSTS;
    }
    
    PLUGIN_DEBUG("HEFT: selected host %s (eft=%.3f)", best_host->hostname, min_eft);
    
    /* 尝试锁定该主机 */
    for (int slot = 0; slot < best_host->n_slots; slot++) {
        int ret = plugin_lock_host("cpu", best_host, slot, 0, cpu_lock_fd);
        
        if (ret == 0) {
            *buildhost = best_host;
            PLUGIN_DEBUG("HEFT: locked host %s slot %d", best_host->hostname, slot);
            return 0;
        } else if (ret != EXIT_BUSY) {
            return ret;
        }
    }
    
    /* 选中的主机满了，尝试其他主机 */
    PLUGIN_DEBUG("HEFT: selected host %s is busy, trying others", best_host->hostname);
    
    for (struct dcc_hostdef *h = hostlist; h; h = h->next) {
        if (h == best_host) continue;
        
        for (int slot = 0; slot < h->n_slots; slot++) {
            int ret = plugin_lock_host("cpu", h, slot, 0, cpu_lock_fd);
            
            if (ret == 0) {
                *buildhost = h;
                PLUGIN_DEBUG("HEFT: fallback locked host %s slot %d", h->hostname, slot);
                return 0;
            } else if (ret != EXIT_BUSY) {
                return ret;
            }
        }
    }
    
    return EXIT_BUSY;
}
