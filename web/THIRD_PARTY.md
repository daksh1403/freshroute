# Runtime attribution

FreshRoute's hosted build includes Pyodide 314.0.7 (Mozilla Public License 2.0), CPython (Python Software Foundation License), NumPy 2.4.6 (BSD-3-Clause), SciPy 1.18.0 (BSD-3-Clause, including HiGHS under MIT), openpyxl 3.1.5 (MIT), and et_xmlfile 2.0.0 (MIT).

Original sources and licensing:

- https://github.com/pyodide/pyodide
- https://github.com/python/cpython
- https://github.com/numpy/numpy
- https://github.com/scipy/scipy
- https://github.com/ERGO-Code/HiGHS
- https://foss.heptapod.net/openpyxl/openpyxl
- https://foss.heptapod.net/openpyxl/et_xmlfile

The NumPy/SciPy wheel artifacts retain their distribution license metadata. FreshRoute does not modify these libraries. Pyodide source corresponding to the pinned runtime is available at the upstream repository's release tags. The build script copies the same pinned runtime from the npm package and verifies package wheel SHA-256 hashes against its lockfile.
