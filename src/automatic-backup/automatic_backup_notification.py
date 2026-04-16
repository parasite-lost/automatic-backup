#!/usr/bin/env python3

"""varlink-based backup notification service"""

# pylint: disable=invalid-name

import enum
import logging
import subprocess
import sys
import threading
import queue

from pathlib import Path
from typing import Callable

import varlink


logging.basicConfig(stream=sys.stderr, format="%(levelname)s - %(message)s", level=logging.INFO)


class RestartableTimer:
    """Timer that can be restarted"""

    def __init__(self, interval: float, callback: Callable):
        self.__interval = interval
        self.__callback = callback
        self.__timer = threading.Timer(self.__interval, self.__callback)

    def reset(self):
        """reset timer"""
        self.cancel()
        self.start()

    def start(self):
        """start timer"""
        self.__timer = threading.Timer(self.__interval, self.__callback)
        self.__timer.start()

    def cancel(self):
        """cancel timer"""
        self.__timer.cancel()


class Status(enum.Enum):
    """notification status"""

    Start = 0
    Running = 1
    Stop = 2


def notify_send(title: str, message: str, notfication_id: str = "") -> str:
    """Show desktop notification with 'notify-send' utility

    Args:
        title (str): title of the notification
        message (str): body of the notification
        notification_id (str, optional): id of notification to replace, or "" (default)

    Returns:
        str: id of the notification
    """
    command = ["notify-send", "-p"]
    if notfication_id:
        command += ["-r", notfication_id]
    command += ["-a", title, message]
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class NotificationHandler:
    """Notification handler with timeout"""

    def __init__(self, timeout: int = 10):
        self.__notification_id = ""
        self.__timer = RestartableTimer(timeout, self.__timed_out)
        self.__count = 0
        self.__queue = queue.Queue()
        self.__thread = threading.Thread(target=self.__process_queue)
        self.__thread.daemon = True
        self.__thread.start()

    def __timed_out(self):
        self.__notify_send("Backup timeout")
        logging.warning("Backup timeout. Lost: %s", self.__count)
        self.__count = 0

    def __notify_send(self, message):
        self.__notification_id = notify_send("Backup", message, self.__notification_id)

    def __start_backup(self):
        if self.__count == 0:
            self.__notify_send("Backup started")
        self.__count += 1
        logging.info("Backup started: %s", self.__count)
        self.__timer.reset()

    def __continue_backup(self):
        if self.__count > 0:
            self.__notify_send("Backup running")
            logging.debug("Backup running: %s", self.__count)
            self.__timer.reset()
        else:
            logging.error("'Runnung' but no backup started.")

    def __stop_backup(self):
        if self.__count <= 0:
            logging.error("'Stop' but no backup started.")
            return
        self.__count = max(0, self.__count - 1)
        if self.__count == 0:
            self.__notify_send("Backup finished")
            self.__timer.cancel()
        logging.info("Backup finished. Backups still running: %s", self.__count)

    def __process_status(self, status: Status):
        match status:
            case Status.Start:
                self.__start_backup()
            case Status.Running:
                self.__continue_backup()
            case Status.Stop:
                self.__stop_backup()
            case _:
                logging.error("'%s': unknown status", status)

    def __process_queue(self):
        while True:
            try:
                status = self.__queue.get()
                self.__process_status(status)
                self.__queue.task_done()
            except queue.ShutDown:
                break

    def __enqueue(self, status: Status):
        try:
            self.__queue.put(status)
        except queue.ShutDown:
            pass

    def start(self):
        """Start: notify about backup starting (if none started yet)"""
        self.__enqueue(Status.Start)

    def running(self):
        """Running: notify about backup running"""
        self.__enqueue(Status.Running)

    def stop(self):
        """Stop: notify about backup finished (if no other is still backups running)"""
        self.__enqueue(Status.Stop)

    def shutdown(self):
        """shutdown notification processing"""
        self.__timer.cancel()
        self.__queue.shutdown(immediate=True)
        self.__thread.join()


service = varlink.Service(
    vendor="parasite-lost",
    product="Automatic Backup Notification Service",
    version="@VERSION@",
    url="",
    interface_dir=Path(__file__).parent / "varlink",
)


class NotificationRequestHandler(varlink.RequestHandler):
    """Notification request handler"""

    service = service


@service.interface("local.automatic-backup.Notification")
class NotificationInterface:
    """Notification interface"""

    notification_handler = NotificationHandler()

    def Start(self) -> None:
        """Start notification"""
        self.notification_handler.start()

    def Running(self) -> None:
        """Running notification"""
        self.notification_handler.running()

    def Stop(self) -> None:
        """Stop notification"""
        self.notification_handler.stop()


class BackupNotificationServer:
    """varlink server for backup notifications"""

    def __init__(self, address: str = ""):
        if address != "" and not address.startswith("unix:"):
            address = f"unix:{address}"
        self.__server = varlink.ThreadingServer(address, NotificationRequestHandler)

    def run(self):
        """run the server"""
        self.__server.serve_forever()
        self.__stop()

    def shutdown(self):
        """shutdown server"""
        self.__server.shutdown()
        self.__stop()

    def __stop(self):
        NotificationInterface.notification_handler.shutdown()
        self.__server.server_close()


if __name__ == "__main__":
    import argparse
    import dataclasses

    @dataclasses.dataclass(kw_only=True)
    class Arguments:
        """CLI argument type annotation helper"""

        address: str

    def parse_arguments() -> Arguments:
        """parse CLI arguments"""
        parser = argparse.ArgumentParser("Backup notification service (varlink)")
        parser.add_argument(
            "address",
            metavar="ADDRESS",
            nargs="?",
            type=str,
            default="",
            help="address to listen on",
        )
        args, _ = parser.parse_known_args()
        return Arguments(**vars(args))

    arguments = parse_arguments()
    server = BackupNotificationServer(arguments.address)
    server.run()
