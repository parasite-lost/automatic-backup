#!/usr/bin/env python3

"""Configure multi-user automatic backup service"""

# pylint: disable=too-many-lines

import abc
import argparse
import json
import os
import pwd
import stat
import subprocess
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, override


__VERSION = "@VERSION@"


@dataclass
class _Settings:
    """Internal module settings"""

    dry_run: bool = False


_settings = _Settings()


def set_dry_run(enabled: bool):
    """Activate dry-run, such that no actual changes to the system are performed
    but only listed what would be done."""
    if enabled:
        print("Performing dry-run.")
    _settings.dry_run = enabled


def dry_run() -> bool:
    """Check whether dry-run setting is active."""
    return _settings.dry_run


def ask_user_confirmation(question: str) -> bool:
    """Ask user for confirmation (Yes/No-question)

    Args:
        question (str): question prompted

    Returns:
        bool: True if user answers with Yes, False if user answers with No.
    """
    if _settings.dry_run:
        return True
    while True:
        answer = input(f"> {question} [Yes/No]")
        if answer.upper() in ("Y", "YES"):
            return True
        if answer.upper() in ("N", "NO"):
            return False


def _os_error(exception: Exception) -> NoReturn:
    print(f"Error: {exception}", file=sys.stderr)
    sys.exit(os.EX_OSERR)


def i_am_root() -> bool:
    """Check if running with root privileges.

    Returns:
        bool: True if running as root, otherwise False.
    """
    return os.getuid() == 0


def write_file(path: Path, content: str, uid: int = os.getuid(), gid: int = os.getgid()) -> None:
    """Write a file with given content. Optional set ownership.

    Args:
        path (Path):         file path to write to.
        content (str):       content of the file to write.
        uid (int, optional): uid of the file. Defaults to os.getuid().
        gid (int, optional): gid of the file to write. Defaults to os.getgid().

    Raises:
        RuntimeError: if containing folder does not exists
    """
    print(f"Creating file{f' ({uid}:{gid})' if i_am_root() else ''}: {path}")
    if _settings.dry_run:
        return
    if not path.parent.exists():
        raise RuntimeError("Parent folder does not exist")
    with path.open("w", encoding="utf-8") as path_f:
        path_f.write(content)
    if i_am_root():
        os.chown(path=path, uid=uid, gid=gid)


def create_dir(path: Path, uid: int = os.getuid(), gid: int = os.getgid(), root_mode: int = None):
    """Create a directory. Optionally set ownership.

    Args:
        path (Path): directory path
        uid (int, optional): uid of directory. Defaults to os.getuid().
        gid (int, optional): gid of directory. Defaults to os.getgid().
        root_mode (int, optional): octal permission mode if run with elevated
                                   privileges. Defaults to None (not explicitly
                                   applied).
    """
    if not path.parent.exists():
        create_dir(path=path.parent, uid=uid, gid=gid)
    print(f"Creating directory{f' ({uid}:{gid})' if i_am_root() else ''}: {path}")
    if _settings.dry_run:
        return
    path.mkdir(parents=False, exist_ok=True)
    if i_am_root():
        os.chown(path=path, uid=uid, gid=gid)
        if root_mode is not None:
            os.chmod(path=path, mode=root_mode)


def current_username() -> str:
    """Get current user's username.

    Returns:
        str: current user's username
    """
    return pwd.getpwuid(os.getuid()).pw_name


def switch_user_command(user: str, command: list[str]) -> list[str]:
    """Generate command to run command as a different user.

    Args:
        user (str):          switch to this user to run command
        command (list[str]): command to run as a different user

    Returns:
        list[str]: command that (when run) will execute the original command as
                   a different user
    """
    return ["run0", "-u", user] + command


def systemd_ask_password() -> str:
    """Secure password entry prompt

    Returns:
        str: password
    """
    try:
        return subprocess.check_output(
            ["systemd-ask-password", "-n"],
            text=True,
        )
    except subprocess.CalledProcessError as e:
        _os_error(e)


def systemd_escape(path: str) -> str:
    """systemd-escape --path

    Args:
        path (str): path to escape

    Returns:
        str: escaped path
    """
    return subprocess.check_output(
        [
            "systemd-escape",
            "--path",
            path,
        ],
        text=True,
    ).strip()


