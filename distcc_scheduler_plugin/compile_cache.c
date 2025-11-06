#include "distcc_plugin.h"
#include <sys/stat.h>

#define MAX_CACHE_SIZE 1000

typedef struct {
    char file_path[256];
    size_t file_size;
    double compile_time;
} cache_entry_t;

static cache_entry_t g_cache[MAX_CACHE_SIZE];
static int g_cache_count = 0;
static char g_cache_file[512] = {0};

int compile_cache_init(void) {
    const char *home = getenv("HOME");
    if (!home) return -1;
    
    snprintf(g_cache_file, sizeof(g_cache_file), 
             "%s/.distcc/compile_cache.txt", home);
    
    /* 加载缓存 */
    FILE *f = fopen(g_cache_file, "r");
    if (!f) {
        PLUGIN_DEBUG("No existing cache file");
        return 0;
    }
    
    while (g_cache_count < MAX_CACHE_SIZE) {
        cache_entry_t *entry = &g_cache[g_cache_count];
        if (fscanf(f, "%255s %zu %lf\n",
                   entry->file_path, &entry->file_size, &entry->compile_time) != 3) {
            break;
        }
        g_cache_count++;
    }
    
    fclose(f);
    PLUGIN_DEBUG("Loaded %d cache entries", g_cache_count);
    return 0;
}

double compile_cache_estimate(const char *file_path, size_t file_size) {
    if (!file_path) {
        /* 基于文件大小的粗略估计 */
        return file_size * 0.00001; // 每字节 0.01ms
    }
    
    /* 查找精确匹配 */
    for (int i = 0; i < g_cache_count; i++) {
        if (strcmp(g_cache[i].file_path, file_path) == 0) {
            return g_cache[i].compile_time;
        }
    }
    
    /* 查找相似大小的文件 */
    double sum = 0;
    int count = 0;
    for (int i = 0; i < g_cache_count; i++) {
        long diff = labs((long)file_size - (long)g_cache[i].file_size);
        if (diff < (long)file_size * 0.3) { // ±30%
            sum += g_cache[i].compile_time;
            count++;
        }
    }
    
    if (count > 0) {
        return sum / count;
    }
    
    /* 默认估计 */
    return file_size * 0.00001;
}

void compile_cache_update(const char *file_path, size_t file_size, double time) {
    if (!file_path || g_cache_count >= MAX_CACHE_SIZE) return;
    
    /* 更新现有条目 */
    for (int i = 0; i < g_cache_count; i++) {
        if (strcmp(g_cache[i].file_path, file_path) == 0) {
            g_cache[i].file_size = file_size;
            g_cache[i].compile_time = time;
            return;
        }
    }
    
    /* 添加新条目 */
    cache_entry_t *entry = &g_cache[g_cache_count];
    strncpy(entry->file_path, file_path, sizeof(entry->file_path) - 1);
    entry->file_size = file_size;
    entry->compile_time = time;
    g_cache_count++;
}

void compile_cache_save(void) {
    if (g_cache_file[0] == '\0' || g_cache_count == 0) return;
    
    FILE *f = fopen(g_cache_file, "w");
    if (!f) {
        PLUGIN_LOG("Failed to save cache");
        return;
    }
    
    for (int i = 0; i < g_cache_count; i++) {
        fprintf(f, "%s %zu %.6f\n",
                g_cache[i].file_path,
                g_cache[i].file_size,
                g_cache[i].compile_time);
    }
    
    fclose(f);
    PLUGIN_DEBUG("Saved %d cache entries", g_cache_count);
}
