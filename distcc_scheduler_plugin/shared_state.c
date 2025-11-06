#include "distcc_plugin.h"
#include <sys/file.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

static int g_state_fd = -1;
static int g_lock_fd = -1;
static scheduler_state_t *g_state = NULL;

int shared_state_init(void) {
    if (g_state != NULL) {
        return 0; // 已初始化
    }
    
    /* 获取状态文件路径 */
    const char *home = getenv("HOME");
    if (!home) {
        PLUGIN_LOG("HOME not set, shared state disabled");
        return -1;
    }
    
    char state_path[512];
    char lock_path[512];
    snprintf(state_path, sizeof(state_path), "%s/.distcc/scheduler_state.dat", home);
    snprintf(lock_path, sizeof(lock_path), "%s/.distcc/scheduler.lock", home);
    
    /* 确保目录存在 */
    char mkdir_cmd[600];
    snprintf(mkdir_cmd, sizeof(mkdir_cmd), "mkdir -p %s/.distcc", home);
    system(mkdir_cmd);
    
    /* 打开状态文件 */
    g_state_fd = open(state_path, O_RDWR | O_CREAT, 0600);
    if (g_state_fd < 0) {
        PLUGIN_LOG("Failed to open state file: %s", strerror(errno));
        return -1;
    }
    
    /* 设置文件大小 */
    if (ftruncate(g_state_fd, sizeof(scheduler_state_t)) < 0) {
        PLUGIN_LOG("ftruncate failed: %s", strerror(errno));
        close(g_state_fd);
        return -1;
    }
    
    /* 映射到内存 */
    g_state = mmap(NULL, sizeof(scheduler_state_t), PROT_READ | PROT_WRITE,
                   MAP_SHARED, g_state_fd, 0);
    if (g_state == MAP_FAILED) {
        PLUGIN_LOG("mmap failed: %s", strerror(errno));
        close(g_state_fd);
        g_state = NULL;
        return -1;
    }
    
    /* 打开锁文件 */
    g_lock_fd = open(lock_path, O_RDWR | O_CREAT, 0600);
    if (g_lock_fd < 0) {
        PLUGIN_LOG("Failed to open lock file: %s", strerror(errno));
        munmap(g_state, sizeof(scheduler_state_t));
        close(g_state_fd);
        g_state = NULL;
        return -1;
    }
    
    PLUGIN_DEBUG("Shared state initialized at %s", state_path);
    return 0;
}

scheduler_state_t* shared_state_lock(void) {
    if (!g_state || g_lock_fd < 0) {
        return NULL;
    }
    
    /* 加独占锁，非阻塞尝试 */
    if (flock(g_lock_fd, LOCK_EX | LOCK_NB) == 0) {
        return g_state;
    }
    
    /* 阻塞等待，最多100ms */
    struct timeval tv_start, tv_now;
    gettimeofday(&tv_start, NULL);
    
    while (1) {
        if (flock(g_lock_fd, LOCK_EX | LOCK_NB) == 0) {
            return g_state;
        }
        
        usleep(1000); // 1ms
        
        gettimeofday(&tv_now, NULL);
        long elapsed_ms = (tv_now.tv_sec - tv_start.tv_sec) * 1000 +
                         (tv_now.tv_usec - tv_start.tv_usec) / 1000;
        
        if (elapsed_ms > 100) {
            PLUGIN_LOG("Lock timeout after %ld ms", elapsed_ms);
            return NULL;
        }
    }
}

void shared_state_unlock(void) {
    if (g_lock_fd >= 0) {
        flock(g_lock_fd, LOCK_UN);
    }
}

void shared_state_cleanup(void) {
    if (g_state) {
        munmap(g_state, sizeof(scheduler_state_t));
        g_state = NULL;
    }
    if (g_state_fd >= 0) {
        close(g_state_fd);
        g_state_fd = -1;
    }
    if (g_lock_fd >= 0) {
        close(g_lock_fd);
        g_lock_fd = -1;
    }
}
