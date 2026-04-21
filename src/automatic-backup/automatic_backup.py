#!/usr/bin/env python3

"""Run backup with borgmatic. Optionally notify a given user about progress."""

import abc
import logging
import subprocess
import sys
import threading

from dataclasses import dataclass
from pathlib import Path
from typing import override

import varlink


logging.basicConfig(stream=sys.stderr, format="%(levelname)s - %(message)s", level=logging.INFO)


def get_notification_socket(user: str) -> str:
    """get varlink socket"""
    address = f"/tmp/automatic-backup-{user}/local.automatic-backup.Notification"
    return address


class BackgroundNotificationClient:
    """Interface for backgound notifications"""

    @abc.abstractmethod
    def connect(self):
        """connect to notification system"""

    @abc.abstractmethod
    def Start(self):  # pylint: disable=invalid-name
        """emit 'Start' notification"""

    @abc.abstractmethod
    def Running(self):  # pylint: disable=invalid-name
        """emit 'Running' notification"""

    @abc.abstractmethod
    def Stop(self):  # pylint: disable=invalid-name
        """emit 'Stop' notification"""

    @abc.abstractmethod
    def disconnect(self):
        """disconnect from notification system"""


class BackupNotificationVarlinkClient(BackgroundNotificationClient):
    """Client for backup notifications via varlink notification service."""

    def __init__(self, address: str):
        """Create backup notification client for varlink notification service.

        Args:
            address (str): varlink unix socket address
        """
        self.address = address
        self.__connection = None

    @override
    def connect(self):
        if not Path(self.address).is_socket():
            self.__connection = None
            return
        client = varlink.Client(f"unix:{self.address}")
        self.__connection = client.open("local.automatic-backup.Notification")

    @override
    def Start(self):  # pylint: disable=invalid-name
        if self.__connection:
            self.__connection.Start()  # pylint: disable=no-member

    @override
    def Running(self):  # pylint: disable=invalid-name
        if self.__connection:
            self.__connection.Running()  # pylint: disable=no-member

    @override
    def Stop(self):  # pylint: disable=invalid-name
        if self.__connection:
            self.__connection.Stop()  # pylint: disable=no-member

    @override
    def disconnect(self):
        if self.__connection:
            self.__connection.close()


class BackgroundNotifier:
    """Continuously notify user about backup being in progress using backup notification client"""

    def __init__(
        self,
        notification_client: BackgroundNotificationClient,
        notification_interval: int = 3,
    ):
        """Create a notifier

        Args:
            notification_client (BackgroundNotificationInterface): backup notification client
            notification_interval (int, optional): interval in seconds to emit notifications.
                                                   Defaults to 3.
        """
        self.__thread = threading.Thread(target=self.__notify)
        self.__stop = threading.Event()
        self.__notification_client = notification_client
        self.__notification_interval = notification_interval

    def start(self):
        """start notifying"""
        self.__thread.start()

    def __notify(self):
        self.__notification_client.connect()
        self.__notification_client.Start()
        while not self.__stop.wait(timeout=self.__notification_interval):
            self.__notification_client.Running()
        self.__notification_client.Stop()
        self.__notification_client.disconnect()

    def stop(self):
        """stop notifying"""
        self.__stop.set()
        self.__thread.join()


class BackupRunnerBorgmatic:
    """This class handles checking readiness for backup and performing backup with borgmatic"""

    def __init__(
        self, notifier: BackgroundNotifier, config: Path, target_path: Path, target_uuid: str = ""
    ):
        """Create a backup runner

        Args:
            notifier (BackgroundNotifier): handler for continuous progress notifications
            config (Path): path to borgmatic config yaml
            backup_path (Path): path to backup target
            target_uuid (str, optional): backup target filesystem UUID (will be checked).
                                         Defaults to "" (not checked).
        """
        self.__config = config
        self.__notifier = notifier
        self.__target_path = target_path
        self.__uuid = target_uuid

    def check_backup_target(self) -> bool:
        """Perform pre-check before running backup.

        Returns:
            bool: whether backup target is ready for backup.
        """
        if not self.__target_path.is_dir():
            logging.error("Backup target does not exist: '%s'", self.__target_path)
            return False
        if not self.__uuid:
            logging.info("No UUID provided. Ignoring.")
            return True
        try:
            actual_uuid = subprocess.check_output(
                [
                    "findmnt",
                    "--nofsroot",
                    "--raw",
                    "--noheadings",
                    "--output",
                    "UUID",
                    "--target",
                    self.__target_path,
                ],
                text=True,
            )
            if actual_uuid.strip() != self.__uuid:
                logging.error("UUID mismatch. Actual: %s, expected: %s.", actual_uuid, self.__uuid)
                return False
            return True
        except subprocess.CalledProcessError:
            logging.error("Cannot determine UUID for '%s'", self.__target_path)
            return False

    def run_backup(self):
        """Run a backup

        Args:
            dry_run (bool, optional): whether to perform a dry-run. Defaults to False.
        """
        self.__notifier.start()
        try:
            repo_create_command = [
                "borgmatic",
                "repo-create",
                "--config",
                str(self.__config),
            ]
            subprocess.run(repo_create_command, check=True)
        except subprocess.CalledProcessError:
            logging.error("Failed to create repo")

        borgmatic_command = [
            "borgmatic",
            "--verbosity",
            "-2",
            "--syslog-verbosity",
            "1",
            "--config",
            str(self.__config),
        ]
        try:
            subprocess.run(borgmatic_command, check=True)
        except subprocess.CalledProcessError:
            logging.error("Failed to run borgmatic.")
        self.__notifier.stop()


@dataclass(kw_only=True)
class Arguments:
    """CLI argument type annotation helper"""

    config: Path  # path to borgmatic config yaml
    path: Path  # path to backup
    uuid: str  # UUID of backup target mount
    notify: str | None  # user to notify


def main(arguments: Arguments):
    """Run backup, notify user about progress"""
    notification_socket = get_notification_socket(arguments.notify)
    notification_client = BackupNotificationVarlinkClient(notification_socket)
    notifier = BackgroundNotifier(notification_client)
    backup_runner = BackupRunnerBorgmatic(
        notifier=notifier,
        config=arguments.config,
        target_path=arguments.path,
        target_uuid=arguments.uuid,
    )
    if backup_runner.check_backup_target():
        backup_runner.run_backup()


if __name__ == "__main__":
    from argparse import ArgumentParser

    def parse_args() -> Arguments:
        """parse CLI arguments"""
        parser = ArgumentParser("automatic backup with borgmatic")
        parser.add_argument(
            "--config", required=True, type=Path, help="Path to borgmatic configuration"
        )
        parser.add_argument("--path", required=True, type=Path, help="Path to backup target folder")
        parser.add_argument(
            "--uuid", required=False, default="", type=str, help="UUID of backup target mount"
        )
        parser.add_argument(
            "--notify",
            required=False,
            default="",
            type=str,
            help="User to notify about backup progress",
        )
        args, _ = parser.parse_known_args()
        return Arguments(**vars(args))

    parsed_arguments = parse_args()
    main(parsed_arguments)