class _Scope(metaclass=abc.ABCMeta):
    """
    General systemd scope interface
    """

    @abc.abstractmethod
    def systemd_command(self, command: list[str]) -> list[str]:
        """systemd command adjusted for system/user scope"""

    @abc.abstractmethod
    def user(self) -> str:
        """user"""

    @abc.abstractmethod
    def scope(self) -> str:
        """scope"""

    @abc.abstractmethod
    def _uid(self) -> int:
        """uid"""

    @abc.abstractmethod
    def _gid(self) -> int:
        """gid"""

    @abc.abstractmethod
    def __str__(self) -> str:
        """string representation"""

    @abc.abstractmethod
    def is_system_scope(self) -> bool:
        """is system scope"""

    @abc.abstractmethod
    def home(self) -> Path:
        """home directory"""

    @abc.abstractmethod
    def _config_base_dir(self) -> Path:
        """base directory for application configuration"""

    @abc.abstractmethod
    def _service_base_dir(self) -> Path:
        """base directory for service units"""

    def __create_dir(self, path: Path) -> None:
        create_dir(path=path, uid=self._uid(), gid=self._gid())

    def __write_file(self, path: Path, content: str) -> None:
        write_file(path=path, content=content, uid=self._uid(), gid=self._gid())

    def config_path(self, service: str, name: str) -> Path:
        """get path to config file for given service (or application) and config file name

        Args:
            service (str): this service's (or application's) config
            name (str): name of the config file

        Returns:
            Path: path to config file
        """
        return self._config_base_dir() / service / name

    def is_config_installed(self, service: str, name: str) -> bool:
        """check if config for given service (or application) is installed

        Args:
            service (str): this service's (or application's) config
            name (str): name of the config file

        Returns:
            bool: whether config file is present
        """
        return self.config_path(service=service, name=name).is_file()

    def install_config(self, service: str, name: str, content: str) -> None:
        """install config for given service (or application)

        Args:
            service (str): this service's (or application's) config
            name (str): name of the config file
            content (str): content of the config file
        """
        config = self.config_path(service, name)
        self.__create_dir(config.parent)
        self.__write_file(config, content)

    @staticmethod
    def __service_name(name: str) -> str:
        required_extension = ".service"
        if not name.endswith(required_extension):
            return name + required_extension
        return name

    def service_path(self, name: str) -> Path:
        """get path to systemd service unit file

        Args:
            name (str): service name

        Returns:
            Path: path to systemd service unit file
        """
        return self._service_base_dir() / self.__service_name(name)

    def is_service_installed(self, name: str) -> bool:
        """check if systemd service unit file is installed

        Args:
            name (str): service name

        Returns:
            bool: whether the systemd service unit file is present
        """
        return self.service_path(name).is_file()

    def install_service(self, name: str, content: str) -> None:
        """install systemd service unit file

        Args:
            name (str): service name
            content (str): systemd service unit file content
        """
        service_file = self.service_path(name)
        self.__create_dir(service_file.parent)
        self.__write_file(service_file, content)

    def enable_service(self, name: str) -> None:
        """enable systemd service

        Args:
            name (str): service name
        """
        service = self.__service_name(name)
        command = self.systemd_command(["systemctl", "enable", service])
        print(f"Enabling service '{service}' for user '{self.user()}'")
        if _settings.dry_run:
            return
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            pass

    @staticmethod
    def __dropin_name(name: str) -> str:
        canonical_file_extension = ".conf"
        if not name.endswith(canonical_file_extension):
            return name + canonical_file_extension
        return name

    def service_dropin_path(self, service: str, name: str) -> Path:
        """get path to dropin file for systemd service

        Args:
            service (str): systemd service name
            name (str): dropin file name

        Returns:
            Path: path to dropin file for systemd service
        """
        service_dropin_dir = self._service_base_dir() / f"{self.__service_name(service)}.d"
        service_dropin = service_dropin_dir / self.__dropin_name(name)
        return service_dropin

    def is_service_dropin_installed(self, service: str, name: str) -> bool:
        """check if dropin file for systemd service is installed

        Args:
            service (str): systemd service name
            name (str): dropin file name

        Returns:
            bool: whether dropin file for systemd service is present
        """
        return self.service_dropin_path(service, name).is_file()

    def install_service_dropin(self, service: str, name: str, content: str) -> None:
        """install dropin file for systemd service

        Args:
            service (str): systemd service name
            name (str): dropin file name
            content (str): content of dropin file for systemd service
        """
        service_dropin = self.service_dropin_path(service, name)
        self.__create_dir(service_dropin.parent)
        self.__write_file(service_dropin, content)


def prompt_password(purpose: str) -> str | None:
    """prompt for password for given purpose

    Args:
        purpose (str): purpose for password

    Returns:
        str | None: confirmed password or None
    """
    print(f"Enter password for {purpose}:")
    if _settings.dry_run:
        ask_password = "NO_PASSWD"
    else:
        ask_password = systemd_ask_password()
    print(f"Repeat password for {purpose}:")
    if _settings.dry_run:
        ask_password_again = "NO_PASSWD"
    else:
        ask_password_again = systemd_ask_password()

    if ask_password == ask_password_again:
        return ask_password
    print("Passwords did not match!", file=sys.stderr)
    return None


