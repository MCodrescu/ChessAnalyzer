# General Development Instructions

## Scope and project context

- Apply these defaults across languages and frameworks. Follow explicit task requirements and more specific repository instructions when they differ from these defaults.
- Before making changes, read relevant project documentation, configuration, implementation, and tests. Follow established architecture, naming, formatting, and tooling conventions.
- Do not assume commands, APIs, dependencies, or environment capabilities exist; verify them from the project or authoritative documentation.
- Ask for clarification when ambiguity materially affects correctness, security, compatibility, or scope. Otherwise, proceed with a reasonable assumption and state it when relevant.

## Design and readability

- Prefer the simplest correct solution. Avoid speculative features, premature optimization, unnecessary abstractions, and unrelated refactoring.
- Use descriptive, consistent names that make intent clear. Keep functions, methods, and modules focused on a single responsibility.
- Build cohesive components with explicit interfaces and dependencies. Separate business logic from infrastructure and external I/O when this improves testability and clarity.
- Prefer object-oriented design when it meaningfully encapsulates state or behavior; use simple functions or other idiomatic patterns when they are clearer. Favor composition over deep inheritance.
- Reuse existing project functionality before introducing duplicate code or dependencies. Do not force an abstraction for superficially similar code with different responsibilities.
- Preserve public interfaces and existing behavior unless the task requires a change. Explain unavoidable breaking changes and any migration steps.

## Documentation

- Document new or changed public APIs and non-obvious internal behavior using the language's standard documentation format and the project's conventions.
- For functions and methods that need documentation, include a brief purpose, arguments, return values, and relevant errors or side effects. Omit sections that do not apply and avoid restating obvious signatures.
- Use comments to explain intent, constraints, and trade-offs rather than narrating the code. Keep documentation accurate as behavior changes.
- Update relevant usage examples, configuration guidance, and project documentation when behavior or setup changes.

## Correctness and security

- Handle relevant edge cases and failures explicitly. Use meaningful errors; do not silently swallow failures or expose sensitive information in messages or logs.
- Validate untrusted input at system boundaries. Use safe, idiomatic APIs for database queries, process execution, file access, and serialization.
- Never hardcode or commit credentials, tokens, or other secrets. Use the project's configuration or secret-management mechanism.
- Keep changes narrowly scoped. Preserve user changes, and do not perform destructive operations, unrelated cleanup, commits, or pushes unless requested.

## Dependencies and API usage

- Prefer the standard library and existing dependencies when they meet the requirements. Add a maintained dependency only when it provides a clear benefit over a straightforward implementation.
- Consult current official documentation when introducing or changing library usage, especially for unfamiliar or version-sensitive APIs. Match the documentation to the project's supported or installed version, not blindly to the newest release.
- Avoid introducing deprecated APIs. When replacing existing deprecated usage, keep the change relevant to the task and verify compatibility.
- Use the project's package manager and update dependency manifests and lockfiles together when applicable. Avoid unrelated dependency upgrades.

## Testing and validation

- Add or update automated tests for new behavior and bug fixes. Cover the affected behavior, meaningful edge cases, and failure paths; add a regression test for a bug when practical.
- Prefer deterministic, isolated tests that verify observable behavior rather than implementation details. Use the existing test framework and conventions.
- Run relevant tests and the project's configured formatters, linters, type checks, and builds as appropriate. Start with focused checks and expand validation according to the change's impact.
- For Python, follow PEP 8 and use Ruff for linting and formatting unless the repository specifies different tooling. Respect project configuration rather than imposing conflicting defaults.
- Do not weaken tests, disable checks, or broadly suppress diagnostics just to make validation pass. Keep necessary exceptions narrow and explain why they are needed.
- If failures appear pre-existing or unrelated to the change, do not attempt to fix them unless requested; verify they fail on the unchanged baseline when practical and report them separately in the summary.
- For documentation-only changes, check accuracy, structure, and any configured documentation checks; do not run unrelated application tests.
- Report what was validated and the outcome. If a check cannot be run, state the limitation and what remains unverified; never claim unexecuted checks passed.
- If a required tool, dependency, or network resource is unavailable, do not install global tooling or modify the environment outside the project without asking; proceed with the remaining checks and report the gap.

## Delivery

- Review the final changes for correctness, scope, readability, and unintended modifications.
- Summarize the changes, validation results, and any remaining risks or follow-up work concisely.
