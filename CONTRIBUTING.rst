============
Contributing
============

* Keep the package standard-library only (``dependencies = []``).
* One public callable per private module; re-export it from the
  subpackage's ``__init__.pyi`` stub (loaded lazily).
* CLIs live in ``module.py``; implementations in ``_module.py``.
* Run ``./style.sh``, ``./lint.sh`` and ``python3 -m pytest`` before a PR.
  Tests marked ``heavy`` need Avida (or a cluster) and skip otherwise.
  CI also runs ``./tidy/test_tidy.sh``, which needs a clean checkout.
* Dev requirements are pinned per Python in ``requirements-dev/``; after
  changing ``pyproject.toml``'s extras, run
  ``requirements-dev/regenerate.sh``.