class SystemScope(_Scope):
    """Systemd system scope"""

    @override
    def systemd_command(self, command):
        return command

    @override
    def user(self) -> str:
        return "root"

    @override
    def scope(self) -> str:
        return "system"

    @override
    def _uid(self) -> int:
        return 0

    @override
    def _gid(self) -> int:
        return 0

    @override
    def __str__(self) -> str:
        return "system"

    @override
    def is_system_scope(self) -> bool:
        return True

    @override
    def home(self) -> Path:
        return Path("/")

    @override
    def _config_base_dir(self) -> Path:
        return Path("/etc")

    @override
    def _service_base_dir(self) -> Path:
        return Path("/etc/systemd/system")


class UserScope(_Scope):
    """systemd user scope"""

    def __init__(self, username: str):
        self.__username = username
        user = pwd.getpwnam(username)
        self.__uid = user.pw_uid
        self.__gid = user.pw_gid
        self.__home_dir = Path(user.pw_dir)

    @override
    def systemd_command(self, command):
        if command[0] not in ("systemctl", "systemd-creds", "systemd-run"):
            print(
                f"'{command[0]}': command currently not supported. Ignoring.",
                file=sys.stderr,
            )
            return command
        if command[1] != "--user":
            command = [command[0], "--user"] + command[1:]
        if self.user() != current_username():
            if i_am_root():
                command = switch_user_command(self.user(), command)
            else:
                raise RuntimeError("Cannot run command for other user without root privileges.")
        return command

    @override
    def user(self) -> str:
        return self.__username

    @override
    def scope(self) -> str:
        return f"user-{self.user()}"

    @override
    def _uid(self) -> int:
        return self.__uid

    @override
    def _gid(self) -> int:
        return self.__gid

    @override
    def __str__(self) -> str:
        return f"user '{self.user()}'"

    @override
    def is_system_scope(self) -> bool:
        return False

    @override
    def home(self) -> Path:
        return self.__home_dir

    @override
    def _config_base_dir(self) -> Path:
        return self.home() / ".config"

    @override
    def _service_base_dir(self) -> Path:
        return self._config_base_dir() / "systemd" / "user"


class SystemdCredential:
    """systemd credential (name, password)"""

    def __init__(self, scope: _Scope, name: str):
        self.__scope = scope
        self.__name = name
        self.__encrypted_pretty = None
        self.__encrypted_plain = None

    def __encrypt_pretty(self, plaintext: str):
        if _settings.dry_run:
            self.__encrypted_pretty = ""
            return
        base_command_pretty = [
            "systemd-creds",
            "encrypt",
            "--pretty",
            f"--name={self.__name}",
            "-",
            "-",
        ]
        command_pretty = self.__scope.systemd_command(base_command_pretty)
        try:
            self.__encrypted_pretty = subprocess.check_output(
                command_pretty, input=plaintext, text=True
            )
        except subprocess.CalledProcessError as e:
            _os_error(e)

    def __encrypt_plain(self, plaintext: str):
        if _settings.dry_run:
            self.__encrypted_plain = ""
            return
        base_command_plain = ["systemd-creds", "encrypt", f"--name={self.__name}", "-", "-"]
        command_plain = self.__scope.systemd_command(base_command_plain)
        try:
            encrypted_plain = subprocess.check_output(command_plain, input=plaintext, text=True)
            # result will contain newlines
            encrypted_plain_oneline = "".join(encrypted_plain.splitlines())
            self.__encrypted_plain = f"SetCredentialEncrypted={self.name}:{encrypted_plain_oneline}"
        except subprocess.CalledProcessError as e:
            _os_error(e)

    @property
    def name(self):
        """name of the credential"""
        return self.__name

    @property
    def encrypted_pretty(self):
        """pretty encoded systemd credential, ready to be inserted into a
        systemd unit. Needs to be set with set_password first."""
        if self.__encrypted_pretty is None:
            raise RuntimeError("No password has been set.")
        return self.__encrypted_pretty

    @property
    def encrypted_plain(self):
        """plain encoded systemd credential, ready to be inserted into a
        systemd unit. Needs to be set with set_password first."""
        if self.__encrypted_plain is None:
            raise RuntimeError("No password has been set.")
        return self.__encrypted_plain

    def set_value(self, value: str):
        """set credential content

        Args:
            value (str): credential value to encrypt
        """
        print(f"Encrypting credentials for {self.__scope}")
        self.__encrypt_pretty(value)
        self.__encrypt_plain(value)


