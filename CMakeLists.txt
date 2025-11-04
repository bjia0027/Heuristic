cmake_minimum_required(VERSION 3.10)
project(distcc_ext_scheduler_dummy C)

option(DISTCC_GEN_COMPILE_DB_ONLY "Only generate compile_commands.json without building binaries" ON)

# 收集源码（仅用于生成编译数据库，不改变原Autotools构建流程）
file(GLOB_RECURSE DISTCC_SRC
	src/*.c
)

if(NOT DISTCC_SRC)
	message(WARNING "No C sources found under src/ - compile database will be almost empty.")
endif()

add_library(distcc_compile_db_objects STATIC ${DISTCC_SRC})
target_include_directories(distcc_compile_db_objects PRIVATE src)

if(DISTCC_GEN_COMPILE_DB_ONLY)
	# 不需要真正链接最终可执行目标，只要对象文件触发编译命令列出
	add_custom_target(dummy_all DEPENDS distcc_compile_db_objects)
endif()

message(STATUS "Configured for compile_commands.json generation. Run: cmake -S . -B build && cmake --build build --target dummy_all -j")
