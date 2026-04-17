"""Unittests for 'configure.py'"""

# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=too-many-lines
# pylint: disable=too-many-public-methods

import os
import pwd
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import override
from unittest import mock

from configure import (
    BackupExcludeUserFile,
    BackupExcludeSystemFile,
    BackupConfig,
    BackupDevice,
    BackupScript,
    BackupServiceFile,
    BackupServiceCredentialFile,
    BackupServiceSetup,
    Ext4UdevRule,
    SystemdCredential,
    SystemScope,
    UserScope,
    ask_user_confirmation,
    create_dir,
    current_username,
    i_am_root,
    prompt_password,
    set_dry_run,
    switch_user_command,
    systemd_escape,
    write_file,
)


class _TestConfigureBase(unittest.TestCase):
    """Base Unittest class providing basic infrastructure and test data"""

    @override
    def setUp(self):
        set_dry_run(False)


class TestConfigure(_TestConfigureBase):  # pylint: disable=too-many-public-methods
    """Test generic methods from 'configure.py'."""

    def test_i_am_root(self):
        with mock.patch("os.getuid") as mock_uid:
            mock_uid.return_value = 0
            self.assertTrue(i_am_root())

            mock_uid.return_value = 1000
            self.assertFalse(i_am_root())

    def test_current_username(self):
        """Test getting current username."""
        self.assertEqual(current_username(), os.environ.get("USER"))

    def test_switch_user_command(self):
        self.assertListEqual(
            switch_user_command("fake-user", ["cat", "/home/fake-user/.bashrc"]),
            ["run0", "-u", "fake-user", "cat", "/home/fake-user/.bashrc"],
        )

    def test_ask_user_confirmation_unrecognized_answer_no(self):
        with mock.patch("configure.input", create=True, side_effect=["Maybe", "No"]) as input_mock:
            self.assertFalse(ask_user_confirmation("test"))
            self.assertEqual(input_mock.call_count, 2)

    def test_ask_user_confirmation_unrecognized_answer_y(self):
        with mock.patch("configure.input", create=True, side_effect=["", "y"]) as input_mock:
            self.assertTrue(ask_user_confirmation("test"))
            self.assertEqual(input_mock.call_count, 2)

    def test_ask_user_confirmation_recognized_answer_n(self):
        with mock.patch("configure.input", create=True, side_effect=["n"]) as input_mock:
            self.assertFalse(ask_user_confirmation("test"))
            self.assertEqual(input_mock.call_count, 1)

    def test_ask_user_confirmation_recognized_answer_yes(self):
        with mock.patch("configure.input", create=True, side_effect=["Yes"]) as input_mock:
            self.assertTrue(ask_user_confirmation("test"))
            self.assertEqual(input_mock.call_count, 1)

    def test_write_file_user(self):
        test_content = "this is a test\nand another test!"

        with TemporaryDirectory() as tmp_dir:
            tmp_file = Path(tmp_dir) / "tmpfile"
            write_file(tmp_file, test_content)
            self.assertTrue(tmp_file.is_file())
            with tmp_file.open("r", encoding="utf-8") as tf:
                self.assertEqual("".join(tf.readlines()), test_content)

    def test_write_file_user_dry_run(self):
        test_content = "this is a test\nand another test!"
        set_dry_run(True)
        with TemporaryDirectory() as tmp_dir:
            tmp_file = Path(tmp_dir) / "tmpfile"
            write_file(tmp_file, test_content)
            self.assertFalse(tmp_file.exists())

    def test_write_file_other_user(self):
        test_content = "test content\nanother test\nand another"

        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("configure.i_am_root") as mock_i_am_root,
            mock.patch("os.chown") as mock_chown,
        ):
            target_file = Path(tmp_dir) / "tmpfile"
            mock_i_am_root.return_value = True
            write_file(target_file, test_content, 1234, 1234)
            mock_chown.assert_has_calls(
                [
                    mock.call(path=target_file, uid=1234, gid=1234),
                ]
            )

    def test_create_dir_user(self):
        with TemporaryDirectory() as tmp_dir:
            target_dir = Path(tmp_dir) / "tmpdir"
            create_dir(path=target_dir)
            self.assertTrue(target_dir.is_dir())

    def test_create_dir_user_dry_run(self):
        set_dry_run(True)
        with TemporaryDirectory() as tmp_dir:
            target_dir = Path(tmp_dir) / "tmpdir"
            create_dir(path=target_dir)
            self.assertFalse(target_dir.exists())

    def test_create_dir_user_recursive(self):
        with TemporaryDirectory() as tmp_dir:
            target_dir = Path(tmp_dir) / "tmpdir" / "second" / "floor"
            create_dir(path=target_dir)
            self.assertTrue(target_dir.is_dir())

    def test_create_dir_user_recursive_dry_run(self):
        set_dry_run(True)
        with TemporaryDirectory() as tmp_dir:
            target_dir_first = Path(tmp_dir) / "tmpdir"
            target_dir_second = target_dir_first / "second" / "floor"
            create_dir(path=target_dir_second)
            self.assertFalse(target_dir_second.exists())
            self.assertFalse(target_dir_first.exists())

    def test_create_dir_other_user(self) -> None:
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("configure.i_am_root") as mock_i_am_root,
            mock.patch("os.chown") as mock_chown,
        ):
            target_dir = Path(tmp_dir) / "tmpdir"
            mock_i_am_root.return_value = True
            create_dir(path=target_dir, uid=1234, gid=1234)
            mock_chown.assert_has_calls(
                [
                    mock.call(path=target_dir, uid=1234, gid=1234),
                ]
            )

    def test_create_dir_other_user_recursive(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("configure.i_am_root", return_value=True),
            mock.patch("os.chown") as mock_chown,
        ):
            target_dir = Path(tmp_dir) / "tmpdir" / "second" / "floor"
            create_dir(path=target_dir, uid=1234, gid=1234)
            mock_chown.assert_has_calls(
                [
                    mock.call(path=target_dir.parent.parent, uid=1234, gid=1234),
                    mock.call(path=target_dir.parent, uid=1234, gid=1234),
                    mock.call(path=target_dir, uid=1234, gid=1234),
                ]
            )

    def test_create_dir_system_no_mode(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("configure.i_am_root", return_value=True),
            mock.patch("os.chown") as mock_chown,
            mock.patch("os.chmod") as mock_chmod,
        ):
            target_dir = Path(tmp_dir) / "dir"
            create_dir(path=target_dir, uid=0, gid=0)
            mock_chown.assert_called_once_with(path=target_dir, uid=0, gid=0)
            mock_chmod.assert_not_called()

    def test_create_dir_system_with_mode(self):
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("configure.i_am_root", return_value=True),
            mock.patch("os.chown") as mock_chown,
            mock.patch("os.chmod") as mock_chmod,
        ):
            target_dir = Path(tmp_dir) / "dir"
            create_dir(path=target_dir, uid=0, gid=0, root_mode=0o777)
            mock_chown.assert_called_once_with(path=target_dir, uid=0, gid=0)
            mock_chmod.assert_called_once_with(path=target_dir, mode=0o777)

    def test_systemd_escape(self):
        self.assertEqual(systemd_escape("/a/b/c/d"), "a-b-c-d")


