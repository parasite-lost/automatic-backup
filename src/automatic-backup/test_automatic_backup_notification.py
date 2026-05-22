"""Unittests for 'configure.py'"""

# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=too-many-lines

import subprocess
import threading
import time
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automatic_backup_notification import (
    BackupNotificationServer,
    NotificationHandler,
    NotificationInterface,
)


class TestAutomaticBackupNotification(unittest.TestCase):
    def test_varlinkctl_communication(self):
        with (
            TemporaryDirectory() as tmpdir,
            mock.patch.object(NotificationInterface.notification_handler, "start") as mock_start,
            mock.patch.object(
                NotificationInterface.notification_handler, "running"
            ) as mock_running,
            mock.patch.object(NotificationInterface.notification_handler, "stop") as mock_stop,
        ):
            # Notification.notification_handler = mock.MagicMock()
            socket = f"{tmpdir}/notification.socket"
            server = BackupNotificationServer(socket)
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()

            subprocess.run(
                [
                    "varlinkctl",
                    "call",
                    socket,
                    "local.automatic-backup.Notification.Start",
                    r"{}",
                ],
                stdout=subprocess.PIPE,
                check=False,
            )
            time.sleep(0.1)
            mock_start.assert_called_once()
            mock_start.reset_mock()
            mock_running.assert_not_called()
            mock_stop.assert_not_called()

            subprocess.run(
                [
                    "varlinkctl",
                    "call",
                    socket,
                    "local.automatic-backup.Notification.Running",
                    r"{}",
                ],
                stdout=subprocess.PIPE,
                check=False,
            )
            time.sleep(0.1)
            mock_start.assert_not_called()
            mock_running.assert_called_once()
            mock_running.reset_mock()
            mock_stop.assert_not_called()

            subprocess.run(
                [
                    "varlinkctl",
                    "call",
                    socket,
                    "local.automatic-backup.Notification.Stop",
                    r"{}",
                ],
                stdout=subprocess.PIPE,
                check=False,
            )
            time.sleep(0.1)
            mock_start.assert_not_called()
            mock_running.assert_not_called()
            mock_stop.assert_called_once()
            mock_stop.reset_mock()

            server.shutdown()
            server_thread.join()
            Path(socket).unlink(missing_ok=True)


