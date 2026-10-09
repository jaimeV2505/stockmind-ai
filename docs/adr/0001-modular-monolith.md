# ADR-0001 Modular monolith + separate workers
Decision: one FastAPI service with domain modules, plus independently scalable workers. Rationale: low ops cost now,
clear seams for later extraction. Consequence: strict module boundaries enforced by package layout/imports.