class _TestWithFakeUserScope(_TestConfigureBase):  # pylint: disable=too-many-instance-attributes
    def _do_setup(self):
        self.tmp_dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp_dir.cleanup)
        self.fake_current_user = "fakecurrentuser"
        self.fake_current_home = Path(self.tmp_dir.name) / "home" / "fakecurrentuser"
        self.fake_current_uid = 1337
        self.fake_current_gid = 1337
        self.fake_current_home.mkdir(parents=True)
        self.fake_current_user_info = pwd.struct_passwd(
            (
                self.fake_current_user,  # pw_name
                "x",  # pw_passwd
                self.fake_current_uid,  # pw_uid
                self.fake_current_gid,  # pw_gid
                "Fake Current User",  # pw_gecos
                str(self.fake_current_home),  # pw_dir
                "/bin/fakesh",  # pw_shell
            )
        )

        self.fake_other_user = "fakeotheruser"
        self.fake_other_home = Path(self.tmp_dir.name) / "home" / "fakeotheruser"
        self.fake_other_uid = 1338
        self.fake_other_gid = 1338
        self.fake_other_home.mkdir(parents=True)
        self.fake_other_user_info = pwd.struct_passwd(
            (
                self.fake_other_user,  # pw_name
                "x",  # pw_passwd
                self.fake_other_uid,  # pw_uid
                self.fake_other_gid,  # pw_gid
                "Fake Other User",  # pw_gecos
                str(self.fake_other_home),  # pw_dir
                "/bin/fakesh",  # pw_shell
            )
        )

        def __mock_getpwnam(username: str):
            if username == "fakecurrentuser":
                return self.fake_current_user_info
            if username == "fakeotheruser":
                return self.fake_other_user_info
            raise KeyError(f"mock_getpwnam(): name not found: '{username}'")

        self.patch_getpwnam = mock.patch("pwd.getpwnam")
        self.mock_getpwnam = self.patch_getpwnam.start()
        self.mock_getpwnam.side_effect = __mock_getpwnam
        self.addCleanup(self.patch_getpwnam.stop)

        self.patch_current_username = mock.patch("configure.current_username")
        self.mock_current_username = self.patch_current_username.start()
        self.mock_current_username.return_value = self.fake_current_user
        self.addCleanup(self.patch_getpwnam.stop)

    @override
    def setUp(self):
        self._do_setup()
        super().setUp()


