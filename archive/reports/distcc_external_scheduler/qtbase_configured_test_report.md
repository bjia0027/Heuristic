# Qt Base 编译测试报告

## 测试信息
- **时间**: 2025-10-30 01:42:51
- **构建目录**: /home/jia/桌面/distcc-3.4/test_projects/qtbase/build-min
- **最大任务数**: 200

## 编译结果
- **总任务数**: 200
- **成功**: 171 (85.50%)
- **失败**: 29
- **跳过**: 0

## 性能指标
- **调度时间**: 0.17秒
- **编译时间**: 290.07秒
- **总时间**: 290.24秒

## 节点任务分配
- **node-5**: 34 任务 (17.0%)
- **localhost**: 34 任务 (17.0%)
- **node-4**: 33 任务 (16.5%)
- **node-1**: 33 任务 (16.5%)
- **node-3**: 33 任务 (16.5%)
- **node-2**: 33 任务 (16.5%)

## 失败任务详情 (前20个)

### qt_0086
- **节点**: node-1
- **返回码**: 1
- **错误**:
```
distcc[253661] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
cc1plus: fatal error: /home/jia/桌面/distcc-3.4/test_projects/qtbase/build-min/src/tools/rcc/rcc_autogen/mocs_compilation.cpp: 没有那个文件或目录
compilation terminated.
distcc[253661] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/build-min/src/tools/rcc/rcc_autogen/mocs_compilation.cpp on localhost failed

```

### qt_0101
- **节点**: node-2
- **返回码**: 1
- **错误**:
```
distcc[253802] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
cc1plus: fatal error: /home/jia/桌面/distcc-3.4/test_projects/qtbase/build-min/src/corelib/Core_autogen/mocs_compilation.cpp: 没有那个文件或目录
compilation terminated.
distcc[253802] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/build-min/src/corelib/Core_autogen/mocs_compilation.cpp on localhost failed

```

### qt_0123
- **节点**: node-3
- **返回码**: 1
- **错误**:
```
distcc[254024] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/ipc/qsharedmemory.cpp:689:10: fatal error: moc_qsharedmemory.cpp: 没有那个文件或目录
  689 | #include "moc_qsharedmemory.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254024] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/ipc/qsharedmemory.cpp on localhost failed

```

### qt_0124
- **节点**: node-2
- **返回码**: 1
- **错误**:
```
distcc[254028] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/ipc/qsystemsemaphore.cpp:400:10: fatal error: moc_qsystemsemaphore.cpp: 没有那个文件或目录
  400 | #include "moc_qsystemsemaphore.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254028] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/ipc/qsystemsemaphore.cpp on localhost failed

```

### qt_0125
- **节点**: localhost
- **返回码**: 1
- **错误**:
```
distcc[254032] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/ipc/qtipccommon.cpp:606:10: fatal error: moc_qtipccommon.cpp: 没有那个文件或目录
  606 | #include "moc_qtipccommon.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254032] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/ipc/qtipccommon.cpp on localhost failed

```

### qt_0127
- **节点**: node-4
- **返回码**: 1
- **错误**:
```
distcc[254043] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qbuffer.cpp:462:11: fatal error: moc_qbuffer.cpp: 没有那个文件或目录
  462 | # include "moc_qbuffer.cpp"
      |           ^~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254043] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qbuffer.cpp on localhost failed

```

### qt_0132
- **节点**: node-2
- **返回码**: 1
- **错误**:
```
distcc[254084] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qfile.cpp:1378:10: fatal error: moc_qfile.cpp: 没有那个文件或目录
 1378 | #include "moc_qfile.cpp"
      |          ^~~~~~~~~~~~~~~
compilation terminated.
distcc[254084] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qfile.cpp on localhost failed

```

### qt_0133
- **节点**: node-3
- **返回码**: 1
- **错误**:
```
distcc[254088] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qfiledevice.cpp:785:10: fatal error: moc_qfiledevice.cpp: 没有那个文件或目录
  785 | #include "moc_qfiledevice.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254088] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qfiledevice.cpp on localhost failed

```

### qt_0135
- **节点**: node-2
- **返回码**: 1
- **错误**:
```
distcc[254102] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qfileselector.cpp:341:10: fatal error: moc_qfileselector.cpp: 没有那个文件或目录
  341 | #include "moc_qfileselector.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254102] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qfileselector.cpp on localhost failed

```

