/* miniLZO - mini subset of the LZO real-time data compression library */
#ifndef __MINILZO_H
#define __MINILZO_H 1

#define MINILZO_VERSION 0x1080

#ifdef __cplusplus
extern "C" {
#endif

/* lzo_uint should match size_t */
#if !defined(__LZO_UINT_H)
#define __LZO_UINT_H 1
#if defined(__SIZE_TYPE__)
typedef __SIZE_TYPE__ lzo_uint;
#else
typedef unsigned long lzo_uint;
#endif
#endif

typedef unsigned char lzo_byte;
typedef lzo_uint lzo_uint32;

#define LZO_E_OK                    0
#define LZO_E_ERROR                 (-1)
#define LZO_E_OUT_OF_MEMORY         (-2)
#define LZO_E_NOT_COMPRESSIBLE      (-3)
#define LZO_E_INPUT_OVERRUN         (-4)
#define LZO_E_OUTPUT_OVERRUN        (-5)
#define LZO_E_LOOKBEHIND_OVERRUN    (-6)
#define LZO_E_EOF_NOT_FOUND         (-7)
#define LZO_E_INPUT_NOT_CONSUMED    (-8)
#define LZO_E_NOT_YET_IMPLEMENTED   (-9)

#define LZO1X_1_MEM_COMPRESS    ((lzo_uint32) (16384L * sizeof(unsigned char *)))

/* function prototypes */
int lzo_init(void);
int lzo1x_1_compress(const lzo_byte *src, lzo_uint src_len,
                     lzo_byte *dst, lzo_uint *dst_len,
                     void *wrkmem);
int lzo1x_decompress_safe(const lzo_byte *src, lzo_uint src_len,
                           lzo_byte *dst, lzo_uint *dst_len,
                           void *wrkmem);

#ifdef __cplusplus
}
#endif

#endif /* __MINILZO_H */
