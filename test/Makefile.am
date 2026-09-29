SUBDIRS = engine api

EXTRA_DIST = utils/README.md utils/crap_report.py utils/bash_complexity.py \
utils/hotspots.py

# CRAP report (utils/crap_report.py) of the Python code of the API and of
# the engine. It is not part of `make check`: it is a report rather than a
# test, and it runs both Python suites again under coverage. It runs with the
# Python next to PYTEST, that of the virtual environment of the API, which
# also has coverage and radon once api/requirements-dev.txt is installed.
.PHONY: crap
if HAVE_PYTEST
crap:
	py=`dirname "$(PYTEST)"`/python; \
	test -x "$$py" || py="$(PYTHON)"; \
	"$$py" $(srcdir)/utils/crap_report.py $(top_srcdir)/api $(srcdir)/api && \
	echo && \
	"$$py" $(srcdir)/utils/crap_report.py $(top_srcdir)/engine $(srcdir)/engine
else
crap:
	@echo "pytest not found: skipping the CRAP report"
endif

# Complexity of the Bash functions of the engine (utils/bash_complexity.py)
# and hotspots of the code (utils/hotspots.py): reports too, and static ones,
# so they need neither the tests nor the virtual environment of the API.
.PHONY: bash-complexity hotspots
bash-complexity:
	cd $(top_srcdir) && $(PYTHON) test/utils/bash_complexity.py

hotspots:
	cd $(top_srcdir) && $(PYTHON) test/utils/hotspots.py