class TestScope(_TestWithFakeUserScope):
    def test_prompt_password(self):
        with (
            mock.patch("configure.systemd_ask_password") as ap,
            mock.patch("builtins.print") as mock_print,
        ):
            ap.side_effect = ["same password", "same password"]
            self.assertEqual(prompt_password("system"), "same password")
            mock_print.assert_has_calls(
                [
                    mock.call("Enter password for system:"),
                    mock.call("Repeat password for system:"),
                ]
            )
            mock_print.reset_mock()
            ap.side_effect = ["password", "different password"]
            self.assertEqual(prompt_password("user 'fakeuser'"), None)
            mock_print.assert_has_calls(
                [
                    mock.call("Enter password for user 'fakeuser':"),
                    mock.call("Repeat password for user 'fakeuser':"),
                    mock.call("Passwords did not match!", file=sys.stderr),
                ]
            )

    def test_systemd_command_current_user(self):
        user_scope = UserScope(self.fake_current_user)

        self.assertSequenceEqual(
            user_scope.systemd_command(["systemctl", "start", "my.service"]),
            ["systemctl", "--user", "start", "my.service"],
        )
        self.assertSequenceEqual(
            user_scope.systemd_command(["systemd-creds", "encrypt", "--name=test", "-", "-"]),
            ["systemd-creds", "--user", "encrypt", "--name=test", "-", "-"],
        )

    def test_systemd_command_other_user(self):
        other_scope = UserScope(self.fake_other_user)
        with self.assertRaises(RuntimeError):
            other_scope.systemd_command(["systemctl", "start", "my.service"])
        with self.assertRaises(RuntimeError):
            other_scope.systemd_command(["systemctl", "start", "my.service"])

        with mock.patch("configure.i_am_root") as mock_i_am_root:
            mock_i_am_root.return_value = True
            self.assertSequenceEqual(
                other_scope.systemd_command(["systemd-creds", "encrypt", "--name=test", "-", "-"]),
                [
                    "run0",
                    "-u",
                    self.fake_other_user,
                    "systemd-creds",
                    "--user",
                    "encrypt",
                    "--name=test",
                    "-",
                    "-",
                ],
            )
            self.assertSequenceEqual(
                other_scope.systemd_command(["systemd-creds", "encrypt", "--name=test", "-", "-"]),
                [
                    "run0",
                    "-u",
                    self.fake_other_user,
                    "systemd-creds",
                    "--user",
                    "encrypt",
                    "--name=test",
                    "-",
                    "-",
                ],
            )

    def test_systemd_command_system(self):
        system_scope = SystemScope()

        self.assertSequenceEqual(
            system_scope.systemd_command(["systemctl", "start", "my.service"]),
            ["systemctl", "start", "my.service"],
        )
        self.assertSequenceEqual(
            system_scope.systemd_command(["systemd-creds", "encrypt", "--name=test", "-", "-"]),
            ["systemd-creds", "encrypt", "--name=test", "-", "-"],
        )

    def test_user_user(self):
        user_scope = UserScope(self.fake_current_user)
        self.assertEqual(user_scope.user(), self.fake_current_user)

    def test_user_system(self):
        system_scope = SystemScope()
        self.assertEqual(system_scope.user(), "root")

    def test_scope_user(self):
        user_scope = UserScope(self.fake_current_user)
        self.assertEqual(user_scope.scope(), f"user-{self.fake_current_user}")

    def test_scope_system(self):
        system_scope = SystemScope()
        self.assertEqual(system_scope.scope(), "system")

    def test_string_user(self):
        user_scope = UserScope(self.fake_current_user)
        self.assertEqual(f"{user_scope}", f"user '{self.fake_current_user}'")

    def test_string_system(self):
        system_scope = SystemScope()
        self.assertEqual(f"{system_scope}", "system")

    def test_home_user(self):
        user_scope = UserScope(self.fake_current_user)
        self.assertEqual(user_scope.home(), self.fake_current_home)

    def test_home_system(self):
        system_scope = SystemScope()
        self.assertEqual(system_scope.home(), Path("/"))

    def test_is_system_scope_user(self):
        user_scope = UserScope(self.fake_current_user)
        self.assertFalse(user_scope.is_system_scope())

    def test_is_system_scope_system(self):
        system_scope = SystemScope()
        self.assertTrue(system_scope.is_system_scope())

    def test_config_user(self):
        user_scope = UserScope(self.fake_current_user)
        fake_user_config = self.fake_current_home / ".config" / "test-app" / "my.conf"
        self.assertEqual(user_scope.config_path("test-app", "my.conf"), fake_user_config)
        self.assertFalse(user_scope.is_config_installed("test-app", "my.conf"))
        self.assertFalse(fake_user_config.exists())
        test_content = "test=abc\nbla=foo"
        user_scope.install_config("test-app", "my.conf", test_content)
        self.assertTrue(user_scope.is_config_installed("test-app", "my.conf"))
        self.assertTrue(fake_user_config.is_file())
        with fake_user_config.open("r", encoding="utf-8") as c_f:
            content = c_f.read()
        self.assertEqual(content, test_content)

    def test_config_path_system(self):
        system_scope = SystemScope()
        fake_system_config = Path("/etc") / "test-app" / "my.conf"
        self.assertEqual(system_scope.config_path("test-app", "my.conf"), fake_system_config)
        self.assertFalse(system_scope.is_config_installed("test-app", "my.conf"))
        self.assertFalse(fake_system_config.exists())
        test_content = "test=abc\nbla=foo"
        with (
            mock.patch("configure.create_dir"),
            mock.patch("configure.write_file") as mock_write_file,
        ):
            system_scope.install_config("test-app", "my.conf", test_content)
            mock_write_file.assert_called_once_with(
                path=fake_system_config, content=test_content, uid=0, gid=0
            )

    def test_service_user(self):
        user_scope = UserScope(self.fake_current_user)
        fake_user_service = (
            self.fake_current_home / ".config" / "systemd" / "user" / "daemon.service"
        )
        self.assertEqual(user_scope.service_path("daemon"), fake_user_service)
        self.assertFalse(user_scope.is_service_installed("daemon"))
        self.assertFalse(fake_user_service.exists())
        test_content = "[Service]\ntest=abc\nbla=foo"
        user_scope.install_service("daemon", test_content)
        self.assertTrue(user_scope.is_service_installed("daemon"))
        self.assertTrue(fake_user_service.is_file())
        with fake_user_service.open("r", encoding="utf-8") as s_f:
            content = s_f.read()
        self.assertEqual(content, test_content)

    def test_service_system(self):
        system_scope = SystemScope()
        fake_system_service = Path("/etc/systemd/system") / "daemon.service"
        self.assertEqual(system_scope.service_path("daemon"), fake_system_service)
        self.assertFalse(system_scope.is_service_installed("daemon"))
        self.assertFalse(fake_system_service.exists())
        test_content = "[Service]\ntest=abc\nbla=foo"
        with (
            mock.patch("configure.create_dir"),
            mock.patch("configure.write_file") as mock_write_file,
        ):
            system_scope.install_service("daemon", test_content)
            mock_write_file.assert_called_once_with(
                path=fake_system_service, content=test_content, uid=0, gid=0
            )

    def test_enable_service_user(self):
        with mock.patch("subprocess.run") as mock_run:
            user_scope = UserScope(self.fake_current_user)
            user_scope.enable_service("fake-test")
            mock_run.assert_called_once_with(
                ["systemctl", "--user", "enable", "fake-test.service"],
                check=True,
            )

    def test_enable_service_system(self):
        with mock.patch("subprocess.run") as mock_run:
            system_scope = SystemScope()
            system_scope.enable_service("fake-test")
            mock_run.assert_called_once_with(
                ["systemctl", "enable", "fake-test.service"],
                check=True,
            )

    def test_service_dropin_user(self):
        user_scope = UserScope(self.fake_current_user)
        fake_user_dropin = (
            self.fake_current_home
            / ".config"
            / "systemd"
            / "user"
            / "daemon.service.d"
            / "my-cfg.conf"
        )
        self.assertEqual(user_scope.service_dropin_path("daemon", "my-cfg"), fake_user_dropin)
        self.assertEqual(user_scope.service_dropin_path("daemon", "my-cfg.conf"), fake_user_dropin)
        self.assertFalse(user_scope.is_service_dropin_installed("daemon", "my-cfg"))
        self.assertFalse(fake_user_dropin.exists())
        test_content = "test=abc\nbla=foo"
        user_scope.install_service_dropin("daemon", "my-cfg", test_content)
        self.assertTrue(user_scope.is_service_dropin_installed("daemon", "my-cfg"))
        self.assertTrue(fake_user_dropin.is_file())
        with fake_user_dropin.open("r", encoding="utf-8") as c_f:
            content = c_f.read()
        self.assertEqual(content, test_content)

    def test_service_dropin_system(self):
        system_scope = SystemScope()
        fake_system_dropin = Path("/etc/systemd/system") / "daemon.service.d" / "my-cfg.conf"
        self.assertEqual(system_scope.service_dropin_path("daemon", "my-cfg"), fake_system_dropin)
        self.assertEqual(
            system_scope.service_dropin_path("daemon", "my-cfg.conf"), fake_system_dropin
        )
        self.assertFalse(system_scope.is_service_dropin_installed("daemon", "my-cfg.conf"))
        self.assertFalse(fake_system_dropin.exists())
        test_content = "test=abc\nbla=foo"
        with (
            mock.patch("configure.create_dir"),
            mock.patch("configure.write_file") as mock_write_file,
        ):
            system_scope.install_service_dropin("daemon", "my-cfg", test_content)
            mock_write_file.assert_called_once_with(
                path=fake_system_dropin, content=test_content, uid=0, gid=0
            )


class TestActualCurrentUserScope(_TestConfigureBase):
    def test_user(self):
        user_scope = UserScope(current_username())
        self.assertEqual(user_scope.user(), os.getenv("USER"))

    def test_home(self):
        user_scope = UserScope(current_username())
        self.assertEqual(user_scope.home(), Path.home())

    def test_config_path_user(self):
        user_scope = UserScope(current_username())
        self.assertEqual(
            user_scope.config_path("test-app", "my.conf"),
            Path.home() / ".config" / "test-app" / "my.conf",
        )

    def test_service_path_user(self):
        user_scope = UserScope(current_username())
        self.assertEqual(
            user_scope.service_path("daemon"),
            Path.home() / ".config" / "systemd" / "user" / "daemon.service",
        )

    def test_service_dropin_path_user(self):
        user_scope = UserScope(current_username())
        self.assertEqual(
            user_scope.service_dropin_path("daemon", "my-cfg"),
            Path.home() / ".config" / "systemd" / "user" / "daemon.service.d" / "my-cfg.conf",
        )


