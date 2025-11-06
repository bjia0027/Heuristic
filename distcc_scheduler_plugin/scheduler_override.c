#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "distcc_plugin.h"

/* 原始函数指针（用于回退到原生算法）*/
typedef int (*original_pick_host_fn)(struct dcc_hostdef **, int *);
static original_pick_host_fn original_dcc_pick_host = NULL;

/* 原始的 dcc_lock_host 函数（需要调用）*/
typedef int (*dcc_lock_host_fn)(const char *, const struct dcc_hostdef *, int, int, int *);
static dcc_lock_host_fn dcc_lock_host_ptr = NULL;

/* 全局配置 */
static scheduler_algo_t g_algorithm = ALGO_NATIVE;
static int g_initialized = 0;

/* 初始化插件 */
static void plugin_init(void) __attribute__((constructor));

static void plugin_init(void) {
    if (g_initialized)
        return;
    
    PLUGIN_LOG("Distcc Scheduler Plugin initializing...");
    
    /* 读取算法配置 */
    const char *algo_env = getenv("DISTCC_ALGO");
    if (!algo_env || strcmp(algo_env, "native") == 0) {
        g_algorithm = ALGO_NATIVE;
        PLUGIN_LOG("Algorithm: NATIVE (plugin disabled)");
        g_initialized = 1;
        return;
    } else if (strcmp(algo_env, "random") == 0) {
        g_algorithm = ALGO_RANDOM;
        PLUGIN_LOG("Algorithm: RANDOM");
    } else if (strcmp(algo_env, "rr") == 0) {
        g_algorithm = ALGO_RR;
        PLUGIN_LOG("Algorithm: ROUND_ROBIN");
    } else if (strcmp(algo_env, "heft") == 0) {
        g_algorithm = ALGO_HEFT;
        PLUGIN_LOG("Algorithm: HEFT");
    } else {
        PLUGIN_LOG("Unknown algorithm '%s', using NATIVE", algo_env);
        g_algorithm = ALGO_NATIVE;
    }
    
    /* 加载原始函数指针 - 延迟到真正需要时 */
    if (g_algorithm != ALGO_NATIVE) {
        PLUGIN_DEBUG("Will lookup symbols on first use");
        
        /* 初始化共享状态（RR/HEFT需要）*/
        if (g_algorithm == ALGO_RR || g_algorithm == ALGO_HEFT) {
            if (shared_state_init() != 0) {
                PLUGIN_LOG("Warning: shared state init failed, falling back to RANDOM");
                g_algorithm = ALGO_RANDOM;
            }
        }
        
        /* 初始化编译缓存（HEFT需要）*/
        if (g_algorithm == ALGO_HEFT) {
            compile_cache_init();
        }
    }
    
    g_initialized = 1;
}

/* 清理插件 */
static void plugin_cleanup(void) __attribute__((destructor));

static void plugin_cleanup(void) {
    if (g_algorithm == ALGO_HEFT) {
        compile_cache_save();
    }
    shared_state_cleanup();
    PLUGIN_LOG("Plugin cleanup done");
}

