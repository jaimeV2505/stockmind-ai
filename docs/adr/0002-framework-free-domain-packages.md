# ADR-0002 Framework-free domain packages under services/
Decision: quantitative and market-data logic is plain Python (numpy/pandas/dataclasses), no FastAPI/SQLAlchemy imports.
Rationale: testability, reuse by API and workers, no hidden I/O in math. 