class TestSystemdCredential(_TestWithFakeUserScope):
    def setUp(self):
        super().setUp()
        self.pretty_encrypted_credential = "pretty:-encrypted-credential-base64-"
        self.plain_encrypted_credential = "-encrypted-credential\n-base64-"
        self.credential_name = "my-cred"
        self.plain_encrypted_credential_oneline = (
            f"SetCredentialEncrypted={self.credential_name}:-encrypted-credential-base64-"
        )

        def __mock_check_output(*args, **_):
            command = args[0]
            if "--pretty" in command:
                return self.pretty_encrypted_credential
            return self.plain_encrypted_credential

        self.patch_check_output = mock.patch("subprocess.check_output")
        self.mock_check_output = self.patch_check_output.start()
        self.mock_check_output.side_effect = __mock_check_output
        self.addCleanup(self.patch_check_output.stop)

    def test_systemd_credential_current_user(self):
        user_scope = UserScope(self.fake_current_user)
        credential = SystemdCredential(user_scope, self.credential_name)
        self.assertEqual(credential.name, self.credential_name)
        password = "Pa55w0rd"
        credential.set_value(password)
        self.mock_check_output.assert_has_calls(
            [
                mock.call(
                    [
                        "systemd-creds",
                        "--user",
                        "encrypt",
                        "--pretty",
                        f"--name={self.credential_name}",
                        "-",
                        "-",
                    ],
                    input=password,
                    text=True,
                ),
                mock.call(
                    [
                        "systemd-creds",
                        "--user",
                        "encrypt",
                        f"--name={self.credential_name}",
                        "-",
                        "-",
                    ],
                    input=password,
                    text=True,
                ),
            ]
        )
        self.assertEqual(credential.encrypted_pretty, self.pretty_encrypted_credential)
        self.assertEqual(credential.encrypted_plain, self.plain_encrypted_credential_oneline)

    def test_systemd_credential_other_user(self):
        user_scope = UserScope(self.fake_other_user)
        with mock.patch("configure.i_am_root") as mock_i_am_root:
            mock_i_am_root.return_value = True
            credential = SystemdCredential(user_scope, self.credential_name)
            self.assertEqual(credential.name, self.credential_name)
            password = "Pa55w0rd"
            credential.set_value(password)
            self.mock_check_output.assert_has_calls(
                [
                    mock.call(
                        [
                            "run0",
                            "-u",
                            self.fake_other_user,
                            "systemd-creds",
                            "--user",
                            "encrypt",
                            "--pretty",
                            f"--name={self.credential_name}",
                            "-",
                            "-",
                        ],
                        input=password,
                        text=True,
                    ),
                    mock.call(
                        [
                            "run0",
                            "-u",
                            self.fake_other_user,
                            "systemd-creds",
                            "--user",
                            "encrypt",
                            f"--name={self.credential_name}",
                            "-",
                            "-",
                        ],
                        input=password,
                        text=True,
                    ),
                ]
            )
            self.assertEqual(credential.encrypted_pretty, self.pretty_encrypted_credential)
            self.assertEqual(credential.encrypted_plain, self.plain_encrypted_credential_oneline)

    def test_systemd_credential_system(self):
        system_scope = SystemScope()
        credential = SystemdCredential(system_scope, self.credential_name)
        self.assertEqual(credential.name, self.credential_name)
        password = "Pa55w0rd"
        credential.set_value(password)
        self.mock_check_output.assert_has_calls(
            [
                mock.call(
                    [
                        "systemd-creds",
                        "encrypt",
                        "--pretty",
                        f"--name={self.credential_name}",
                        "-",
                        "-",
                    ],
                    input=password,
                    text=True,
                ),
                mock.call(
                    [
                        "systemd-creds",
                        "encrypt",
                        f"--name={self.credential_name}",
                        "-",
                        "-",
                    ],
                    input=password,
                    text=True,
                ),
            ]
        )
        self.assertEqual(credential.encrypted_pretty, self.pretty_encrypted_credential)
        self.assertEqual(credential.encrypted_plain, self.plain_encrypted_credential_oneline)


class _TestWithFakeDevice(_TestConfigureBase):  # pylint: disable=too-many-public-methods
    fs_type = "ext4"
    uuid = "ab501007-dead-beef-1337-422342234223"
    device = "/dev/mapper/luks-01234567-89ab-cdef-0123-456789abcdef"
    mount_point = Path("/run/media/test/target")
    folder = mount_point / "backup/directory"

    def __mock_findmnt_return_value(self, fstype: str) -> str:
        return f"""\
{{
   "filesystems": [
      {{
         "source": "{self.device}",
         "target": "{self.mount_point}",
         "fstype": "{fstype}",
         "uuid": "{self.uuid}"
      }}
   ]
}}\
"""

    target = "run-media-test-target"
    repo_suffix = "testing"

    def _do_setup(self):
        self.patch_findmnt = mock.patch("configure.BackupDevice._findmnt")
        self.mock_findmnt = self.patch_findmnt.start()
        self.mock_findmnt.return_value = self.__mock_findmnt_return_value(self.fs_type)

    @override
    def setUp(self):
        self._do_setup()
        super().setUp()


class TestBackupDevice(_TestWithFakeDevice):
    @override
    def setUp(self):
        super().setUp()
        self.backup_device = BackupDevice(self.folder, self.repo_suffix)

    def test_folder(self):
        self.assertEqual(self.backup_device.folder, self.folder)

    def test_folder_resolve(self):
        unresolved_folder = Path("/test/this/../../backup/directory")
        backup_device = BackupDevice(unresolved_folder, self.repo_suffix)
        self.assertEqual(backup_device.folder, Path("/backup/directory"))

    def test_repo_suffix(self):
        self.assertEqual(self.backup_device.repo_suffix, self.repo_suffix)

    def test_device(self):
        self.assertEqual(self.backup_device.device, self.device)

    def test_mount_point(self):
        self.assertEqual(self.backup_device.mount_point, self.mount_point)

    def test_filesystem_type(self):
        self.assertEqual(self.backup_device.filesystem_type, self.fs_type)

    def test_uuid(self):
        self.assertEqual(self.backup_device.uuid, self.uuid)

    def test_systemd_escaped(self):
        self.assertEqual(self.backup_device.systemd_escaped, self.target)

    def test_mount_unit(self):
        self.assertEqual(self.backup_device.mount_unit, f"{self.target}.mount")

    def test_str(self):
        self.assertEqual(
            str(self.backup_device),
            f"""\
Backup target:
  - Device: {self.device}
  - Mount point: {self.mount_point}
  - Backup path: {self.folder}
  - Filesystem: {self.fs_type}
  - UUID: {self.uuid}
  - Mount target: {self.target}
  - Mount unit: {self.target}.mount
  - Repo suffix: {self.repo_suffix}
""",
        )


class _TestWithFakeDeviceAndFakeUserScope(
    _TestWithFakeDevice, _TestWithFakeUserScope, _TestConfigureBase
):
    @override
    def setUp(self):
        _TestWithFakeDevice._do_setup(self)
        _TestWithFakeUserScope._do_setup(self)
        _TestConfigureBase.setUp(self)


class TestExt4UdevRule(_TestWithFakeDeviceAndFakeUserScope):
    def test_rule_content(self):
        backup_device = BackupDevice(Path("/what/ever/man"), "suffix")
        udev_rule = Ext4UdevRule(backup_device)

        udev_rule_content = (
            f'SUBSYSTEM=="block", ENV{{ID_FS_UUID}}=="{self.uuid}" ENV{{UDISKS_AUTO}}="1"\n'
        )

        udev_rule_file = Path("/etc/udev/rules.d") / f"65-ext4-automount-{self.uuid}.rules"

        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            udev_rule.install()
            mock_write_file.assert_called_once_with(
                path=udev_rule_file,
                content=udev_rule_content,
                uid=0,
                gid=0,
            )


