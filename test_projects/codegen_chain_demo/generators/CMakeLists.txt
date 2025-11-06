cmake_minimum_required(VERSION 3.16)

# 数据与脚本目录
set(GEN_SCRIPTS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/scripts)
set(GEN_DATA_DIR    ${CMAKE_CURRENT_SOURCE_DIR}/data)

# 确保生成目录存在
file(MAKE_DIRECTORY ${GEN_DIR})

# 收集所有生成产物
set(ALL_GEN_OUTPUTS)
set(ALL_GEN_SOURCES)

# 1) 配置头生成：config.in -> config.h
set(CONFIG_IN   ${GEN_DATA_DIR}/config.in)
set(CONFIG_OUT  ${GEN_DIR}/config.h)
add_custom_command(
  OUTPUT  ${CONFIG_OUT}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/gen_config.py ${CONFIG_IN} ${CONFIG_OUT}
  DEPENDS ${GEN_SCRIPTS_DIR}/gen_config.py ${CONFIG_IN}
  COMMENT "Generating config.h from config.in"
)
list(APPEND ALL_GEN_OUTPUTS ${CONFIG_OUT})

# 2) 批量处理多个 TableGen 文件 (ops*.td -> ops*_gen.h/cpp)
file(GLOB TD_FILES "${GEN_DATA_DIR}/ops*.td")
foreach(TD_FILE ${TD_FILES})
  get_filename_component(TD_NAME ${TD_FILE} NAME_WE)
  set(TD_OUT_H   ${GEN_DIR}/${TD_NAME}_gen.h)
  set(TD_OUT_CPP ${GEN_DIR}/${TD_NAME}_gen.cpp)
  add_custom_command(
    OUTPUT  ${TD_OUT_H} ${TD_OUT_CPP}
    COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/tblgen.py ${TD_FILE} ${TD_OUT_H} ${TD_OUT_CPP}
    DEPENDS ${GEN_SCRIPTS_DIR}/tblgen.py ${TD_FILE}
    COMMENT "Generating ${TD_NAME}_gen.[h|cpp] from ${TD_NAME}.td"
  )
  list(APPEND ALL_GEN_OUTPUTS ${TD_OUT_H} ${TD_OUT_CPP})
  list(APPEND ALL_GEN_SOURCES ${TD_OUT_CPP})
endforeach()

# 3) 批量处理多个 Proto 文件 (*.proto -> *.pb.h/cc)
file(GLOB PROTO_FILES "${GEN_DATA_DIR}/*.proto")
foreach(PROTO_FILE ${PROTO_FILES})
  get_filename_component(PROTO_NAME ${PROTO_FILE} NAME_WE)
  set(PROTO_OUT_H  ${GEN_DIR}/${PROTO_NAME}.pb.h)
  set(PROTO_OUT_CC ${GEN_DIR}/${PROTO_NAME}.pb.cc)
  add_custom_command(
    OUTPUT  ${PROTO_OUT_H} ${PROTO_OUT_CC}
    COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/protogen.py ${PROTO_FILE} ${PROTO_OUT_H} ${PROTO_OUT_CC}
    DEPENDS ${GEN_SCRIPTS_DIR}/protogen.py ${PROTO_FILE}
    COMMENT "Generating ${PROTO_NAME}.pb.[h|cc] from ${PROTO_NAME}.proto"
  )
  list(APPEND ALL_GEN_OUTPUTS ${PROTO_OUT_H} ${PROTO_OUT_CC})
  list(APPEND ALL_GEN_SOURCES ${PROTO_OUT_CC})
endforeach()

# 4) 批量处理多个 QRC 文件 (resources*.qrc -> qrc_resources*.cpp)
file(GLOB QRC_FILES "${GEN_DATA_DIR}/*.qrc")
foreach(QRC_FILE ${QRC_FILES})
  get_filename_component(QRC_NAME ${QRC_FILE} NAME_WE)
  set(QRC_OUT_CPP ${GEN_DIR}/qrc_${QRC_NAME}.cpp)
  add_custom_command(
    OUTPUT  ${QRC_OUT_CPP}
    COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/rcc.py ${QRC_FILE} ${QRC_OUT_CPP}
    DEPENDS ${GEN_SCRIPTS_DIR}/rcc.py ${QRC_FILE}
    COMMENT "Generating qrc_${QRC_NAME}.cpp from ${QRC_NAME}.qrc"
  )
  list(APPEND ALL_GEN_OUTPUTS ${QRC_OUT_CPP})
  list(APPEND ALL_GEN_SOURCES ${QRC_OUT_CPP})
endforeach()

# 5) MOC 简化：widget.h(Q_OBJECT) -> moc_widget.cpp
set(MOC_IN      ${GEN_DATA_DIR}/widget.h)
set(MOC_OUT_CPP ${GEN_DIR}/moc_widget.cpp)
add_custom_command(
  OUTPUT  ${MOC_OUT_CPP}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/moc.py ${MOC_IN} ${MOC_OUT_CPP}
  DEPENDS ${GEN_SCRIPTS_DIR}/moc.py ${MOC_IN}
  COMMENT "Generating moc_widget.cpp from widget.h"
)
list(APPEND ALL_GEN_OUTPUTS ${MOC_OUT_CPP})
list(APPEND ALL_GEN_SOURCES ${MOC_OUT_CPP})

# 汇总 codegen 目标
add_custom_target(codegen ALL
  DEPENDS ${ALL_GEN_OUTPUTS}
)

# 生成产物作为静态库，便于其它模块链接和建立依赖
set_source_files_properties(${ALL_GEN_SOURCES} PROPERTIES GENERATED TRUE)
add_library(generated STATIC ${ALL_GEN_SOURCES})
add_dependencies(generated codegen)
target_include_directories(generated PUBLIC ${GEN_DIR})