@dataclass(kw_only=True)
class MountData:
    """mount data for an external filesystem"""

    device: Path
    mount_point: Path
    uuid: str
    hotplug: bool


def get_mount_data(path: Path, /, source: bool) -> MountData:
    """find mount information based on source or target path

    Args:
        path (Path): path to query information for
        source (bool): whether path is a source (true) or target (false) path

    Returns:
    """
    if source:
        direction = "--source"
    else:
        direction = "--target"
    try:
        findmnt_data = subprocess.check_output(
            [
                "findmnt",
                "--json",
                "--nofsroot",
                "--output",
                "SOURCE,TARGET,UUID",
                direction,
                f"{path}",
            ],
            text=True,
        )
        parsed_findmnt_json = json.loads(findmnt_data)
        file_system = parsed_findmnt_json["filesystems"][0]
        device = file_system["source"]
        lsblk_data = subprocess.check_output(
            [
                "lsblk",
                "--json",
                "--output",
                "HOTPLUG",
                device,
            ],
            text=True,
        )
        parsed_lsblk_json = json.loads(lsblk_data)
        hotplug_data = parsed_lsblk_json["blockdevices"][0]
        return MountData(
            device=Path(device),
            mount_point=Path(file_system["target"]),
            uuid=file_system["uuid"],
            hotplug=hotplug_data["hotplug"],
        )
    except subprocess.CalledProcessError as e:
        _os_error(e)


class ExternalFileSystem:
    """This class represents an external filesystem"""

    def __init__(self, path: Path):
        self._update_mount_data(path, source=False)

    def _update_mount_data(self, path: Path, source: bool = False):
        self._mount_data = get_mount_data(path, source)
        self._systemd_escaped: str = systemd_escape(self._mount_data.mount_point)
        self._mount_unit: str = f"{self._systemd_escaped}.mount"

    @property
    def device(self) -> Path:
        """source device (node)"""
        return self._mount_data.device

    @property
    def mount_point(self) -> Path:
        """mount point"""
        return self._mount_data.mount_point

    @property
    def uuid(self) -> str:
        """filesystem uuid"""
        return self._mount_data.uuid

    @property
    def systemd_escaped(self) -> str:
        """systemd escaped mount path"""
        return self._systemd_escaped

    @property
    def mount_unit(self) -> str:
        """systemd mount unit"""
        return self._mount_unit

    @property
    def hotpluggable(self) -> bool:
        """whether filesystem is hotpluggable"""
        return self._mount_data.hotplug

    def __str__(self) -> str:
        return (
            "Mount target:\n"
            f"  - Device: {self.device}\n"
            f"  - Mount point: {self.mount_point}\n"
            f"  - UUID: {self.uuid}\n"
            f"  - Mount target: {self.systemd_escaped}\n"
            f"  - Mount unit: {self.mount_unit}\n"
        )


class BackupLocation(ExternalFileSystem):  # pylint: disable=too-many-instance-attributes
    """
    This class represents a backup location.
    """

    def __init__(self, path: Path, repo_suffix: str):
        """backup location

        Args:
            path (Path): path to backup location
            repo_suffix (str): backup repository name suffix
        """
        resolved_path = path.resolve()
        super().__init__(resolved_path)
        self._subfolder: Path = resolved_path.relative_to(self.mount_point, walk_up=False)
        self._repo_suffix: str = repo_suffix

    @property
    def folder(self) -> Path:
        """backup folder (where to place backups)"""
        return self.mount_point / self._subfolder

    @property
    def repo_suffix(self) -> str:
        """borg repository suffix"""
        return self._repo_suffix

    def __str__(self) -> str:
        return (
            "Backup location:\n"
            f"  - Backup path: {self.folder}\n"
            f"  - Repo suffix: {self.repo_suffix}\n"
            f"  - Device: {self.device}\n"
            f"  - UUID: {self.uuid}\n"
            f"  - Mount point: {self.mount_point}\n"
            f"  - Mount target: {self.systemd_escaped}\n"
        )

    def allows_multi_user_access(self):
        """Check if permissions for the location are rwx for others"""
        perms = self.folder.stat().st_mode
        full_access = stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        return perms & full_access == full_access


