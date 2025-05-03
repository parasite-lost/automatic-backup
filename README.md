# Configure Automatic Backup Triggered By Filesystem Mount

Purpose: Configure systemd services to always run a backup script when a
specific partition is mounted, identified by mount path and verified filesystem
UUID (to avoid running the service when a different partition is mounted to the
same path).

Usage example: automatically run a backup when attaching your external backup disk.

## Preparation

Make sure the target filesystem, e.g. a partition on an external disk, will be
mounted consistently to the same mount point (e.g. to `/run/media/$USER/FS_LABEL`).
GNU/Linux desktop environments typically automount most filesystems to a
consistent mount point; exception: ext4 filesystems may need to be mounted
manually (the configuration script provided here can remedy this if desired).

## Configuration

Run `configure-automatic-backup --path FOLDER --repo REPO-NAME` - where `FOLDER`
should be the path to the backup filesystem mount point and `REPO-NAME` should
be a name for the repository (do not use `/`).

The script will print information and ask for confirmation before installing.
Note that the given path needs to exist and will always be provided to the
backup script by the configured systemd service when triggered to check if it
is present.

Additional options:
* `--info` only print some information, do not install
* `--dry-run` print what the installation would do, do not install
* `--system` install a system service intended to backup the root
             filesystem (requires root privileges)
* `--user USER` install a user service for user `USER` (requires root privileges
                if different user)
* `--notify USER` installed services will send desktop notifications to the user
                  `USER`
* `--key-path FOLDER` folder where to store exported repo keys (keep them
                      safe!). Default: `borg-keys` folder in the current working
                      directory.

The script will install:
* `automatic-backup-SYSTEMD-MOUNT-UNIT.service` and an accompanying
  `credential.conf` dropin file containing the backup password as systemd
  credential: systemd service that triggers when `SYSTEMD-MOUNT-UNIT.mount` is
  activated (the corresponding systemd mount unit for your selected backup file
  system)
* (optional) `/etc/udev/rules.d/65-ext4-automount-UUID.rules`: automount rule
  for ext4 filesystem with `UUID` of the selected backup filesystem (note: by
  default ext4 will not be automounted). This can be skipped if you want to
  manage this by yourself or do not want automounting.
* `borgmatic-config.yaml` and `excludes-system`/`excludes-user` with suitable
  default settings either to `/etc/borgmatic/` or `$HOME/.config/borgmatic/`
* repo keys will be exported (see `--key-path` option).

### Example:

* mount external disk filesystem to `/run/media/myuser/backupdisk`
* run the following to install a system (`/` filesystem) backup and a user backup (`/home/myuser`)

```
sudo configure-automatic-backup --path /run/media/myuser/backupdisk --repo myhostname --user myuser --system --notify myuser --key-path /home/myuser/borg-keys
```
