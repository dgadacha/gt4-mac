# Hardened VU1 emitter, fixtures and controls. Included from the root project
# after native/, which provides ps2runtime_vulkan for the differential test.
# Tests are registered by the root CMakeLists.txt so CTest sees them.

# The donor lives in the assets checkout (GT4_ASSETS_ROOT, set by native/; a worktree has no private/).
set(GT4_VU_DONOR "${GT4_ASSETS_ROOT}/private/references/ps2-web-recomp")
if(NOT EXISTS "${GT4_VU_DONOR}/runtime/include/ps2/vu_ops.hpp")
    message(FATAL_ERROR "vu_recomp requires the pinned donor checkout under private/references")
endif()

set(VU_RECOMP_SRC "${CMAKE_CURRENT_SOURCE_DIR}/src")
set(VU_RECOMP_TESTS "${CMAKE_CURRENT_SOURCE_DIR}/tests")
set(VU_DONOR_INCLUDES "${GT4_VU_DONOR}/runtime/include" "${GT4_VU_DONOR}/runtime/src")

add_library(gt4_vu_recomp_core STATIC "${VU_RECOMP_SRC}/vurecomp.cpp" "${VU_RECOMP_SRC}/sha256.cpp")
target_include_directories(gt4_vu_recomp_core PUBLIC "${VU_RECOMP_SRC}" ${VU_DONOR_INCLUDES})
target_compile_options(gt4_vu_recomp_core PRIVATE ${GT4_WARNING_FLAGS})

add_executable(gt4_vu_recomp "${VU_RECOMP_SRC}/vurecomp_main.cpp")
target_link_libraries(gt4_vu_recomp PRIVATE gt4_vu_recomp_core)
target_compile_options(gt4_vu_recomp PRIVATE ${GT4_WARNING_FLAGS})

add_library(gt4_vu_fixtures STATIC "${VU_RECOMP_TESTS}/vu_fixtures.cpp")
target_include_directories(gt4_vu_fixtures PUBLIC "${VU_RECOMP_TESTS}" ${VU_DONOR_INCLUDES})
target_compile_options(gt4_vu_fixtures PRIVATE ${GT4_WARNING_FLAGS})

add_executable(gt4_vu_fixture_writer "${VU_RECOMP_TESTS}/fixture_writer.cpp")
target_link_libraries(gt4_vu_fixture_writer PRIVATE gt4_vu_fixtures)
target_compile_options(gt4_vu_fixture_writer PRIVATE ${GT4_WARNING_FLAGS})

add_executable(gt4_vu_recomp_core_tests "${VU_RECOMP_TESTS}/core_tests.cpp")
target_link_libraries(gt4_vu_recomp_core_tests PRIVATE gt4_vu_recomp_core gt4_vu_fixtures)
target_compile_options(gt4_vu_recomp_core_tests PRIVATE ${GT4_WARNING_FLAGS})

# Build-time corpus and generation. Both output directories are removed and
# recreated inside the build tree, never in the source tree or the donor.
set(VU_GENERATED_ROOT "${CMAKE_BINARY_DIR}/vu_recomp")
set(VU_CORPUS_DIR "${VU_GENERATED_ROOT}/corpus")
set(VU_OUTPUT_DIR "${VU_GENERATED_ROOT}/generated")
set(VU_GENERATED_SOURCE "${VU_OUTPUT_DIR}/vu1_generated.cpp")
add_custom_command(
    OUTPUT "${VU_GENERATED_SOURCE}" "${VU_OUTPUT_DIR}/manifest.json"
    COMMAND "${CMAKE_COMMAND}" -E rm -rf "${VU_CORPUS_DIR}" "${VU_OUTPUT_DIR}"
    COMMAND $<TARGET_FILE:gt4_vu_fixture_writer> "${VU_CORPUS_DIR}"
    COMMAND $<TARGET_FILE:gt4_vu_recomp> "${VU_CORPUS_DIR}" "${VU_OUTPUT_DIR}"
    DEPENDS gt4_vu_fixture_writer gt4_vu_recomp
    VERBATIM)
