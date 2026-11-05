include("/opt/mxe/usr/x86_64-w64-mingw32.shared/share/cmake/mxe-conf.cmake")
# Override MXE's source-Qt host tools when using an official prebuilt Windows Qt kit.
if(NOT "$ENV{EGLANTINE_QT_HOST}" STREQUAL "")
    set(QT_HOST_PATH "$ENV{EGLANTINE_QT_HOST}")
endif()
if(NOT "$ENV{EGLANTINE_QT_TARGET}" STREQUAL "")
    list(PREPEND CMAKE_FIND_ROOT_PATH "$ENV{EGLANTINE_QT_TARGET}")
endif()