class TestBackupExcludes(_TestWithFakeDeviceAndFakeUserScope):
    def test_exclude_user(self):
        user_scope = UserScope(self.fake_current_user)
        backup_device = BackupDevice(Path("/fake/path"), "fake-repo")
        exclude = BackupExcludeUserFile(user_scope, backup_device)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            exclude.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                self.fake_current_home
                / ".config"
                / "borgmatic"
                / f"excludes-user-{backup_device.systemd_escaped}",
            )
            self.assertEqual(uid, self.fake_current_uid)
            self.assertEqual(gid, self.fake_current_gid)

            self.assertIn(f"{self.fake_current_home}/.cache", content)

    def test_exclude_system(self):
        backup_device = BackupDevice(Path("/fake/path"), "fake-repo")
        exclude = BackupExcludeSystemFile(backup_device)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            exclude.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                Path("/etc/borgmatic") / f"excludes-system-{backup_device.systemd_escaped}",
            )
            self.assertEqual(uid, 0)
            self.assertEqual(gid, 0)

            self.assertNotIn("@@", content)

            self.assertIn("/var/cache", content)


class TestBackupConfig(_TestWithFakeDeviceAndFakeUserScope):
    def test_config_user(self):
        scope = UserScope(self.fake_current_user)
        fake_path = Path("/fake/path")
        fake_repo = "fake-repo"
        backup_device = BackupDevice(fake_path, fake_repo)
        credential = SystemdCredential(scope, "borgmatic")
        config = BackupConfig(scope, backup_device, credential)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            config.install()

            self.assertEqual(mock_write_file.call_count, 2)

            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                self.fake_current_home
                / ".config"
                / "borgmatic"
                / f"borgmatic-config-{backup_device.systemd_escaped}.yaml",
            )
            self.assertEqual(uid, self.fake_current_uid)
            self.assertEqual(gid, self.fake_current_gid)

            self.assertNotIn("@@", content)

            self.assertIn(
                (
                    f"commands:\n"
                    f"  - before: repository\n"
                    f"    run:\n"
                    f"      - findmnt {backup_device.folder} > /dev/null || exit 75"
                ),
                content,
            )
            self.assertIn(
                (
                    f"repositories:\n"
                    f"    # The local path or Borg URL of the repository.\n"
                    f"    - path: {fake_path}/{scope.scope()}-{fake_repo}\n"
                ),
                content,
            )
            self.assertIn(f"      label: {scope.scope()}-{fake_repo}", content)
            self.assertIn(
                (f"exclude_from:\n" f"    - {config.exclude.file_path()}"),
                content,
            )
            self.assertIn(f"source_directories:\n    - {scope.home()}", content)
            self.assertIn(
                f'encryption_passphrase: "{{credential systemd {credential.name}}}"', content
            )
        self.assertEqual(config.repo_path(), Path("/fake/path/user-fakecurrentuser-fake-repo"))

    def test_config_system(self):
        scope = SystemScope()
        fake_path = Path("/fake/path")
        fake_repo = "fake-repo"
        backup_device = BackupDevice(fake_path, fake_repo)
        credential = SystemdCredential(scope, "borgmatic")
        config = BackupConfig(scope, backup_device, credential)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            config.install()

            self.assertEqual(mock_write_file.call_count, 2)

            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                Path("/etc")
                / "borgmatic"
                / f"borgmatic-config-{backup_device.systemd_escaped}.yaml",
            )
            self.assertEqual(uid, 0)
            self.assertEqual(gid, 0)

            self.assertNotIn("@@", content)

            self.assertIn(
                (
                    f"commands:\n"
                    f"  - before: repository\n"
                    f"    run:\n"
                    f"      - findmnt {backup_device.folder} > /dev/null || exit 75"
                ),
                content,
            )
            self.assertIn(
                (
                    f"repositories:\n"
                    f"    # The local path or Borg URL of the repository.\n"
                    f"    - path: {fake_path}/{scope.scope()}-{fake_repo}\n"
                ),
                content,
            )
            self.assertIn(f"      label: {scope.scope()}-{fake_repo}", content)
            self.assertIn(
                (f"exclude_from:\n" f"    - {config.exclude.file_path()}"),
                content,
            )
            self.assertIn(f"source_directories:\n    - {scope.home()}", content)
            self.assertIn(
                f'encryption_passphrase: "{{credential systemd {credential.name}}}"', content
            )
        self.assertEqual(config.repo_path(), Path("/fake/path/system-fake-repo"))


class TestBackupService(_TestWithFakeDeviceAndFakeUserScope):
    systemd_inhibit = (
        'systemd-inhibit --what=idle:sleep:shutdown --who="%N" --why="automatic backup"'
    )

    def test_service_user(self):
        user_scope = UserScope(self.fake_current_user)
        fake_path = Path("/bla/foo")
        device = BackupDevice(fake_path, self.repo_suffix)
        credential = SystemdCredential(user_scope, "borgmatic")
        config = BackupConfig(user_scope, device, credential)
        service = BackupServiceFile(
            scope=user_scope,
            device=device,
            config=config,
            script=BackupScript(),
            notify_user=self.fake_other_user,
        )
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            service.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                self.fake_current_home
                / ".config"
                / "systemd"
                / "user"
                / f"automatic-backup-{device.systemd_escaped}.service",
            )
            self.assertEqual(uid, self.fake_current_uid)
            self.assertEqual(gid, self.fake_current_gid)

            self.assertNotIn("@@", content)

            self.assertIn(
                (
                    f"Description=Automatic backup to '{fake_path}'\n"
                    f"Requires={device.mount_unit}\n"
                    f"After={device.mount_unit}\n"
                ),
                content,
            )
            self.assertIn(
                (f'ReadWritePaths="{fake_path}" -%h/.cache/borg -%h/.config/borg -%h/.borgmatic'),
                content,
            )
            self.assertIn(
                (f"[Install]\n" f"WantedBy={device.mount_unit}\n"),
                content,
            )
            self.assertIn(self.systemd_inhibit, content)
            main_command = (
                f'"{Path(__file__).parent}/automatic_backup.py"'
                f' --config "{config.file_path()}"'
                f' --uuid "{self.uuid}"'
                f' --path "{fake_path}"'
                f' --notify "{self.fake_other_user}"'
                "\n"
            )
            exec_start = f"ExecStart={self.systemd_inhibit} {main_command}"
            self.assertIn(exec_start, content)

    def test_service_system(self):
        system_scope = SystemScope()
        fake_path = Path("/bla/foo")
        device = BackupDevice(fake_path, self.repo_suffix)
        credential = SystemdCredential(system_scope, "borgmatic")
        config = BackupConfig(system_scope, device, credential)
        service = BackupServiceFile(
            scope=system_scope,
            device=device,
            config=config,
            script=BackupScript(),
            notify_user=self.fake_other_user,
        )
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            service.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                Path("/etc/systemd/system") / f"automatic-backup-{device.systemd_escaped}.service",
            )
            self.assertEqual(uid, 0)
            self.assertEqual(gid, 0)

            self.assertNotIn("@@", content)

            self.assertIn(
                (
                    f"Description=Automatic backup to '{fake_path}'\n"
                    f"Requires={device.mount_unit}\n"
                    f"After={device.mount_unit}\n"
                ),
                content,
            )
            self.assertIn(
                (f'ReadWritePaths="{fake_path}" -%h/.cache/borg -%h/.config/borg -%h/.borgmatic'),
                content,
            )
            self.assertIn(
                (f"[Install]\n" f"WantedBy={device.mount_unit}\n"),
                content,
            )
            self.assertIn(self.systemd_inhibit, content)
            main_command = (
                f'"{Path(__file__).parent}/automatic_backup.py"'
                f' --config "{config.file_path()}"'
                f' --uuid "{device.uuid}"'
                f' --path "{fake_path}"'
                f' --notify "{self.fake_other_user}"'
                "\n"
            )
            exec_start = f"ExecStart={self.systemd_inhibit} {main_command}"
            self.assertIn(exec_start, content)


