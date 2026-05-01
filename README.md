# Configure Automatic Backup Triggered By Filesystem Mount

Purpose: Configure systemd services to always run a backup script when a
specific partition is mounted, identified by mount path and verified filesystem
UUID (to avoid running the service when a different partition is mounted to the
same path).

Usage example: automatically run a backup when attaching your external backup disk.

## Preparation (automatic mounting)

Make sure the target filesystem, e.g. a partition on an external disk, is
mounted, e.g. to `/run/media/$USER/BACKUP_DISK`.
GNU/Linux desktop environments typically mount external filesystems to such a
consistent mount points using udisks.

To ensure that automatic mounting works you can run (requires root privileges)
the following command to create a suitable udev rule letting udisks automount
the selected filesystem.

```
sudo configure-automatic-backup setup-automount --path /path/to/my/filesystem
```

Options:

- `--dry-run`: print what the script would do (no changes to system)
- `--shared`: for multi-user setups, mount point will be accessible to all users

## Backup Configuration

To configure automatic backup run the following command where `FOLDER` is the
location where the backup repositories should be placed and `REPO-NAME` is a
suffix appended to each backup for easier reference:

```
configure-automatic-backup setup-backup --path FOLDER --repo REPO-NAME --user $USER
```

Additional options:
* `--info` only print some information, do not install
* `--dry-run` print what the installation would do, do not install
* `--system` install a system service intended to backup the root
             filesystem (requires root privileges)
* `--user USER` install a user service for user `USER` (requires root privileges
                if different user)
* `--notify USER` installed services will send desktop notifications to the user
                  `USER`
* `--shared` reconfigure backup target partition as a shared mount (required for
             accessibility for multiple users)
* `--key-path FOLDER` folder where to store exported repo keys (keep them
                      safe!). Default: `borg-keys` folder in the current working
                      directory.

The script will print information and ask for confirmation and backup passwords
before installing. Note that the given path needs to exist and will always be
provided to the backup script by the configured systemd service when triggered
to check if it is present.

The script will install:
* `automatic-backup-SYSTEMD-MOUNT-UNIT.service` and an accompanying
  `credential.conf` dropin file containing the backup password as systemd
  credential: systemd service that triggers when `SYSTEMD-MOUNT-UNIT.mount` is
  activated (the corresponding systemd mount unit for your selected backup
  filesystem)
* `borgmatic-config.yaml` and `excludes-system`/`excludes-user` with suitable
  default settings either to `/etc/borgmatic/` or `$HOME/.config/borgmatic/`
  Note: instead of relying on the excludes file you can use `.nobackup` files in
  folders that you do not wish to backup.
* repo keys will be exported (see `--key-path` option) for convenience.

## Example:

* have external disk filesystem mounted to `/run/media/$USER/BACKUP_DISK`
* run the following to install a system (`/` filesystem) backup and a user backup (`/home/$USER`)

```
sudo configure-automatic-backup setup-backup \
  --path /run/media/$USER/BACKUP_DISK \
  --repo mybackup \
  --user $USER \
  --system \
  --notify $USER \
  --key-path /home/$USER/borg-keys
```