class _FileTemplate(metaclass=abc.ABCMeta):
    """File template base class"""

    __template_folder = Path(__file__).parent / "templates"
    template_file: str = None

    def __init__(
        self,
        *,
        file_name: str,
    ):
        self._file_name = file_name
        self._substitutions: dict[str, str] = {}

    @abc.abstractmethod
    def _resolve_substitutions(self):
        """resolve subsitutions"""

    def __template_file(self) -> Path:
        return self.__template_folder / self.template_file

    def __content_substitute(self, line: str) -> str:
        for macro, value in self._substitutions.items():
            line = line.replace(macro, value)
        return line

    def __content(self) -> str:
        """Get content from template with data filled in."""
        template_file = self.__template_file()
        file_content = ""
        with template_file.open(mode="r", encoding="utf-8") as t_f:
            for line in t_f:
                file_content += self.__content_substitute(line)
        return file_content

    @abc.abstractmethod
    def file_path(self) -> Path:
        """Target file path"""

    @abc.abstractmethod
    def is_installed(self) -> bool:
        """Check if target file is already installed"""

    def install(self, force=False):
        """Install file (by default do not overwrite existing file).

        Args:
            force (bool, optional): If True overwrite existing file. Defaults to False.
        """
        if not force and self.is_installed():
            print(f"'{self._file_name}' already installed. Skipping.")
            return
        self._resolve_substitutions()
        file_content = self.__content()
        self._do_install(content=file_content)

    @abc.abstractmethod
    def _do_install(self, content: str):
        """install file"""


class _ConfigFileTemplate(_FileTemplate):
    config_dir: str = None

    def __init__(self, scope: _Scope, file_name: str):
        super().__init__(file_name=file_name)
        self._scope = scope

    @override
    @abc.abstractmethod
    def _resolve_substitutions(self):
        pass

    @override
    def file_path(self) -> Path:
        return self._scope.config_path(self.config_dir, self._file_name)

    @override
    def is_installed(self) -> bool:
        return self._scope.is_config_installed(self.config_dir, self._file_name)

    @override
    def _do_install(self, content: str):
        return self._scope.install_config(
            service=self.config_dir, name=self._file_name, content=content
        )


class _AutomaticBackupUdevRule(_ConfigFileTemplate):
    """basic udev rule"""

    template_file = None
    config_dir = "udev/rules.d"

    def __init__(self, file_system: ExternalFileSystem):
        super().__init__(
            scope=SystemScope(),
            file_name=f"65-automatic-backup-{file_system.uuid}.rules",
        )
        self.__device_uuid = file_system.uuid

    @override
    def _resolve_substitutions(self):
        self._substitutions = {"@@DEVICE_UUID@@": self.__device_uuid}


class PrivateUdevRule(_AutomaticBackupUdevRule):
    """Template file for udev rule for automounting a filesystem privately."""

    template_file = "65-private-automount-UUID.rules"


class SharedUdevRule(_AutomaticBackupUdevRule):
    """Template file for udev rule for automounting as filesystem accessible to
    all users."""

    template_file = "65-shared-automount-UUID.rules"


class BackupExcludeUserFile(_ConfigFileTemplate):
    """User backup excludes"""

    template_file = "excludes-user"
    config_dir = "borgmatic"

    def __init__(self, user_scope: UserScope, location: BackupLocation):
        super().__init__(
            scope=user_scope,
            file_name=f"excludes-user-{location.systemd_escaped}",
        )

    @override
    def _resolve_substitutions(self):
        self._substitutions = {
            "@@USER_HOME@@": f"{self._scope.home()}",
        }


class BackupExcludeSystemFile(_ConfigFileTemplate):
    """System backup excludes"""

    template_file = "excludes-system"
    config_dir = "borgmatic"

    def __init__(self, location: BackupLocation):
        super().__init__(
            scope=SystemScope(),
            file_name=f"excludes-system-{location.systemd_escaped}",
        )

    @override
    def _resolve_substitutions(self):
        return


class BackupConfig(_ConfigFileTemplate):
    """Main borgmatic per-user configuration."""

    template_file = "borgmatic-config.yaml"
    config_dir = "borgmatic"

    def __init__(self, scope: _Scope, location: BackupLocation, credential: SystemdCredential):
        if scope.is_system_scope():
            self.exclude = BackupExcludeSystemFile(location)
        else:
            self.exclude = BackupExcludeUserFile(scope, location)
        self.__credential = credential
        self.__location = location
        super().__init__(
            scope=scope,
            file_name=f"borgmatic-config-{location.systemd_escaped}.yaml",
        )

    def _folder(self) -> Path:
        return self.__location.folder

    def _repo(self) -> str:
        return f"{self._scope.scope()}-{self.__location.repo_suffix}"

    def repo_path(self) -> Path:
        """repository path"""
        return self._folder() / self._repo()

    @override
    def _resolve_substitutions(self):
        self._substitutions = {
            "@@BORG_REPO_CREDENTIAL@@": self.__credential.name,
            "@@BACKUP_FOLDER@@": str(self._folder()),
            "@@BACKUP_EXCLUDE_FILE@@": str(self.exclude.file_path()),
            "@@BACKUP_SOURCE_DIR@@": str(self._scope.home()),
            "@@BACKUP_REPO@@": self._repo(),
        }

    @override
    def _do_install(self, content):
        self.exclude.install()
        super()._do_install(content)