class TestNotificationHandler(unittest.TestCase):
    def test_start_timeout(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()

            time.sleep(0.15)

            mock_notify_send.assert_has_calls(
                [
                    mock.call("starting", "Backup started", "...", ""),
                    mock.call("stopping", "Backup stopped", "Error: Backup timed out", "42"),
                ]
            )
            mock_logging_info.assert_called_once_with("Backup started: %s", 1)
            mock_logging_warning.assert_called_once_with("Backup timeout. Lost: %s", 1)

            notification.shutdown()

    def test_start_extends_time_until_timeout(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()
            time.sleep(0.05)
            notification.start()
            time.sleep(0.05)
            notification.start()
            time.sleep(0.05)

            mock_notify_send.assert_called_once_with(
                "starting", "Backup started", "...", ""
            )  # not timed out yet
            mock_notify_send.reset_mock()

            time.sleep(0.15)

            mock_notify_send.assert_called_once_with(
                "stopping", "Backup stopped", "Error: Backup timed out", "42"
            )
            mock_logging_info.assert_has_calls(
                [
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup started: %s", 2),
                    mock.call("Backup started: %s", 3),
                ]
            )

            mock_logging_warning.assert_called_once_with("Backup timeout. Lost: %s", 3)

            notification.shutdown()

    def test_start_start_stop_timeout(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()
            notification.start()
            notification.stop()

            time.sleep(0.15)

            mock_notify_send.assert_has_calls(
                [
                    mock.call("starting", "Backup started", "...", ""),
                    mock.call("stopping", "Backup stopped", "Error: Backup timed out", "42"),
                ]
            )
            mock_logging_info.assert_has_calls(
                [
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup started: %s", 2),
                    mock.call("Backup finished. Backups still running: %s", 1),
                ]
            )

            mock_logging_warning.assert_called_once_with("Backup timeout. Lost: %s", 1)

            notification.shutdown()

    def test_start_start_stop_stop_no_timeout(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()
            notification.start()
            notification.stop()
            notification.stop()

            time.sleep(0.15)

            mock_notify_send.assert_has_calls(
                [
                    mock.call("starting", "Backup started", "...", ""),
                    mock.call("stopping", "Backup stopped", "Backup finished successfully", "42"),
                ]
            )
            mock_logging_info.assert_has_calls(
                [
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup started: %s", 2),
                    mock.call("Backup finished. Backups still running: %s", 1),
                    mock.call("Backup finished. Backups still running: %s", 0),
                ]
            )

            mock_logging_warning.assert_not_called()

            notification.shutdown()

    def test_running_extends_timer_no_timeout(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()
            notification.start()
            time.sleep(0.05)
            notification.running()
            time.sleep(0.05)
            notification.running()
            time.sleep(0.05)
            notification.running()
            time.sleep(0.05)
            notification.running()
            notification.stop()
            notification.stop()

            time.sleep(0.15)

            mock_notify_send.assert_has_calls(
                [
                    mock.call("starting", "Backup started", "...", ""),
                    mock.call("stopping", "Backup stopped", "Backup finished successfully", "42"),
                ]
            )
            mock_logging_info.assert_has_calls(
                [
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup started: %s", 2),
                    mock.call("Backup finished. Backups still running: %s", 1),
                    mock.call("Backup finished. Backups still running: %s", 0),
                ]
            )

            mock_logging_warning.assert_not_called()

            notification.shutdown()

    def test_continuous_notification(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=10, notification_interval=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()
            notification.start()
            time.sleep(0.35)  # time for three continuous notifications
            notification.stop()
            notification.stop()

            time.sleep(0.1)

            mock_notify_send.assert_has_calls(
                [
                    mock.call("starting", "Backup started", "...", ""),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("stopping", "Backup stopped", "Backup finished successfully", "42"),
                ]
            )
            mock_logging_info.assert_has_calls(
                [
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup started: %s", 2),
                    mock.call("Backup finished. Backups still running: %s", 1),
                    mock.call("Backup finished. Backups still running: %s", 0),
                ]
            )

            mock_logging_warning.assert_not_called()

            notification.shutdown()

    def test_repeated_phases_of_continuous_notification(self):
        with (
            mock.patch("automatic_backup_notification.notify_send") as mock_notify_send,
            mock.patch("logging.info") as mock_logging_info,
            mock.patch("logging.warning") as mock_logging_warning,
        ):
            notification = NotificationHandler(timeout=10, notification_interval=0.1)
            self.addCleanup(notification.shutdown)
            mock_notify_send.return_value = "42"

            notification.start()
            time.sleep(0.35)  # time for three continuous notifications
            notification.stop()

            time.sleep(0.1)

            notification.start()
            time.sleep(0.25)  # time for two continuous notifications
            notification.stop()

            time.sleep(0.1)

            mock_notify_send.assert_has_calls(
                [
                    mock.call("starting", "Backup started", "...", ""),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("stopping", "Backup stopped", "Backup finished successfully", "42"),
                    mock.call("starting", "Backup started", "...", "42"),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("running", "Backup running", "...", "42"),
                    mock.call("stopping", "Backup stopped", "Backup finished successfully", "42"),
                ]
            )
            mock_logging_info.assert_has_calls(
                [
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup finished. Backups still running: %s", 0),
                    mock.call("Backup started: %s", 1),
                    mock.call("Backup finished. Backups still running: %s", 0),
                ]
            )

            mock_logging_warning.assert_not_called()

            notification.shutdown()


if __name__ == "__main__":
    unittest.main()
