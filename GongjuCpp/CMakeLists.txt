cmake_minimum_required(VERSION 3.16)
project(GongjuCpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

add_executable(GongjuCpp WIN32
  src/main.cpp
  src/adb_helper.cpp
  src/main_window.cpp
  src/log_viewer.cpp
  src/adb_browser.cpp
  src/screen_mirror.cpp
)

target_compile_definitions(GongjuCpp PRIVATE UNICODE _UNICODE)
target_link_libraries(GongjuCpp PRIVATE
  user32 gdi32 kernel32 shell32 ole32 gdiplus
)

if(MSVC)
  target_compile_options(GongjuCpp PRIVATE /W4 /utf-8)
  set_target_properties(GongjuCpp PROPERTIES
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
endif()
