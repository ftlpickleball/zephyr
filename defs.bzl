# Forwarding alias for backwards compatibility
load(
    "//bazel:defs.bzl",
    _device_api_linker_files = "device_api_linker_files",
    _driver_validation_file = "driver_validation_file",
    _dts_cc_library = "dts_cc_library",
    _dts_library = "dts_library",
    _gen_kobject_placeholders = "gen_kobject_placeholders",
    _kobj_types_enum_file = "kobj_types_enum_file",
    _syscall_library_files = "syscall_library_files",
    _userspace_gperf_hash_files = "userspace_gperf_hash_files",
    _zephyr_offset_header = "zephyr_offset_header",
)

device_api_linker_files = _device_api_linker_files
driver_validation_file = _driver_validation_file
dts_cc_library = _dts_cc_library
dts_library = _dts_library
gen_kobject_placeholders = _gen_kobject_placeholders
kobj_types_enum_file = _kobj_types_enum_file
syscall_library_files = _syscall_library_files
userspace_gperf_hash_files = _userspace_gperf_hash_files
zephyr_offset_header = _zephyr_offset_header
