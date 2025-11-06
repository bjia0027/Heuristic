#ifndef DISTCC_PLUGIN_H
#define DISTCC_PLUGIN_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/types.h>

/* 从 distcc 原始头文件复制必要的结构定义 */

/* 主机模式 */
enum dcc_mode {
    DCC_MODE_TCP = 1,
    DCC_MODE_SSH,
    DCC_MODE_LOCAL
};

/* 主机定义（最小化版本，只包含调度需要的字段）*/
struct dcc_hostdef {
    enum dcc_mode mode;
    char *user;
    char *hostname;
    int port;
    char *ssh_command;
    int is_up;
    int n_slots;
    char *hostdef_string;
    /* 省略其他字段... */
    struct dcc_hostdef *next;
};

/* 调度算法枚举 */
typedef enum {
    ALGO_NATIVE,   // 使用 distcc 原生算法（不劫持）
    ALGO_RANDOM,   // 随机选择
    ALGO_RR,       // 轮转
    ALGO_HEFT      // 启发式最早完成时间
} scheduler_algo_t;

/* 共享状态结构 */
typedef struct {
    int rr_cursor;                // RR 游标
    double host_efts[64];         // HEFT 每主机的 EFT（最多支持64台主机）
    int initialized;              // 是否已初始化
} scheduler_state_t;

/* 函数声明 */

/* 算法实现 */
int algo_random(struct dcc_hostdef *hostlist, int n_hosts,
                struct dcc_hostdef **buildhost, int *cpu_lock_fd);

int algo_round_robin(struct dcc_hostdef *hostlist, int n_hosts,
                     struct dcc_hostdef **buildhost, int *cpu_lock_fd);

int algo_heft(struct dcc_hostdef *hostlist, int n_hosts,
              struct dcc_hostdef **buildhost, int *cpu_lock_fd,
              const char *input_file);

/* 共享状态管理 */
int shared_state_init(void);
scheduler_state_t* shared_state_lock(void);
void shared_state_unlock(void);
void shared_state_cleanup(void);

/* 编译时长缓存 */
int compile_cache_init(void);
double compile_cache_estimate(const char *file_path, size_t file_size);
void compile_cache_update(const char *file_path, size_t file_size, double time);
void compile_cache_save(void);

/* 辅助函数 */
int count_hosts(struct dcc_hostdef *hostlist);
double get_current_time(void);

/* 日志宏（简化版）*/
#define PLUGIN_LOG(fmt, ...) \
    fprintf(stderr, "[distcc-plugin] " fmt "\n", ##__VA_ARGS__)

#define PLUGIN_DEBUG(fmt, ...) \
    do { if (getenv("DISTCC_PLUGIN_DEBUG")) \
        fprintf(stderr, "[distcc-plugin DEBUG] " fmt "\n", ##__VA_ARGS__); \
    } while(0)

/* 错误码 */
#define EXIT_BUSY 115
#define EXIT_NO_HOSTS 110

#endif /* DISTCC_PLUGIN_H */