### qt_0140
- **节点**: node-5
- **返回码**: 1
- **错误**:
```
distcc[254134] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qiodevice.cpp:2233:10: fatal error: moc_qiodevice.cpp: 没有那个文件或目录
 2233 | #include "moc_qiodevice.cpp"
      |          ^~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254134] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qiodevice.cpp on localhost failed

```

### qt_0145
- **节点**: node-4
- **返回码**: 1
- **错误**:
```
distcc[254164] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qnoncontiguousbytedevice.cpp:553:10: fatal error: moc_qnoncontiguousbytedevice_p.cpp: 没有那个文件或目录
  553 | #include "moc_qnoncontiguousbytedevice_p.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254164] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qnoncontiguousbytedevice.cpp o
```

### qt_0148
- **节点**: node-1
- **返回码**: 1
- **错误**:
```
distcc[254184] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qsavefile.cpp:412:10: fatal error: moc_qsavefile.cpp: 没有那个文件或目录
  412 | #include "moc_qsavefile.cpp"
      |          ^~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254184] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qsavefile.cpp on localhost failed

```

### qt_0149
- **节点**: node-3
- **返回码**: 1
- **错误**:
```
distcc[254188] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qstandardpaths.cpp:633:10: fatal error: moc_qstandardpaths.cpp: 没有那个文件或目录
  633 | #include "moc_qstandardpaths.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254188] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qstandardpaths.cpp on localhost failed

```

### qt_0152
- **节点**: localhost
- **返回码**: 1
- **错误**:
```
distcc[254208] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qtemporaryfile.cpp:986:10: fatal error: moc_qtemporaryfile.cpp: 没有那个文件或目录
  986 | #include "moc_qtemporaryfile.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254208] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/io/qtemporaryfile.cpp on localhost failed

```

### qt_0158
- **节点**: node-4
- **返回码**: 1
- **错误**:
```
distcc[254260] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qabstracteventdispatcher.cpp:457:10: fatal error: moc_qabstracteventdispatcher.cpp: 没有那个文件或目录
  457 | #include "moc_qabstracteventdispatcher.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254260] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qabstracteventdispatcher.cpp
```

### qt_0162
- **节点**: node-1
- **返回码**: 1
- **错误**:
```
distcc[254279] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qcoreapplication.cpp:3392:10: fatal error: moc_qcoreapplication.cpp: 没有那个文件或目录
 3392 | #include "moc_qcoreapplication.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254279] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qcoreapplication.cpp on localhost failed

```

### qt_0163
- **节点**: node-5
- **返回码**: 1
- **错误**:
```
distcc[254283] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qcoreevent.cpp:655:10: fatal error: moc_qcoreevent.cpp: 没有那个文件或目录
  655 | #include "moc_qcoreevent.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254283] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qcoreevent.cpp on localhost failed

```

### qt_0166
- **节点**: localhost
- **返回码**: 1
- **错误**:
```
distcc[254297] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qeventloop.cpp:452:10: fatal error: moc_qeventloop.cpp: 没有那个文件或目录
  452 | #include "moc_qeventloop.cpp"
      |          ^~~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254297] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qeventloop.cpp on localhost failed

```

### qt_0173
- **节点**: node-3
- **返回码**: 1
- **错误**:
```
distcc[254362] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qmimedata.cpp:661:10: fatal error: moc_qmimedata.cpp: 没有那个文件或目录
  661 | #include "moc_qmimedata.cpp"
      |          ^~~~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254362] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qmimedata.cpp on localhost failed

```

### qt_0174
- **节点**: node-4
- **返回码**: 1
- **错误**:
```
distcc[254366] (dcc_build_somewhere) Warning: failed to distribute, running locally instead
/home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qobject.cpp:5606:10: fatal error: moc_qobject.cpp: 没有那个文件或目录
 5606 | #include "moc_qobject.cpp"
      |          ^~~~~~~~~~~~~~~~~
compilation terminated.
distcc[254366] ERROR: compile /home/jia/桌面/distcc-3.4/test_projects/qtbase/src/corelib/kernel/qobject.cpp on localhost failed

```

