/* Minimal lzo stub implementation */
#include "minilzo.h"

int lzo_init(void) { return LZO_E_OK; }

int lzo1x_1_compress(const lzo_byte *src, lzo_uint src_len,
                     lzo_byte *dst, lzo_uint *dst_len,
                     void *wrkmem) {
    /* Stub: just copy data (no compression) */
    unsigned long i;
    (void)wrkmem;  /* unused */
    if (src_len > *dst_len) return LZO_E_OUTPUT_OVERRUN;
    for (i = 0; i < src_len; i++) dst[i] = src[i];
    *dst_len = src_len;
    return LZO_E_OK;
}

int lzo1x_decompress_safe(const lzo_byte *src, lzo_uint src_len,
                           lzo_byte *dst, lzo_uint *dst_len,
                           void *wrkmem) {
    /* Stub: just copy data (assumes no compression) */
    unsigned long i;
    (void)wrkmem;  /* unused */
    if (src_len > *dst_len) return LZO_E_OUTPUT_OVERRUN;
    for (i = 0; i < src_len; i++) dst[i] = src[i];
    *dst_len = src_len;
    return LZO_E_OK;
}