class TestBackupCredentials(_TestWithFakeDeviceAndFakeUserScope):
    credential_text = (
        "SetCredentialEncrypted=borgmatic: \\\n"
        "        p4ptHsi4/HNIT+b4nZ2IwKgtCoHcb7NAuhMkvKMA0yrGuJ+IGMUKr7PACjNGd+ELMjkCJ \\\n"
        "        Z6hwfhBVzjRLj5VOngfXgDi0ZKzPnc4+HkDjVd5+O+wY/QX1yQ+PbfmmJeJCelLb09SmR \\\n"
        "        wdw1i37YCdAhguSlNCYrwLKEVecijZc2nXC7n1L310aCjvervdVmYs99BxTX6UniRa1M5 \\\n"
        "        GWevgOkbn/dkatzOBK341j7A1CqaqGqVN5b4EMUL+ujQZT2j21BfND4ZpOrm1GJS5yKyt \\\n"
        "        szGisal7s8kU/15noinjT3DaVe7kVC3+iXD/NCtnbb4OB9xf9WGBb5/hrJqKy3w==\n"
    )

    def test_credential_current_user(self):
        user_scope = UserScope(self.fake_current_user)
        credential = SystemdCredential(user_scope, "borgmatic")
        device = BackupDevice(Path("/fake/path"), "fake-repo")
        config = BackupConfig(user_scope, device, credential)
        script = BackupScript()
        service = BackupServiceFile(scope=user_scope, device=device, config=config, script=script)
        credential_dropin = BackupServiceCredentialFile(user_scope, service, credential)

        with mock.patch("subprocess.check_output") as mock_check_output:
            mock_check_output.return_value = self.credential_text
            credential.set_value("secred-password")
            self.assertEqual(credential.encrypted_pretty, self.credential_text)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            credential_dropin.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                self.fake_current_home
                / ".config/systemd/user"
                / f"automatic-backup-{device.systemd_escaped}.service.d"
                / "credential.conf",
            )
            self.assertEqual(uid, self.fake_current_uid)
            self.assertEqual(gid, self.fake_current_gid)

            self.assertNotIn("@@", content)

            self.assertIn(f"[Service]\n{self.credential_text}", content)

    def test_credential_other_user(self):
        user_scope = UserScope(self.fake_other_user)
        credential = SystemdCredential(user_scope, "borgmatic")
        device = BackupDevice(Path("/fake/path"), "fake-repo")
        config = BackupConfig(user_scope, device, credential)
        script = BackupScript()
        service = BackupServiceFile(scope=user_scope, device=device, config=config, script=script)
        credential_dropin = BackupServiceCredentialFile(user_scope, service, credential)

        with (
            mock.patch("subprocess.check_output") as mock_check_output,
            mock.patch("configure.i_am_root", return_value=True),
        ):
            mock_check_output.return_value = self.credential_text
            credential.set_value("secred-password")
            self.assertEqual(credential.encrypted_pretty, self.credential_text)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            credential_dropin.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                self.fake_other_home
                / ".config/systemd/user"
                / f"automatic-backup-{device.systemd_escaped}.service.d"
                / "credential.conf",
            )
            self.assertEqual(uid, self.fake_other_uid)
            self.assertEqual(gid, self.fake_other_gid)

            self.assertNotIn("@@", content)

            self.assertIn(f"[Service]\n{self.credential_text}", content)

    def test_credential_system(self):
        system_scope = SystemScope()
        credential = SystemdCredential(system_scope, "borgmatic")
        device = BackupDevice(Path("/fake/path"), "fake-repo")
        config = BackupConfig(system_scope, device, credential)
        script = BackupScript()
        service = BackupServiceFile(scope=system_scope, device=device, config=config, script=script)
        credential_dropin = BackupServiceCredentialFile(system_scope, service, credential)

        with mock.patch("subprocess.check_output") as mock_check_output:
            mock_check_output.return_value = self.credential_text
            credential.set_value("secret-password")
            self.assertEqual(credential.encrypted_pretty, self.credential_text)
        with (
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
        ):
            credential_dropin.install()

            mock_write_file.assert_called_once()
            path: Path = mock_write_file.call_args.kwargs["path"]
            content: str = mock_write_file.call_args.kwargs["content"]
            uid: int = mock_write_file.call_args.kwargs["uid"]
            gid: int = mock_write_file.call_args.kwargs["gid"]

            self.assertEqual(
                path,
                Path("/etc/systemd/system")
                / f"automatic-backup-{device.systemd_escaped}.service.d"
                / "credential.conf",
            )
            self.assertEqual(uid, 0)
            self.assertEqual(gid, 0)

            self.assertNotIn("@@", content)

            self.assertIn(f"[Service]\n{self.credential_text}", content)