# pylint: disable=too-few-public-methods
class BackupScript:
    """main backup script"""

    def __init__(self):
        self.__file = Path(__file__).parent / "automatic_backup.py"

    def file_path(self) -> Path:
        """path to backup script file"""
        return self.__file


class BackupServiceFile(_FileTemplate):
    """Backup service unit file"""

    template_file = "automatic-backup-.service"

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        *,
        scope: _Scope,
        location: BackupLocation,
        config: BackupConfig,
        script: BackupScript,
        notify_user: str = None,
    ):
        super().__init__(
            file_name=f"automatic-backup-{location.systemd_escaped}",
        )
        self.__scope = scope
        self.__location = location
        self.__config = config
        self.__script = script
        self.__notify_user = notify_user

    @override
    def _resolve_substitutions(self):
        # perform escaping for paths to prevent misinterpretations by systemd
        # note: mount unit must not be escaped (it is already correctly encoded
        # for systemd), uuid is safe
        self._substitutions = {
            "@@BACKUP_FOLDER@@": str(self.__location.folder).replace("\\", "\\\\"),
            "@@MOUNT_UNIT@@": self.__location.mount_unit,
            "@@DEVICE_UUID@@": self.__location.uuid,
            "@@SCRIPT_NAME@@": str(self.__script.file_path()).replace("\\", "\\\\"),
            "@@BACKUP_CONFIG_FILE@@": str(self.__config.file_path()).replace("\\", "\\\\"),
        }
        if self.__notify_user:
            self._substitutions["@@NOTIFY_USER@@"] = self.__notify_user

    def name(self):
        """service name"""
        return self._file_name

    @override
    def is_installed(self):
        return self.__scope.is_service_installed(self._file_name)

    @override
    def file_path(self):
        return self.__scope.service_path(self._file_name)

    @override
    def _do_install(self, content):
        return self.__scope.install_service(self._file_name, content)

    def enable(self):
        """Enable the service"""
        self.__scope.enable_service(self._file_name)


class BackupServiceCredentialFile(_FileTemplate):
    """dropin credential file for service"""

    template_file = "credential.conf"

    def __init__(self, scope: _Scope, service: BackupServiceFile, credential: SystemdCredential):
        self.__scope = scope
        self.__service = service.name()
        self.__credential = credential
        super().__init__(
            file_name="credential.conf",
        )

    def _resolve_substitutions(self):
        self._substitutions = {
            "@@BORG_REPO_CREDENTIAL@@": self.__credential.encrypted_pretty,
        }

    @override
    def is_installed(self):
        return self.__scope.is_service_dropin_installed(self.__service, self._file_name)

    @override
    def file_path(self):
        return self.__scope.service_dropin_path(self.__service, self._file_name)

    @override
    def _do_install(self, content):
        return self.__scope.install_service_dropin(self.__service, self._file_name, content)


