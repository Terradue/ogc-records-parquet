# Develop and build documentation

Run these commands from the repository root with Hatch installed.

## Run the quality gates

```bash
hatch run dev:format-check
hatch run dev:lint-check
hatch run dev:typecheck
hatch run dev:security
hatch run test:test
```

`hatch run dev:quality` groups the four static checks.
`hatch run dev:check` also runs tests in the development environment;
`hatch run test:test` runs the configured Python matrix.

For packaging:

```bash
hatch build
```

The source distribution includes the documentation and MkDocs configuration.
The wheel contains the library and license notices.

## Preview the documentation

```bash
hatch run docs:serve
```

Open the local URL printed by MkDocs, normally `http://127.0.0.1:8000/`.
The dedicated Hatch environment installs MkDocs and the mkdocstrings Python
handler without installing the library. The handler reads signatures and
Google-style docstrings directly from `src/`.

## Build and validate

```bash
hatch run docs:build
```

The build writes to `site/`, which is ignored by Git. Strict mode makes
warnings fail the build, including configured checks for missing local links
and anchors. It does not check the availability of external websites or execute
Python examples.

To use another output directory:

```bash
hatch run docs:build --site-dir /tmp/ogc-records-docs
```

The build creates static files. Hosting and deployment are separate steps.

## Choose the right section

Follow [Diátaxis](https://diataxis.fr/) when adding content:

- **Tutorials:** guided learning with a small, reproducible result and observable
  checkpoints.
- **How-to guides:** steps to accomplish a specific task for an existing user.
- **Reference:** signatures, defaults, types, format rules, and failure conditions.
- **Explanation:** rationale, trade-offs, and relationships between concepts.

Add each page to `mkdocs.yaml`, use relative links between documentation pages,
and check examples against the public API. Keep the README as an entry point;
put detailed contracts in reference pages. Changes to public signatures or
storage behavior must update the source docstrings and relevant storage
reference pages. The Python API page renders the public exports automatically.
