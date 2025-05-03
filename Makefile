VERSION := $(shell awk '/^Version: / {print $$2}' automatic-backup.spec)
INSTALL ?= install -p
DESTDIR ?=
PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
LIBDIR ?= $(PREFIX)/lib
LIBRARY := $(LIBDIR)/automatic-backup
SRC := src
BUILD := build
ARTIFACTS := artifacts
TARBALLDIR := $(ARTIFACTS)/tarballs
PACKAGEDIR := $(ARTIFACTS)/packages
TARBALL := $(TARBALLDIR)/automatic-backup-$(VERSION).tar.xz

.PHONY: all build-rmp check clean distclean install uninstall $(TARBALL)

all:

clean:
	rm -rf $(BUILD)

distclean: clean
	rm -rf $(ARTIFACTS)

$(TARBALL): src automatic-backup.spec Makefile LICENSE README.md
	mkdir -p "$(TARBALLDIR)"
	tar cJf '$@' --exclude=__pycache__ --transform 's|^|automatic-backup-$(VERSION)/|' $^

check:
	black --line-length=100 --check --diff ./src/automatic-backup/*.py
	pylint --max-line-length=100 ./src/automatic-backup/*.py
	flake8 --max-line-length=100 ./src/automatic-backup/*.py

	cd src/automatic-backup && python -m unittest  > /dev/null

install:
# ensure directories exist
	$(INSTALL) -Dm 755 -d $(DESTDIR)$(LIBDIR)
	$(INSTALL) -Dm 755 -d $(DESTDIR)$(BINDIR)
# install configuration library
	$(INSTALL) -Dm 755 -d $(DESTDIR)$(LIBRARY)
# install configuration library, substitute version, preserve timestamp
	$(INSTALL) -Dm 755 $(SRC)/automatic-backup/configure.py $(DESTDIR)$(LIBRARY)/configure.py
	sed -e 's,@VERSION@,$(VERSION),' -i $(DESTDIR)$(LIBRARY)/configure.py
	touch -r $(SRC)/automatic-backup/configure.py $(DESTDIR)$(LIBRARY)/configure.py
# install configuration script, substitute library path, preserve timestamp
	$(INSTALL) -Dm 755 $(SRC)/scripts/configure-automatic-backup $(DESTDIR)$(BINDIR)/configure-automatic-backup
	sed -e 's,@LIBDIR@,$(LIBDIR),' -i $(DESTDIR)$(BINDIR)/configure-automatic-backup
	touch -r $(SRC)/scripts/configure-automatic-backup $(DESTDIR)$(BINDIR)/configure-automatic-backup
# install backup service template files
	$(INSTALL) -Dm 755 -d $(DESTDIR)$(LIBRARY)/templates
	$(INSTALL) -Dm 644 $(SRC)/automatic-backup/templates/* $(DESTDIR)$(LIBRARY)/templates
# install main backup script
	$(INSTALL) -Dm 755 $(SRC)/automatic-backup/automatic_backup.py $(DESTDIR)$(LIBRARY)/automatic_backup.py

# install notification service, substitute version, preserve timestamp
	$(INSTALL) -Dm 755 $(SRC)/automatic-backup/automatic_backup_notification.py $(DESTDIR)$(LIBRARY)/automatic_backup_notification.py
	sed -e 's,@VERSION@,$(VERSION),' -i $(DESTDIR)$(LIBRARY)/automatic_backup_notification.py
	touch -r $(SRC)/automatic-backup/automatic_backup_notification.py $(DESTDIR)$(LIBRARY)/automatic_backup_notification.py
# install notification varlink interface file
	$(INSTALL) -Dm 755 -d $(DESTDIR)$(LIBRARY)/varlink
	$(INSTALL) -Dm 644 $(SRC)/automatic-backup/varlink/*.varlink $(DESTDIR)$(LIBRARY)/varlink
# install notification varlink socket unit
	$(INSTALL) -Dm 644 $(SRC)/units/automatic-backup-notification-varlink.socket $(DESTDIR)$(LIBDIR)/systemd/user/automatic-backup-notification-varlink.socket
# install notification service unit, substitute library path, preserve timestamp
	$(INSTALL) -Dm 644 $(SRC)/units/automatic-backup-notification.service $(DESTDIR)$(LIBDIR)/systemd/user/automatic-backup-notification.service
	sed -e 's,@LIBDIR@,$(LIBDIR),' -i $(DESTDIR)$(LIBDIR)/systemd/user/automatic-backup-notification.service
	touch -r $(SRC)/units/automatic-backup-notification.service $(DESTDIR)$(LIBDIR)/systemd/user/automatic-backup-notification.service

uninstall:
	rm $(DESTDIR)$(BINDIR)/configure-automatic-backup

	rm $(DESTDIR)$(LIBRARY)/automatic_backup_notification.py
	rm $(DESTDIR)$(LIBRARY)/configure.py

	rm $(DESTDIR)$(LIBRARY)/varlink/*
	rmdir $(DESTDIR)$(LIBRARY)/varlink

	rm $(DESTDIR)$(LIBRARY)/templates/*
	rmdir $(DESTDIR)$(LIBRARY)/templates

	rmdir $(DESTDIR)$(LIBRARY)

	rm $(DESTDIR)$(LIBDIR)/systemd/user/automatic-backup-notification-varlink.socket
	rm $(DESTDIR)$(LIBDIR)/systemd/user/automatic-backup-notification.service

build-rpm: $(TARBALL)
	mkdir -p ~/rpmbuild/SOURCES
	cp "$(TARBALL)" ~/rpmbuild/SOURCES
	rpmbuild -bb automatic-backup.spec
	mkdir -p $(PACKAGEDIR)
	cp ~/rpmbuild/RPMS/**/automatic-backup-*.rpm $(PACKAGEDIR)/
