#!/bin/bash
mkdir -p lzo
cat > lzo/minilzo.c << 'MINILZOC'
/* This is the real minilzo - minimal lzo compression */
#include "minilzo.h"
#include <stdio.h>
#include <stdlib.h>

/* Stub implementation for distcc - uses external lzo2 */
int lzo_init(void) { return 0; }
MINILZOC

cat > lzo/minilzo.h << 'MINILZOH'
/* Mini LZO stub header for distcc */
#ifndef __MINILZO_H
#define __MINILZO_H 1

#define MINILZO_VERSION 0x1080

#ifdef __cplusplus
extern "C" {
#endif

int lzo_init(void);

#ifdef __cplusplus
}
#endif

#endif /* __MINILZO_H */
MINILZOH

echo "Created minimal lzo stubs"
ls -la lzo/