class TestBackupServiceSetup(_TestWithFakeDeviceAndFakeUserScope):
    credential_text = "-encrypted-password"
    credential_text_plain = f"SetCredentialEncrypted=borgmatic:{credential_text}"

    def __fake_check_output(self, *args, **kwargs):
        if "systemd-creds" in args[0]:
            return self.credential_text
        raise NotImplementedError(f"Unexpected args='{args}', kwargs='{kwargs}'.")

    def test_export_key_current_user(self):
        current_scope = UserScope(self.fake_current_user)
        device = BackupDevice(Path("/fake/path"), "fake-repo")
        current_backup_service = BackupServiceSetup(current_scope, device)
        credential = SystemdCredential(current_scope, "borgmatic")
        with mock.patch("subprocess.check_output") as mock_check_output:
            mock_check_output.side_effect = self.__fake_check_output
            credential.set_value("secret-password")
            self.assertEqual(credential.encrypted_plain, self.credential_text_plain)
        config = BackupConfig(current_scope, device, credential)
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.run") as mock_run,
        ):
            export_path = Path(tmp_dir) / "testdir"
            current_backup_service.export_key(config, credential, export_path)
            self.assertTrue(export_path.is_dir())
            mock_run.assert_called_once_with(
                [
                    "systemd-run",
                    "--user",
                    "-P",
                    "--wait",
                    "-p",
                    self.credential_text_plain,
                    "borgmatic",
                    "key",
                    "export",
                    "--paper",
                    "--config",
                    str(config.file_path()),
                    "--path",
                    str(
                        export_path
                        / f"{device.systemd_escaped}-{self.fake_current_user}-fake-repo.key"
                    ),
                ],
                check=True,
            )

    def test_export_key_other_user(self):
        other_scope = UserScope(self.fake_other_user)
        repo_name = "fake-repo"
        device = BackupDevice(Path("/fake/path"), repo_name)
        other_backup_service = BackupServiceSetup(other_scope, device)
        credential = SystemdCredential(other_scope, "borgmatic")
        with (
            mock.patch("subprocess.check_output") as mock_check_output,
            mock.patch("configure.i_am_root", return_value=True),
        ):
            mock_check_output.side_effect = self.__fake_check_output
            credential.set_value("secret-password")
            self.assertEqual(credential.encrypted_plain, self.credential_text_plain)
        config = BackupConfig(other_scope, device, credential)
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.run") as mock_run,
            mock.patch("configure.i_am_root", return_value=True),
            mock.patch("os.chown") as mock_chown,
            mock.patch("os.chmod") as mock_chmod,
        ):
            export_path = Path(tmp_dir) / "testdir"
            other_backup_service.export_key(config, credential, export_path)
            mock_chown.assert_called_once()
            mock_chmod.assert_called_once_with(path=export_path, mode=0o777)
            self.assertTrue(export_path.is_dir())
            mock_run.assert_called_once_with(
                [
                    "run0",
                    "-u",
                    self.fake_other_user,
                    "systemd-run",
                    "--user",
                    "-P",
                    "--wait",
                    "-p",
                    self.credential_text_plain,
                    "borgmatic",
                    "key",
                    "export",
                    "--paper",
                    "--config",
                    str(config.file_path()),
                    "--path",
                    str(
                        export_path
                        / f"{device.systemd_escaped}-{self.fake_other_user}-{repo_name}.key"
                    ),
                ],
                check=True,
            )

    def test_export_key_system(self):
        system_scope = SystemScope()
        repo_name = "fake-repo"
        device = BackupDevice(Path("/fake/path"), repo_name)
        current_backup_service = BackupServiceSetup(system_scope, device)
        credential = SystemdCredential(system_scope, "borgmatic")
        with (
            mock.patch("subprocess.check_output") as mock_check_output,
            mock.patch("configure.i_am_root", return_value=True),
        ):
            mock_check_output.side_effect = self.__fake_check_output
            credential.set_value("secret-password")
            self.assertEqual(credential.encrypted_plain, self.credential_text_plain)
        config = BackupConfig(system_scope, device, credential)
        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.run") as mock_run,
            mock.patch("configure.i_am_root", return_value=True),
            mock.patch("os.chown") as mock_chown,
            mock.patch("os.chmod") as mock_chmod,
        ):
            export_path = Path(tmp_dir) / "testdir"
            current_backup_service.export_key(config, credential, export_path)
            mock_chown.assert_called_once()
            mock_chmod.assert_called_once_with(path=export_path, mode=0o777)
            self.assertTrue(export_path.is_dir())
            mock_run.assert_called_once_with(
                [
                    "systemd-run",
                    "-P",
                    "--wait",
                    "-p",
                    self.credential_text_plain,
                    "borgmatic",
                    "key",
                    "export",
                    "--paper",
                    "--config",
                    str(config.file_path()),
                    "--path",
                    str(export_path / f"{device.systemd_escaped}-root-{repo_name}.key"),
                ],
                check=True,
            )

    # pylint: disable=too-many-locals
    def test_setup_current_user(self):
        current_scope = UserScope(self.fake_current_user)
        device = BackupDevice(Path("/fake/path"), "fake-repo")

        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.check_output") as mock_check_output,
            mock.patch("configure.prompt_password") as mock_prompt_password,
            mock.patch("configure.ask_user_confirmation") as mock_ask_user_confirmation,
            mock.patch("configure.i_am_root") as mock_i_am_root,
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
            mock.patch("subprocess.run") as mock_run,
        ):
            mock_check_output.side_effect = self.__fake_check_output
            mock_prompt_password.return_value = "pa55w0rd"
            mock_ask_user_confirmation.return_value = True
            mock_i_am_root.return_value = True

            current_backup_service = BackupServiceSetup(current_scope, device)
            current_backup_service.setup(key_path=Path(tmp_dir), notify_user="fake")

            mock_prompt_password.assert_called_once()
            mock_ask_user_confirmation.assert_not_called()
            self.assertEqual(mock_write_file.call_count, 4)
            install_dropin_args = mock_write_file.call_args_list[0].kwargs
            install_exclude_args = mock_write_file.call_args_list[1].kwargs
            install_config_args = mock_write_file.call_args_list[2].kwargs
            install_service_args = mock_write_file.call_args_list[3].kwargs
            self.assertEqual(
                install_dropin_args["path"],
                self.fake_current_home
                / ".config/systemd/user"
                / f"automatic-backup-{device.systemd_escaped}.service.d"
                / "credential.conf",
            )
            self.assertEqual(install_dropin_args["uid"], self.fake_current_uid)
            self.assertEqual(install_dropin_args["gid"], self.fake_current_gid)

            self.assertEqual(
                install_exclude_args["path"],
                self.fake_current_home
                / f".config/borgmatic/excludes-user-{device.systemd_escaped}",
            )
            self.assertEqual(install_exclude_args["uid"], self.fake_current_uid)
            self.assertEqual(install_exclude_args["gid"], self.fake_current_gid)
            config_path = (
                self.fake_current_home
                / f".config/borgmatic/borgmatic-config-{device.systemd_escaped}.yaml"
            )
            self.assertEqual(
                install_config_args["path"],
                config_path,
            )
            self.assertEqual(install_config_args["uid"], self.fake_current_uid)
            self.assertEqual(install_config_args["gid"], self.fake_current_gid)
            self.assertEqual(
                install_service_args["path"],
                self.fake_current_home
                / f".config/systemd/user/automatic-backup-{device.systemd_escaped}.service",
            )
            self.assertEqual(install_service_args["uid"], self.fake_current_uid)
            self.assertEqual(install_service_args["gid"], self.fake_current_gid)
            mock_run.assert_has_calls(
                [
                    mock.call(
                        [
                            "systemd-run",
                            "--user",
                            "-P",
                            "--wait",
                            "-p",
                            self.credential_text_plain,
                            "borgmatic",
                            "repo-create",
                            "--config",
                            str(config_path),
                        ],
                        check=True,
                    ),
                    mock.call(
                        [
                            "systemd-run",
                            "--user",
                            "-P",
                            "--wait",
                            "-p",
                            self.credential_text_plain,
                            "borgmatic",
                            "key",
                            "export",
                            "--paper",
                            "--config",
                            str(config_path),
                            "--path",
                            f"{tmp_dir}/{device.systemd_escaped}-fakecurrentuser-fake-repo.key",
                        ],
                        check=True,
                    ),
                    mock.call(
                        [
                            "systemctl",
                            "--user",
                            "enable",
                            f"automatic-backup-{device.systemd_escaped}.service",
                        ],
                        check=True,
                    ),
                ]
            )

    # pylint: disable=too-many-locals
    def test_setup_other_user(self):
        other_scope = UserScope(self.fake_other_user)
        device = BackupDevice(Path("/fake/path"), "fake-repo")

        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.check_output") as mock_check_output,
            mock.patch("configure.prompt_password") as mock_prompt_password,
            mock.patch("configure.ask_user_confirmation") as mock_ask_user_confirmation,
            mock.patch("configure.i_am_root") as mock_i_am_root,
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
            mock.patch("subprocess.run") as mock_run,
        ):
            mock_check_output.side_effect = self.__fake_check_output
            mock_prompt_password.return_value = "pa55w0rd"
            mock_ask_user_confirmation.return_value = True
            mock_i_am_root.return_value = True

            other_backup_service = BackupServiceSetup(other_scope, device)
            other_backup_service.setup(key_path=Path(tmp_dir), notify_user="fake")

            mock_prompt_password.assert_called_once()
            mock_ask_user_confirmation.assert_not_called()
            self.assertEqual(mock_write_file.call_count, 4)
            install_dropin_args = mock_write_file.call_args_list[0].kwargs
            install_exclude_args = mock_write_file.call_args_list[1].kwargs
            install_config_args = mock_write_file.call_args_list[2].kwargs
            install_service_args = mock_write_file.call_args_list[3].kwargs
            self.assertEqual(
                install_dropin_args["path"],
                self.fake_other_home
                / ".config/systemd/user"
                / f"automatic-backup-{device.systemd_escaped}.service.d"
                / "credential.conf",
            )
            self.assertEqual(install_dropin_args["uid"], self.fake_other_uid)
            self.assertEqual(install_dropin_args["gid"], self.fake_other_gid)

            self.assertEqual(
                install_exclude_args["path"],
                self.fake_other_home / f".config/borgmatic/excludes-user-{device.systemd_escaped}",
            )
            self.assertEqual(install_exclude_args["uid"], self.fake_other_uid)
            self.assertEqual(install_exclude_args["gid"], self.fake_other_gid)
            config_path = (
                self.fake_other_home
                / f".config/borgmatic/borgmatic-config-{device.systemd_escaped}.yaml"
            )
            self.assertEqual(
                install_config_args["path"],
                config_path,
            )
            self.assertEqual(install_config_args["uid"], self.fake_other_uid)
            self.assertEqual(install_config_args["gid"], self.fake_other_gid)
            self.assertEqual(
                install_service_args["path"],
                self.fake_other_home
                / f".config/systemd/user/automatic-backup-{device.systemd_escaped}.service",
            )
            self.assertEqual(install_service_args["uid"], self.fake_other_uid)
            self.assertEqual(install_service_args["gid"], self.fake_other_gid)
            mock_run.assert_has_calls(
                [
                    mock.call(
                        [
                            "run0",
                            "-u",
                            "fakeotheruser",
                            "systemd-run",
                            "--user",
                            "-P",
                            "--wait",
                            "-p",
                            self.credential_text_plain,
                            "borgmatic",
                            "repo-create",
                            "--config",
                            str(config_path),
                        ],
                        check=True,
                    ),
                    mock.call(
                        [
                            "run0",
                            "-u",
                            "fakeotheruser",
                            "systemd-run",
                            "--user",
                            "-P",
                            "--wait",
                            "-p",
                            self.credential_text_plain,
                            "borgmatic",
                            "key",
                            "export",
                            "--paper",
                            "--config",
                            str(config_path),
                            "--path",
                            f"{tmp_dir}/{device.systemd_escaped}-fakeotheruser-fake-repo.key",
                        ],
                        check=True,
                    ),
                    mock.call(
                        [
                            "run0",
                            "-u",
                            "fakeotheruser",
                            "systemctl",
                            "--user",
                            "enable",
                            f"automatic-backup-{device.systemd_escaped}.service",
                        ],
                        check=True,
                    ),
                ]
            )

    def test_setup_system(self):
        system_scope = SystemScope()
        device = BackupDevice(Path("/fake/path"), "fake-repo")

        with (
            TemporaryDirectory() as tmp_dir,
            mock.patch("subprocess.check_output") as mock_check_output,
            mock.patch("configure.prompt_password") as mock_prompt_password,
            mock.patch("configure.ask_user_confirmation") as mock_ask_user_confirmation,
            mock.patch("configure.i_am_root") as mock_i_am_root,
            mock.patch("configure.write_file") as mock_write_file,
            mock.patch("configure.create_dir"),
            mock.patch("subprocess.run") as mock_run,
        ):
            mock_check_output.side_effect = self.__fake_check_output
            mock_prompt_password.return_value = "pa55w0rd"
            mock_ask_user_confirmation.return_value = True
            mock_i_am_root.return_value = True

            system_backup_service = BackupServiceSetup(system_scope, device)
            system_backup_service.setup(key_path=Path(tmp_dir), notify_user="fake")

            mock_prompt_password.assert_called_once()
            mock_ask_user_confirmation.assert_not_called()
            self.assertEqual(mock_write_file.call_count, 4)
            install_dropin_args = mock_write_file.call_args_list[0].kwargs
            isntall_exclude_args = mock_write_file.call_args_list[1].kwargs
            install_config_args = mock_write_file.call_args_list[2].kwargs
            install_service_args = mock_write_file.call_args_list[3].kwargs
            self.assertEqual(
                install_dropin_args["path"],
                Path("/etc/systemd/system")
                / f"automatic-backup-{device.systemd_escaped}.service.d"
                / "credential.conf",
            )
            self.assertEqual(install_dropin_args["uid"], 0)
            self.assertEqual(install_dropin_args["gid"], 0)

            self.assertEqual(
                isntall_exclude_args["path"],
                Path("/etc") / f"borgmatic/excludes-system-{device.systemd_escaped}",
            )
            self.assertEqual(isntall_exclude_args["uid"], 0)
            self.assertEqual(isntall_exclude_args["gid"], 0)
            config_path = Path("/etc") / f"borgmatic/borgmatic-config-{device.systemd_escaped}.yaml"
            self.assertEqual(install_config_args["path"], config_path)
            self.assertEqual(install_config_args["uid"], 0)
            self.assertEqual(install_config_args["gid"], 0)
            self.assertEqual(
                install_service_args["path"],
                Path("/etc/systemd/system") / f"automatic-backup-{device.systemd_escaped}.service",
            )
            self.assertEqual(install_service_args["uid"], 0)
            self.assertEqual(install_service_args["gid"], 0)
            mock_run.assert_has_calls(
                [
                    mock.call(
                        [
                            "systemd-run",
                            "-P",
                            "--wait",
                            "-p",
                            self.credential_text_plain,
                            "borgmatic",
                            "repo-create",
                            "--config",
                            str(config_path),
                        ],
                        check=True,
                    ),
                    mock.call(
                        [
                            "systemd-run",
                            "-P",
                            "--wait",
                            "-p",
                            self.credential_text_plain,
                            "borgmatic",
                            "key",
                            "export",
                            "--paper",
                            "--config",
                            str(config_path),
                            "--path",
                            f"{tmp_dir}/{device.systemd_escaped}-root-fake-repo.key",
                        ],
                        check=True,
                    ),
                    mock.call(
                        [
                            "systemctl",
                            "enable",
                            f"automatic-backup-{device.systemd_escaped}.service",
                        ],
                        check=True,
                    ),
                ]
            )


if __name__ == "__main__":
    unittest.main()
