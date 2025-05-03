"""unittests for automatic_backup"""

# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=too-many-lines

import threading
import time
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from unittest import mock

from automatic_backup import (
    BackgroundNotificationClient,
    BackgroundNotifier,
    BackupNotificationVarlinkClient,
    BackupRunnerBorgmatic,
    get_notification_socket,
)
from automatic_backup_notification import (
    BackupNotificationServer,
    NotificationInterface,
    NotificationHandler,
)


class TestAutomaticBackupMethods(unittest.TestCase):
    def test_run_backup(self):
        with (mock.patch("subprocess.run") as mock_subprocess_run,):
            mock_notifier = mock.MagicMock(spec=BackgroundNotifier)
            backup_runner = BackupRunnerBorgmatic(
                notifier=mock_notifier,
                config=Path("/what/ever"),
                target_path=Path("/some/where"),
                target_uuid="1234",
            )

            backup_runner.run_backup()

            mock_notifier.start.assert_called_once()
            create_repo_command = [
                "borgmatic",
                "repo-create",
                "--config",
                "/what/ever",
            ]
            # pylint: disable=duplicate-code
            create_backup_command = [
                "borgmatic",
                "--verbosity",
                "-2",
                "--syslog-verbosity",
                "1",
                "--config",
                "/what/ever",
            ]
            mock_subprocess_run.assert_has_calls(
                [
                    mock.call(
                        create_repo_command,
                        check=True,
                    ),
                    mock.call(
                        create_backup_command,
                        check=True,
                    ),
                ]
            )
            mock_notifier.stop.assert_called_once()

    def test_nonexistent_path_fail(self):
        mock_notifier = mock.MagicMock(spec=BackgroundNotifier)
        backup_runner = BackupRunnerBorgmatic(
            notifier=mock_notifier,
            config=Path("/what/ever"),
            target_path=Path("/some/where"),
            target_uuid="1234",
        )
        with (
            mock.patch("logging.error"),
            mock.patch("logging.info"),
        ):
            self.assertFalse(backup_runner.check_backup_target())

    def test_no_uuid_success(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("logging.info"),
        ):
            mock_notifier = mock.MagicMock(spec=BackgroundNotifier)
            backup_runner = BackupRunnerBorgmatic(
                notifier=mock_notifier,
                config=Path("/what/ever"),
                target_path=Path(tmp_dir),
                target_uuid="",
            )
            self.assertTrue(backup_runner.check_backup_target())

    def test_wrong_uuid_fail(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.check_output", return_value="1234"),
            mock.patch("logging.error"),
            mock.patch("logging.info"),
        ):
            mock_notifier = mock.MagicMock(spec=BackgroundNotifier)
            backup_runner = BackupRunnerBorgmatic(
                notifier=mock_notifier,
                config=Path("/what/ever"),
                target_path=Path(tmp_dir),
                target_uuid="4321",
            )
            self.assertFalse(backup_runner.check_backup_target())

    def test_failed_uuid_fail(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("logging.error"),
            mock.patch("logging.info"),
        ):
            mock_notifier = mock.MagicMock(spec=BackgroundNotifier)
            backup_runner = BackupRunnerBorgmatic(
                notifier=mock_notifier,
                config=Path("/what/ever"),
                target_path=Path(tmp_dir),
                target_uuid="1234",
            )
            self.assertFalse(backup_runner.check_backup_target())

    def test_correct_uuid_success(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.check_output", return_value="1234"),
        ):
            mock_notifier = mock.MagicMock(spec=BackgroundNotifier)
            backup_runner = BackupRunnerBorgmatic(
                notifier=mock_notifier,
                config=Path("/what/ever"),
                target_path=Path(tmp_dir),
                target_uuid="1234",
            )
            self.assertTrue(backup_runner.check_backup_target())

    def test_user_socket_path(self):
        self.assertEqual(
            get_notification_socket("abcdef"),
            "/tmp/automatic-backup-abcdef/local.automatic-backup.Notification",
        )


class TestBackupNotificationClient(unittest.TestCase):
    def test_varlink_communication(self):
        with (TemporaryDirectory() as tmpdir,):
            mock_notification_handler = mock.MagicMock(spec=NotificationHandler)
            NotificationInterface.notification_handler = mock_notification_handler

            socket = f"{tmpdir}/notification.socket"
            server = BackupNotificationServer(socket)
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()

            connection = BackupNotificationVarlinkClient(socket)

            connection.connect()

            connection.Start()
            time.sleep(0.1)
            mock_notification_handler.start.assert_called_once()
            mock_notification_handler.start.reset_mock()
            mock_notification_handler.running.assert_not_called()
            mock_notification_handler.stop.assert_not_called()

            connection.Running()
            time.sleep(0.1)
            mock_notification_handler.start.assert_not_called()
            mock_notification_handler.running.assert_called_once()
            mock_notification_handler.running.reset_mock()
            mock_notification_handler.stop.assert_not_called()

            connection.Stop()
            time.sleep(0.1)
            mock_notification_handler.start.assert_not_called()
            mock_notification_handler.running.assert_not_called()
            mock_notification_handler.stop.assert_called_once()
            mock_notification_handler.stop.reset_mock()

            connection.disconnect()

            server.shutdown()
            server_thread.join()
            Path(socket).unlink(missing_ok=True)


class TestBackupNotifier(unittest.TestCase):
    def test_notify_thread(self):

        mock_notification_client = mock.MagicMock(spec=BackgroundNotificationClient)
        notifier = BackgroundNotifier(
            notification_client=mock_notification_client, notification_interval=0.1
        )

        notifier.start()
        sleep(0.25)  # long enough for 2 Running notifications ()
        notifier.stop()

        mock_notification_client.connect.assert_called_once()
        mock_notification_client.Start.assert_called_once()
        mock_notification_client.Running.assert_has_calls([mock.call(), mock.call()])
        mock_notification_client.Stop.assert_called_once()
        mock_notification_client.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