class BackupServiceSetup:  # pylint: disable=too-few-public-methods
    """This class provides configurataion and installation of the backup service."""

    def __init__(self, scope: _Scope, location: BackupLocation):
        self.__scope = scope
        self.__location = location

    def create_repo(self, config: BackupConfig, credential: SystemdCredential):
        """create initial backup repo

        Args:
            config (BackupConfig): backup configuration
            credential (SystemdCredential): backup encryption credential
        """
        print(f"Create backup repo for {self.__scope.user()}")
        base_command = [
            "systemd-run",
            "-P",
            "--wait",
            "-p",
            credential.encrypted_plain,
            "borgmatic",
            "repo-create",
            "--config",
            str(config.file_path()),
        ]
        command = self.__scope.systemd_command(base_command)
        if _settings.dry_run:
            return
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            _os_error(e)

    def export_key(self, config: BackupConfig, credential: SystemdCredential, key_path: Path):
        """export backup repo key to file

        Args:
            config (BackupConfig): backup configuration
            credential (SystemdCredential): backup encryption credential
            key_path (Path): folder to store backup encryption keys
        """
        create_dir(path=key_path, root_mode=0o777)
        key_file = key_path / (
            f"{self.__location.systemd_escaped}"
            f"-{self.__scope.user()}"
            f"-{self.__location.repo_suffix}.key"
        )
        print(f"Exporting repo key for {self.__scope.user()} to {key_path}")
        base_command = [
            "systemd-run",
            "-P",
            "--wait",
            "-p",
            credential.encrypted_plain,
            "borgmatic",
            "key",
            "export",
            "--paper",
            "--config",
            str(config.file_path()),
            "--path",
            str(key_file),
        ]
        command = self.__scope.systemd_command(base_command)
        if _settings.dry_run:
            return
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            _os_error(e)

    def setup(self, key_path: Path, notify_user: str = None) -> None:
        """setup backup service (otionally with notification of specific user)

        Args:
            notify_user (str, optional): user to notify about backup progress. Defaults to None.
            key_path (Path): where to store borg repo keys for safe keeping
        """
        # 1. configure systemd credential
        credential = SystemdCredential(self.__scope, "borgmatic")

        # 3. configure backup configuration
        config = BackupConfig(self.__scope, self.__location, credential)

        # 4. configure service
        backup_script = BackupScript()
        service = BackupServiceFile(
            scope=self.__scope,
            location=self.__location,
            config=config,
            script=backup_script,
            notify_user=notify_user,
        )
        # 5. configure service credential dropin
        service_dropin = BackupServiceCredentialFile(
            scope=self.__scope, service=service, credential=credential
        )
        initialize = not service_dropin.is_installed()

        if initialize:
            purpose = str(self.__scope)
            password = prompt_password(purpose)
            if not password:
                return  # skip installation in this scope on password mismatch
            credential.set_value(password)

        # 6. install credential dropin
        service_dropin.install(force=False)

        # 7. install configuration
        force = False
        if config.is_installed():
            if ask_user_confirmation("Overwrite backup config?"):
                force = True
        config.install(force)

        if initialize:
            # 8. create repo
            self.create_repo(config, credential)

            # 9. export key
            self.export_key(config, credential, key_path)

        # 10. install service
        force = False
        if service.is_installed():
            if ask_user_confirmation("Overwrite backup service unit?"):
                force = True
        service.install(force)

        # 7. enable the service
        service.enable()


def get_user_scopes(user_list: list[str]) -> set[_Scope]:
    """retrieve user scopes depending on provided user list.
    Each user is checked if it exists in the system.

    Args:
        user_list (list[str]): list of users

    Returns:
        set[_Scope]: without root privileges only the current user's scope
                     with root privileges all user scopes
    """
    if not i_am_root():
        return {UserScope(current_username())}

    scopes = set()
    for user in user_list:
        try:
            scopes.add(UserScope(user))
        except KeyError:
            print(f"User '{user}' does not exist!")
            sys.exit(os.EX_NOUSER)
    return scopes


@dataclass(kw_only=True)
class _Command:
    command: str


@dataclass(kw_only=True)
class SetupAutoMountCommand(_Command):
    """CLI argument type annotation helper for auto mount configuration"""

    dry_run: bool
    mount_path: Path
    shared: bool


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True)
class SetupBackupCommand(_Command):
    """CLI argument type annotation helper for auto backup configuration"""

    dry_run: bool
    path: Path
    repo: str
    info: bool
    user: list[str]
    system: bool
    notify: str | None
    key_path: Path


def configure_automount(arguments: SetupAutoMountCommand):
    """Configure automount"""
    set_dry_run(arguments.dry_run)

    if not i_am_root():
        print(f"Error: '{arguments.command}' requires root privileges. Aborted.", file=sys.stderr)
        sys.exit(os.EX_NOPERM)
    file_system = ExternalFileSystem(arguments.mount_path)
    if not file_system.hotpluggable:
        print("Error: hotpluggable block device required. Aborted.", file=sys.stderr)
        sys.exit(os.EX_USAGE)
    if file_system.uuid is None:
        print(f"Error: filesystem has no UUID: {arguments.mount_path}. Aborted.", file=sys.stderr)
        sys.exit(os.EX_USAGE)
    if arguments.shared:
        udev_rule = SharedUdevRule(file_system)
    else:
        udev_rule = PrivateUdevRule(file_system)
    force = False
    if udev_rule.is_installed():
        if ask_user_confirmation("Overwrite existing udev configuration?"):
            force = True
    print(file_system)
    if not ask_user_confirmation(f"Continue{' (dry-run)' if arguments.dry_run else ''}?"):
        print("Aborted.")
        return
    udev_rule.install(force)
    print(f"Please remove and plug in '{file_system.device}' again to confirm configuration works.")


