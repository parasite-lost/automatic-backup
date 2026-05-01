Name:          automatic-backup
Version:       0.4.3
Release:       %autorelease
Summary:       Run automatic backups
Vendor:        parasite-lost

License:       Unlicensed
URL:           https://github.com/parasite-lost/automatic-backup
Source0:       %{name}-%{version}.tar.xz

BuildArch:     noarch

BuildRequires: black
BuildRequires: make
BuildRequires: pylint
BuildRequires: python3
BuildRequires: python3-flake8
BuildRequires: python3-varlink
BuildRequires: systemd

Requires: borgmatic
Requires: python3
Requires: python3-varlink
Requires: systemd

%description
Configure encrypted backup to run automatically via systemd units when a given
filesystem is mounted.

%prep
%autosetup


%build
rm -rf %{buildroot}
%make_build


%check
make check


%install
%make_install PREFIX=%{_prefix}


%files
%license LICENSE
%doc README.md
%dir %{_libdir}/%{name}
%{_bindir}/*
%{_libdir}/%{name}/*
%{_userunitdir}/*


%changelog
%autochangelog
