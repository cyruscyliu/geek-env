#!/usr/bin/env python3

import unittest

from scripts.agentctl import InvalidTransitionError, transition_public_state


class UserStoryGraphTest(unittest.TestCase):
    def test_config_edges(self) -> None:
        self.assertEqual(transition_public_state("none", "config"), "saved")
        self.assertEqual(transition_public_state("saved", "config"), "saved")
        self.assertEqual(transition_public_state("ready", "config"), "saved")
        self.assertEqual(transition_public_state("failed", "config"), "saved")

    def test_apply_edges(self) -> None:
        self.assertEqual(transition_public_state("saved", "apply"), "starting")
        self.assertEqual(transition_public_state("ready", "apply"), "starting")
        self.assertEqual(transition_public_state("failed", "apply"), "starting")

    def test_system_edges(self) -> None:
        self.assertEqual(transition_public_state("starting", event="pod_ready"), "ready")
        self.assertEqual(transition_public_state("starting", event="failure"), "failed")

    def test_exec_edge(self) -> None:
        self.assertEqual(transition_public_state("ready", "exec"), "ready")

    def test_status_edges(self) -> None:
        self.assertEqual(transition_public_state("none", "status"), "none")
        self.assertEqual(transition_public_state("saved", "status"), "saved")
        self.assertEqual(transition_public_state("starting", "status"), "starting")
        self.assertEqual(transition_public_state("ready", "status"), "ready")
        self.assertEqual(transition_public_state("failed", "status"), "failed")

    def test_delete_edges(self) -> None:
        self.assertEqual(transition_public_state("saved", "delete"), "none")
        self.assertEqual(transition_public_state("starting", "delete"), "none")
        self.assertEqual(transition_public_state("ready", "delete"), "none")
        self.assertEqual(transition_public_state("failed", "delete"), "none")

    def test_rejects_invalid_user_edges(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("none", "apply")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("saved", "exec")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("starting", "exec")

    def test_rejects_invalid_system_edges(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("ready", event="pod_ready")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("failed", event="failure")

    def test_requires_exactly_one_transition_input(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("saved")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("starting", "status", event="failure")


if __name__ == "__main__":
    unittest.main()
