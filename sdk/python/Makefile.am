# The Python SDK: the package `debasher`, installed as a Python package
# under $(pkgpythondir) ($(pythondir)/debasher), importable without more
# when the prefix is that of the Python itself (a virtual environment, a
# conda environment) and through PYTHONPATH otherwise; and the tool
# debasher_build, which writes a program described with it.
pkgpython_PYTHON = debasher/__init__.py debasher/_paths.py	\
debasher/errors.py debasher/process.py debasher/program.py	\
debasher/layout.py debasher/build.py

# The directories of the installation, which the package needs to import
# the API of the web UI ($(pkgdatadir)/api) and to find the tools of the
# engine: written by make, never by hand (see debasher/_paths.py).
nodist_pkgpython_PYTHON = debasher/_install.py
BUILT_SOURCES = debasher/_install.py

bin_SCRIPTS = debasher_build

EXTRA_DIST = .gitignore debasher_build.sh

CLEANFILES = $(bin_SCRIPTS) debasher/_install.py

# Built again after a new configure, whose values they carry
debasher/_install.py: Makefile
	rm -f $@
	echo '"""The directories of this installation, written by make."""' > $@
	echo "PKGDATADIR = \"$(pkgdatadir)\"" >> $@
	echo "BINDIR = \"$(bindir)\"" >> $@
	echo "LIBEXECDIR = \"$(libexecdir)\"" >> $@
	echo "PYTHONDIR = \"$(pythondir)\"" >> $@

# The launcher of the tool, as api/Makefile.am builds debasher_webui: a
# Bash script with the directories of the installation in front, which
# chooses the Python to run the tool with (see debasher_build.sh).
debasher_build: debasher_build.sh Makefile
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "debasher_pkgdatadir=\"$(pkgdatadir)\"" >> $@
	echo "debasher_pythondir=\"$(pythondir)\"" >> $@
	echo "debasher_default_python=\"$(PYTHON)\"" >> $@
	cat $< >> $@
	chmod ugo+x $@

clean-local:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
