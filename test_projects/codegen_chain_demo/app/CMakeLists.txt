cmake_minimum_required(VERSION 3.16)

file(GLOB APP_SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/*.cpp)

add_executable(codegen_app ${APP_SOURCES})
add_dependencies(codegen_app codegen)
target_link_libraries(codegen_app PRIVATE generated)
target_include_directories(codegen_app PRIVATE ${GEN_DIR})
