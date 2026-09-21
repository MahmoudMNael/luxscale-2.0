# Builds the `luxcore` Python extension module from C++ sources +
# nanobind's combined translation unit (NB_STATIC, no separate lib).
# Variables _LUX_PY_INCLUDE / _LUX_NB_DIR / _LUX_NP_INCLUDE / _LUX_EXT_SUFFIX
# are provided by the top-level CMakeLists.

set(_LUX_SOURCES
    src/bindings.cpp
    src/vector_math.cpp
    src/ies.cpp
    src/patch_set.cpp
    src/fixture.cpp
    src/visibility_policy.cpp
    src/direct_engine.cpp
    src/radiosity_solver.cpp
    src/geometry_engine.cpp
    src/matrix_ops.cpp
    "${_LUX_NB_DIR}/src/nb_combined.cpp")

add_library(luxcore MODULE ${_LUX_SOURCES})

target_include_directories(
  luxcore
  PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include
          ${_LUX_PY_INCLUDE}
          ${_LUX_PY_INCLUDE_PARENT}
          ${_LUX_NB_DIR}/include
          ${_LUX_NB_DIR}/ext/robin_map/include
          ${_LUX_NP_INCLUDE})

target_compile_definitions(luxcore PRIVATE NB_STATIC)
if(OpenMP_CXX_FOUND)
  target_link_libraries(luxcore PRIVATE OpenMP::OpenMP_CXX)
  target_compile_definitions(luxcore PRIVATE LUXCORE_HAS_OPENMP=1)
endif()

target_compile_options(
  luxcore
  PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/O2 /W4 /EHsc>
          $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-O3
          -Wall
          -Wextra
          -Wpedantic
          -fvisibility=hidden
          -ffast-math
          -fno-math-errno>)

# Emit `luxcore<EXT_SUFFIX>` at the repo root for in-place development.
set_target_properties(
  luxcore
  PROPERTIES PREFIX ""
             SUFFIX "${_LUX_EXT_SUFFIX}"
             LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
             ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
             OUTPUT_NAME "luxcore")

install(FILES "$<TARGET_FILE:luxcore>" DESTINATION .)