/* 劫持的主机选择函数 */
int dcc_pick_host_from_list_and_lock_it(struct dcc_hostdef **buildhost,
                                        int *cpu_lock_fd)
{
    /* 确保初始化 */
    if (!g_initialized) {
        plugin_init();
    }
    
    /* 延迟加载符号（第一次调用时）*/
    if (!original_dcc_pick_host && g_algorithm != ALGO_NATIVE) {
        original_dcc_pick_host = dlsym(RTLD_DEFAULT, "dcc_pick_host_from_list_and_lock_it");
        PLUGIN_DEBUG("Late symbol lookup: dcc_pick_host=%p", original_dcc_pick_host);
    }
    
    if (!dcc_lock_host_ptr && g_algorithm != ALGO_NATIVE) {
        dcc_lock_host_ptr = dlsym(RTLD_DEFAULT, "dcc_lock_host");
        PLUGIN_DEBUG("Late symbol lookup: dcc_lock_host=%p", dcc_lock_host_ptr);
        
        if (!dcc_lock_host_ptr) {
            PLUGIN_LOG("Warning: dcc_lock_host not found, falling back to NATIVE");
            g_algorithm = ALGO_NATIVE;
        }
    }
    
    /* 如果是 NATIVE 或初始化失败，调用原始函数 */
    if (g_algorithm == ALGO_NATIVE) {
        if (original_dcc_pick_host) {
            return original_dcc_pick_host(buildhost, cpu_lock_fd);
        } else {
            PLUGIN_LOG("ERROR: native algorithm but no original function!");
            return EXIT_NO_HOSTS;
        }
    }
    
    /* 获取主机列表（通过调用 distcc 的函数）*/
    typedef int (*get_hostlist_fn)(struct dcc_hostdef **, int *);
    get_hostlist_fn dcc_get_hostlist = dlsym(RTLD_DEFAULT, "dcc_get_hostlist");
    if (!dcc_get_hostlist) {
        void *main_handle = dlopen(NULL, RTLD_LAZY);
        if (main_handle) {
            dcc_get_hostlist = dlsym(main_handle, "dcc_get_hostlist");
            dlclose(main_handle);
        }
    }
    
    struct dcc_hostdef *hostlist = NULL;
    int n_hosts = 0;
    int ret;
    
    if (!dcc_get_hostlist || (ret = dcc_get_hostlist(&hostlist, &n_hosts)) != 0) {
        PLUGIN_LOG("Failed to get hostlist, falling back to original");
        if (original_dcc_pick_host) {
            return original_dcc_pick_host(buildhost, cpu_lock_fd);
        }
        return EXIT_NO_HOSTS;
    }
    
    if (!hostlist || n_hosts == 0) {
        PLUGIN_LOG("Empty hostlist");
        return EXIT_NO_HOSTS;
    }
    
    PLUGIN_DEBUG("Got hostlist with %d hosts", n_hosts);
    
    /* 根据算法分发 */
    switch (g_algorithm) {
        case ALGO_RANDOM:
            ret = algo_random(hostlist, n_hosts, buildhost, cpu_lock_fd);
            break;
            
        case ALGO_RR:
            ret = algo_round_robin(hostlist, n_hosts, buildhost, cpu_lock_fd);
            break;
            
        case ALGO_HEFT: {
            const char *input_file = getenv("DISTCC_INPUT_FILE");
            ret = algo_heft(hostlist, n_hosts, buildhost, cpu_lock_fd, input_file);
            break;
        }
            
        default:
            PLUGIN_LOG("Unknown algorithm, falling back");
            if (original_dcc_pick_host) {
                return original_dcc_pick_host(buildhost, cpu_lock_fd);
            }
            return EXIT_NO_HOSTS;
    }
    
    /* 如果算法失败，回退到原始实现 */
    if (ret != 0) {
        PLUGIN_DEBUG("Algorithm failed with %d, trying original", ret);
        if (original_dcc_pick_host) {
            return original_dcc_pick_host(buildhost, cpu_lock_fd);
        }
    }
    
    return ret;
}

/* 导出 dcc_lock_host 给算法使用 */
int plugin_lock_host(const char *type, const struct dcc_hostdef *host,
                     int slot, int block, int *lock_fd)
{
    if (!dcc_lock_host_ptr) {
        dcc_lock_host_ptr = dlsym(RTLD_DEFAULT, "dcc_lock_host");
        if (!dcc_lock_host_ptr) {
            void *main_handle = dlopen(NULL, RTLD_LAZY);
            if (main_handle) {
                dcc_lock_host_ptr = dlsym(main_handle, "dcc_lock_host");
                dlclose(main_handle);
            }
        }
    }
    
    if (dcc_lock_host_ptr) {
        return dcc_lock_host_ptr(type, host, slot, block, lock_fd);
    }
    
    return -1;
}
