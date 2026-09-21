cmake_minimum_required(VERSION 3.28)

# LuxScale C++ physics core (luxcore extension).
#
# NOTE: this file deliberately avoids find_package(Python Development.*):
# some environments (e.g. distro venvs without python3-dev installed
# system-wide) lack /usr/include/python3.X/Python.h. The Dijon fallback
# below honours LUXCORE_PYTHON_INCLUDE so headers extracted anywhere
# (e.g. from the python3.14-dev .deb into /tmp) keep the build working.
# nanobind is consumed as headers + nb_combined.cpp (no nanobind CONFIG
# package needed), and libpython is NOT linked on Linux (symbols resolve
# from the loading interpreter).

project(luxscale_cpp VERSION 2.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python 3.11 COMPONENTS Interpreter REQUIRED)
find_package(OpenMP)

# --- resolve Python include dir (headers only; no link needed on Linux) ---
execute_process(
  COMMAND "${Python_EXECUTABLE}" -c
          "import sysconfig; print(sysconfig.get_config_var('INCLUDEPY'))"
  OUTPUT_STRIP_TRAILING_WHITESPACE
  OUTPUT_VARIABLE _LUX_PY_INCLUDE)
if(DEFINED ENV{LUXCORE_PYTHON_INCLUDE} AND NOT "$ENV{LUXCORE_PYTHON_INCLUDE}" STREQUAL "")
  set(_LUX_PY_INCLUDE "$ENV{LUXCORE_PYTHON_INCLUDE}")
endif()
if(NOT EXISTS "${_LUX_PY_INCLUDE}/Python.h")
  # Well-known user-space fallback (see scripts/build_luxcore.py docs).
  foreach(_cand "/tmp/pydev/root/usr/include/python3.14" "/usr/include/python3.14"
                "/usr/local/include/python3.14")
    if(EXISTS "${_cand}/Python.h")
      set(_LUX_PY_INCLUDE "${_cand}")
      break()
    endif()
  endforeach()
endif()
if(NOT EXISTS "${_LUX_PY_INCLUDE}/Python.h")
  message(FATAL_ERROR "Python.h not found (tried ${_LUX_PY_INCLUDE}). "
                      "Set LUXCORE_PYTHON_INCLUDE to the python3.14 headers dir.")
endif()
message(STATUS "LuxCore Python headers: ${_LUX_PY_INCLUDE}")
# Platform pyconfig lives one level up (<prefix>/include/x86_64-linux-gnu/...).
get_filename_component(_LUX_PY_INCLUDE_PARENT "${_LUX_PY_INCLUDE}" DIRECTORY)

execute_process(
  COMMAND "${Python_EXECUTABLE}" -c "import nanobind, os; print(os.path.dirname(nanobind.__file__))"
  OUTPUT_STRIP_TRAILING_WHITESPACE
  OUTPUT_VARIABLE _LUX_NB_DIR)
execute_process(
  COMMAND "${Python_EXECUTABLE}" -c "import numpy; print(numpy.get_include())"
  OUTPUT_STRIP_TRAILING_WHITESPACE
  OUTPUT_VARIABLE _LUX_NP_INCLUDE)
execute_process(
  COMMAND "${Python_EXECUTABLE}" -c
          "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))"
  OUTPUT_STRIP_TRAILING_WHITESPACE
  OUTPUT_VARIABLE _LUX_EXT_SUFFIX)

add_subdirectory(luxcore)