def configure_backup(arguments: SetupBackupCommand):
    """Configure automatic backup"""

    set_dry_run(arguments.dry_run)

    # 1. collect information on backup location
    backup_location = BackupLocation(arguments.path, arguments.repo)
    print(backup_location)

    # 2. check privilege
    if len(arguments.user) > 1:
        # multi-user setup
        if not i_am_root():
            print("Error: multi-user setup requires root privileges.", file=sys.stderr)
            sys.exit(os.EX_USAGE)
        if not backup_location.allows_multi_user_access():
            print(
                "Error: multi-user setup requires location with multi-user access.", file=sys.stderr
            )
            print(
                "Consider reconfiguring the external filesystem using 'setup-automount --shared'",
                file=sys.stderr,
            )
            sys.exit(os.EX_USAGE)
    if arguments.system and not i_am_root():
        print("Error: multi-user setup requires root privileges.", file=sys.stderr)
        sys.exit(os.EX_USAGE)

    # 3. determine whether notification service can be enabled
    notify_scope = None
    if arguments.notify:
        if i_am_root() or (arguments.notify == current_username()):
            print(f"Enabling backup status notifications for '{arguments.notify}'")
            notify_scope = UserScope(arguments.notify)

    # 4. determine scopes to install backup service in
    scopes = get_user_scopes(arguments.user)
    print((f"Installing user backup service for: {', '.join(map(str, scopes))}"))
    # 5. add system scope if applicable
    if i_am_root():
        scopes.add(SystemScope())
        print("Installing system backup service.")

    if arguments.info:
        return

    if not ask_user_confirmation(f"Continue{' (dry-run)' if arguments.dry_run else ''}?"):
        print("Aborted.")
        return

    # 6. enable notification service
    if notify_scope:
        notify_scope.enable_service("automatic-backup-notification")

    # 7. install backup services in all scopes
    for scope in scopes:
        backup_service = BackupServiceSetup(scope, backup_location)
        backup_service.setup(key_path=arguments.key_path, notify_user=arguments.notify)


def main() -> None:
    """main function"""

    def parse_arguments() -> SetupBackupCommand | SetupAutoMountCommand:
        """Parse commandline arguments.

        Returns:
            Arguments: parsed commandline arguments
        """
        parser = argparse.ArgumentParser(
            prog="configure-automatic-backup",
            description="Configure automatic backup triggered by mounting configured filesystem.",
        )
        parser.add_argument("--version", action="version", version=f"{parser.prog} {__VERSION}")

        subparsers = parser.add_subparsers(
            dest="command", help="Available subcommands", required=True
        )
        automount_command_parser = subparsers.add_parser("setup-automount", help="Setup automount.")
        automount_command_parser.add_argument(
            "--dry-run", action="store_true", help="Dry-run", default=False, required=False
        )
        automount_command_parser.add_argument(
            "--mount-path",
            type=Path,
            help="Mount point of external filesystem to configure",
            required=True,
        )
        automount_command_parser.add_argument(
            "--shared",
            action="store_true",
            help="Configure as shared mount (multi-user setup).",
            default=False,
        )

        backup_command_parser = subparsers.add_parser(
            "setup-backup", help="Setup automatic backup."
        )
        backup_command_parser.add_argument(
            "--dry-run", action="store_true", help="Dry-run", default=False, required=False
        )
        backup_command_parser.add_argument(
            "--path",
            metavar="FOLDER",
            type=Path,
            help="Base path where backups will be stored (mount point of backup filesystem).",
            required=True,
        )
        backup_command_parser.add_argument(
            "--repo",
            metavar="REPO-NAME",
            type=str,
            help="Base backup repository name.",
            required=True,
        )
        backup_command_parser.add_argument(
            "--info", action="store_true", default=False, help="Only print information."
        )
        backup_command_parser.add_argument(
            "--user",
            action="append",
            type=str,
            help="Install user service for given username.",
        )
        backup_command_parser.add_argument(
            "--system",
            action="store_true",
            default=False,
            help="Install system service.",
        )
        backup_command_parser.add_argument(
            "--notify",
            metavar="USER",
            type=str,
            help="User to inform about backup progress via notif-send.",
            default=None,
            required=False,
        )
        backup_command_parser.add_argument(
            "--key-path",
            metavar="FOLDER",
            type=Path,
            help="Path where to store repo keys",
            default=Path.cwd() / "borg-keys",
            required=False,
        )

        args, _ = parser.parse_known_args()
        if args.command == "setup-backup":
            return SetupBackupCommand(**vars(args))
        if args.command == "setup-automount":
            return SetupAutoMountCommand(**vars(args))
        raise NotImplementedError("Unhandled command")

    arguments = parse_arguments()

    if isinstance(arguments, SetupBackupCommand):
        configure_backup(arguments)
    elif isinstance(arguments, SetupAutoMountCommand):
        configure_automount(arguments)


if __name__ == "__main__":
    main()