set_source_files_properties("${VU_GENERATED_SOURCE}" PROPERTIES GENERATED TRUE)

set(GT4_VU_CORPUS_DIR "" CACHE PATH "Optional recorded VU1 corpus directory for gt4_vu_corpus_differential (read only, never copied)")

add_executable(gt4_vu_differential_tests "${VU_RECOMP_TESTS}/differential_tests.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp" "${VU_GENERATED_SOURCE}")
target_include_directories(gt4_vu_differential_tests PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
target_link_libraries(gt4_vu_differential_tests PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
target_compile_options(gt4_vu_differential_tests PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)

# Corpus differential: the table is generated from GT4_VU_CORPUS_DIR at build time.
# Without it, an empty table is written so the test reports a skip.
set(VU_CORPUS_OUTPUT_DIR "${VU_GENERATED_ROOT}/corpus_table")
set(VU_CORPUS_SOURCE "${VU_CORPUS_OUTPUT_DIR}/vu1_generated.cpp")
if(GT4_VU_CORPUS_DIR)
    if(NOT IS_DIRECTORY "${GT4_VU_CORPUS_DIR}")
        message(FATAL_ERROR "GT4_VU_CORPUS_DIR is not a directory")
    endif()
    add_custom_command(
        OUTPUT "${VU_CORPUS_SOURCE}" "${VU_CORPUS_OUTPUT_DIR}/manifest.json"
        COMMAND "${CMAKE_COMMAND}" -E rm -rf "${VU_CORPUS_OUTPUT_DIR}"
        COMMAND $<TARGET_FILE:gt4_vu_recomp> "${GT4_VU_CORPUS_DIR}" "${VU_CORPUS_OUTPUT_DIR}"
        DEPENDS gt4_vu_recomp
        VERBATIM)
else()
    file(MAKE_DIRECTORY "${VU_CORPUS_OUTPUT_DIR}")
    file(WRITE "${VU_CORPUS_SOURCE}" "#include \"vu_recomp_contract.hpp\"

namespace gt4::vugen::generated {
extern const ProgramEntry kPrograms[] = {{0u, 0u, false, false, \"\", nullptr}};
extern const std::uint32_t kProgramCount = 0u;
}
")
endif()
set_source_files_properties("${VU_CORPUS_SOURCE}" PROPERTIES GENERATED TRUE)
# TASK-010: the corpus table is compiled once as an OBJECT library and linked into every executable
# that replays it (mismatch replay, corpus differential, flag benchmark). Before, each executable
# compiled its own copy (three times for a 426-file corpus).
add_library(gt4_vu_corpus_table OBJECT "${VU_CORPUS_SOURCE}")
target_include_directories(gt4_vu_corpus_table PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
target_link_libraries(gt4_vu_corpus_table PRIVATE ps2runtime_vulkan gt4_vu_fixtures)
target_compile_options(gt4_vu_corpus_table PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)
add_executable(gt4_vu1_mismatch_replay "${VU_RECOMP_TESTS}/vu1_mismatch_replay.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp" $<TARGET_OBJECTS:gt4_vu_corpus_table>)
target_include_directories(gt4_vu1_mismatch_replay PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
target_link_libraries(gt4_vu1_mismatch_replay PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
target_compile_options(gt4_vu1_mismatch_replay PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)
add_executable(gt4_vu_corpus_differential "${VU_RECOMP_TESTS}/corpus_differential_tests.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp" $<TARGET_OBJECTS:gt4_vu_corpus_table>)
target_include_directories(gt4_vu_corpus_differential PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
target_link_libraries(gt4_vu_corpus_differential PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
target_compile_options(gt4_vu_corpus_differential PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)

# Flag-elision benchmark: the corpus table with flag elision next to the same corpus
# emitted with the donor flag behaviour (namespace gt4::vugen::baseline). Corpus only.
if(GT4_VU_CORPUS_DIR)
    set(VU_BASELINE_OUTPUT_DIR "${VU_GENERATED_ROOT}/corpus_baseline")
    set(VU_BASELINE_SOURCE "${VU_BASELINE_OUTPUT_DIR}/vu1_generated.cpp")
    add_custom_command(
        OUTPUT "${VU_BASELINE_SOURCE}" "${VU_BASELINE_OUTPUT_DIR}/manifest.json"
        COMMAND "${CMAKE_COMMAND}" -E rm -rf "${VU_BASELINE_OUTPUT_DIR}"
        COMMAND $<TARGET_FILE:gt4_vu_recomp> --no-flag-elision --namespace gt4::vugen::baseline "${GT4_VU_CORPUS_DIR}" "${VU_BASELINE_OUTPUT_DIR}"
        DEPENDS gt4_vu_recomp
        VERBATIM)
    set_source_files_properties("${VU_BASELINE_SOURCE}" PROPERTIES GENERATED TRUE)
    # EXCLUDE_FROM_ALL: the baseline table (about 204 CPU-s, serial) is not part of the default build.
    # Build it on demand: cmake --build <build-dir> --target gt4_vu1_flag_bench
    # No CTest target depends on this executable.
    add_executable(gt4_vu1_flag_bench EXCLUDE_FROM_ALL "${VU_RECOMP_TESTS}/vu1_flag_bench.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp" $<TARGET_OBJECTS:gt4_vu_corpus_table> "${VU_BASELINE_SOURCE}")
    target_include_directories(gt4_vu1_flag_bench PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
    target_link_libraries(gt4_vu1_flag_bench PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
    target_compile_options(gt4_vu1_flag_bench PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)
endif()

# VU1 AOT registry controls: only with the AOT capsule, which provides the runtime
# overlay and the game table (GT4_VU1_GENERATED_DIR).
if(GT4_VU1_GENERATED_DIR)
    add_executable(gt4_vu1_aot_registry_test "${VU_RECOMP_TESTS}/vu1_aot_registry_test.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp")
    target_include_directories(gt4_vu1_aot_registry_test PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
    target_link_libraries(gt4_vu1_aot_registry_test PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
    target_compile_options(gt4_vu1_aot_registry_test PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)
endif()

# VU0 emitter controls (slice 160): synthetic images, no capsule needed.
add_executable(gt4_vu0_emitter_tests "${VU_RECOMP_TESTS}/vu0_emitter_tests.cpp")
target_include_directories(gt4_vu0_emitter_tests PRIVATE "${VU_RECOMP_SRC}")
target_link_libraries(gt4_vu0_emitter_tests PRIVATE gt4_vu_recomp_core)
target_compile_options(gt4_vu0_emitter_tests PRIVATE ${GT4_WARNING_FLAGS})

# VU0 AOT controls (slice 160): only with the VU0 capsule (GT4_VU0_GENERATED_DIR), which provides the
# overlay and the VU0 table. The pinned image is read at run time (GT4_VU0_IMAGE_FILE, read only).
set(GT4_VU0_IMAGE_FILE "${GT4_ASSETS_ROOT}/private/slice160-vu0-image/vu0_image.bin" CACHE FILEPATH
    "Pinned VU0 image (scripts/vu0_image.py build) for the VU0 AOT controls, read only")
if(GT4_VU0_GENERATED_DIR)
    add_executable(gt4_vu0_differential_tests "${VU_RECOMP_TESTS}/vu0_differential_tests.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp")
    target_include_directories(gt4_vu0_differential_tests PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
    target_link_libraries(gt4_vu0_differential_tests PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
    target_compile_options(gt4_vu0_differential_tests PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)
    add_executable(gt4_vu0_aot_registry_test "${VU_RECOMP_TESTS}/vu0_aot_registry_test.cpp" "${VU_RECOMP_TESTS}/gif_capture.cpp")
    target_include_directories(gt4_vu0_aot_registry_test PRIVATE "${VU_RECOMP_SRC}" "${VU_RECOMP_TESTS}")
    target_link_libraries(gt4_vu0_aot_registry_test PRIVATE gt4_vu_fixtures ps2runtime_vulkan $<$<PLATFORM_ID:Windows>:user32>)
    target_compile_options(gt4_vu0_aot_registry_test PRIVATE ${GT4_WARNING_FLAGS} -Wno-unused-label)
endif()
