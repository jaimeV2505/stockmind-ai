# ADR-0003 Own numpy/pandas indicators, validated against TA-Lib in CI
Decision: implement indicators ourselves (TA-Lib needs native builds), document every convention, and add a CI job comparing
against TA-Lib. Status: own implementations + independent-reference tests done; TA-Lib cross-check NOT yet done (next-tasks #2).
