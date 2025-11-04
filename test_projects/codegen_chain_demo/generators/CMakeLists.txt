cmake_minimum_required(VERSION 3.16)

# 数据与脚本目录
set(GEN_SCRIPTS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/scripts)
set(GEN_DATA_DIR    ${CMAKE_CURRENT_SOURCE_DIR}/data)

# 确保生成目录存在
file(MAKE_DIRECTORY ${GEN_DIR})

# 1) 配置头生成：config.in -> config.h
set(CONFIG_IN   ${GEN_DATA_DIR}/config.in)
set(CONFIG_OUT  ${GEN_DIR}/config.h)
add_custom_command(
  OUTPUT  ${CONFIG_OUT}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/gen_config.py ${CONFIG_IN} ${CONFIG_OUT}
  DEPENDS ${GEN_SCRIPTS_DIR}/gen_config.py ${CONFIG_IN}
  COMMENT "Generating config.h from config.in"
)

# 2) TableGen 简化：ops.td -> ops_gen.h / ops_gen.cpp
set(TD_IN       ${GEN_DATA_DIR}/ops.td)
set(TD_OUT_H    ${GEN_DIR}/ops_gen.h)
set(TD_OUT_CPP  ${GEN_DIR}/ops_gen.cpp)
add_custom_command(
  OUTPUT  ${TD_OUT_H} ${TD_OUT_CPP}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/tblgen.py ${TD_IN} ${TD_OUT_H} ${TD_OUT_CPP}
  DEPENDS ${GEN_SCRIPTS_DIR}/tblgen.py ${TD_IN}
  COMMENT "Generating ops_gen.[h|cpp] from ops.td"
)

# 3) Proto 简化：messages.proto -> messages.pb.h / messages.pb.cc
set(PROTO_IN     ${GEN_DATA_DIR}/messages.proto)
set(PROTO_OUT_H  ${GEN_DIR}/messages.pb.h)
set(PROTO_OUT_CC ${GEN_DIR}/messages.pb.cc)
add_custom_command(
  OUTPUT  ${PROTO_OUT_H} ${PROTO_OUT_CC}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/protogen.py ${PROTO_IN} ${PROTO_OUT_H} ${PROTO_OUT_CC}
  DEPENDS ${GEN_SCRIPTS_DIR}/protogen.py ${PROTO_IN}
  COMMENT "Generating messages.pb.[h|cc] from messages.proto"
)

# 4) 资源编译简化：resources.qrc -> qrc_resources.cpp
set(QRC_IN      ${GEN_DATA_DIR}/resources.qrc)
set(QRC_OUT_CPP ${GEN_DIR}/qrc_resources.cpp)
add_custom_command(
  OUTPUT  ${QRC_OUT_CPP}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/rcc.py ${QRC_IN} ${QRC_OUT_CPP}
  DEPENDS ${GEN_SCRIPTS_DIR}/rcc.py ${QRC_IN}
  COMMENT "Generating qrc_resources.cpp from resources.qrc"
)

# 5) MOC 简化：widget.h(Q_OBJECT) -> moc_widget.cpp
set(MOC_IN      ${GEN_DATA_DIR}/widget.h)
set(MOC_OUT_CPP ${GEN_DIR}/moc_widget.cpp)
add_custom_command(
  OUTPUT  ${MOC_OUT_CPP}
  COMMAND ${Python3_EXECUTABLE} ${GEN_SCRIPTS_DIR}/moc.py ${MOC_IN} ${MOC_OUT_CPP}
  DEPENDS ${GEN_SCRIPTS_DIR}/moc.py ${MOC_IN}
  COMMENT "Generating moc_widget.cpp from widget.h"
)

# 汇总 codegen 目标
add_custom_target(codegen ALL
  DEPENDS ${CONFIG_OUT} ${TD_OUT_H} ${TD_OUT_CPP} ${PROTO_OUT_H} ${PROTO_OUT_CC} ${QRC_OUT_CPP} ${MOC_OUT_CPP}
)

# 生成产物作为静态库，便于其它模块链接和建立依赖
set(GEN_SOURCES ${TD_OUT_CPP} ${PROTO_OUT_CC} ${QRC_OUT_CPP} ${MOC_OUT_CPP})
set_source_files_properties(${GEN_SOURCES} PROPERTIES GENERATED TRUE)
add_library(generated STATIC ${GEN_SOURCES})
add_dependencies(generated codegen)
target_include_directories(generated PUBLIC ${GEN_DIR})
