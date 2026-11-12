#!/usr/bin/env python3
"""Explicit test membership: missing tests or empty discovery must fail the gate."""
import unittest

NAMES = [
    "test_fw_split.FirmwareSplit.test_prefix",
    "test_fw_split.FirmwareSplit.test_every_later_byte_survives",
    "test_fw_split.FirmwareSplit.test_first_occurrence",
    "test_fw_split.FirmwareSplit.test_no_partial_marker",
    "test_fw_split.FirmwareSplit.test_comparison_rejects_changed_suffix",
    "test_tools.Tools.test_esp_alias_refusal",
    "test_tools.Tools.test_esp_failure_preserves_image",
    "test_tools.Tools.test_esp_symlink_sizes",
    "test_tools.Tools.test_feeder_success",
    "test_tools.Tools.test_feeder_missing_marker",
    "test_tools.Tools.test_feeder_closed_stdin",
    "test_tools.Tools.test_feeder_cancellation",
    "test_tools.Tools.test_supervisor_cancellation",
    "test_tools.Tools.test_ovmf_environment_isolation",
    "test_tools.Tools.test_home_keys_only_remove_final_wait",
    "test_tools.Tools.test_home_driver_failure_blocks_second_boot",
    "test_pool.Pool.test_existing_zero_display",
    "test_pool.Pool.test_reported_display",
    "test_pool.Pool.test_unreported_or_leaked_frames",
    "test_pool.Pool.test_malformed_anywhere",
    "test_pool.Pool.test_duplicate_or_incomplete",
    "test_pool.Pool.test_stable_hybrid_readiness",
    "test_usbms_frames.UsbmsFrames.test_every_transfer_names_a_driver_frame",
    "test_usbms_frames.UsbmsFrames.test_no_frame_is_released",
    "test_usbms_frames.UsbmsFrames.test_the_frames_are_taken_once",
]
suite = unittest.defaultTestLoader.loadTestsFromNames(NAMES)
assert suite.countTestCases() == len(NAMES) and NAMES
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
