# Releasing

Halo ships **four packages on one shared version**:

| Registry | Package |
|---|---|
| npm | `@halo-format/halo`, `@halo-format/claude` |
| PyPI | `halo-format`, `halo-format-claude` |

Releases are driven by [Changesets](https://github.com/changesets/changesets) and published from
GitHub Actions with **OIDC trusted publishing** — there are no npm or PyPI tokens stored in the repo.
The two npm packages are locked together with Changesets `fixed`; the two Python packages are synced
to the same version by [`ts/scripts/sync-python-version.mjs`](ts/scripts/sync-python-version.mjs).

## Day-to-day: how to ship a change

1. **Add a changeset** with your PR. From the TypeScript workspace:

   ```bash
   cd ts
   pnpm changeset
   ```

   Pick a bump level (patch / minor / major) and write a one-line summary. Because the packages share
   a version, selecting either npm package bumps all four together — a Python-only change still warrants
   a changeset. Commit the generated `ts/.changeset/*.md` file with your PR.

2. **Merge your PR to `main`.** The [Release workflow](.github/workflows/release.yml) sees the pending
   changeset and opens (or updates) a **"release: version packages"** PR that bumps every package's
   version, syncs the Python `pyproject.toml` files, and writes `CHANGELOG.md` entries.

3. **Merge the "release: version packages" PR.** That second merge triggers the workflow again, which
   now **publishes** to npm and PyPI, creates the git tags, and creates the GitHub releases.

So a release is "tag + publish on merge to `main`" — specifically, on the merge of the version PR.

## One-time setup (required before the first release)

These are configured outside the repo and only need doing once.

### 1. GitHub repository settings

- **Settings → Actions → General → Workflow permissions:** enable
  **"Allow GitHub Actions to create and approve pull requests"** (so the workflow can open the version PR).
- **Settings → Environments:** create an environment named **`release`**. (The release job runs in it;
  the trusted-publisher configs below reference it. Add required-reviewer protection here if you want a
  manual gate before publish.)

### 2. npm trusted publishers

For **each** npm package (`@halo-format/halo` and `@halo-format/claude`), on npmjs.com →
the package → **Settings → Trusted Publisher → GitHub Actions**, set:

| Field | Value |
|---|---|
| Organization / user | `halo-format` |
| Repository | `halo` |
| Workflow filename | `release.yml` |
| Environment | `release` |

> **First publish of a brand-new package name.** npm trusted publishing attaches to an existing
> package. If the very first publish fails because the package does not exist yet, do a one-time manual
> bootstrap with a short-lived [granular access token](https://docs.npmjs.com/creating-and-viewing-access-tokens)
> — `cd ts && pnpm -r build && pnpm --filter @halo-format/halo --filter @halo-format/claude publish --access public`
> — then configure the trusted publisher above and let CI take over from then on.

The workflow already sets `id-token: write`, updates npm to ≥ 11.5.1, and each `package.json` has
`publishConfig.provenance: true` and a `repository` field, so publishes are signed with provenance.

### 3. PyPI trusted publishers

PyPI supports **pending publishers**, so you can configure these *before* the projects exist and the
first OIDC publish will create them. On pypi.org → **Account → Publishing → Add a pending publisher**,
add one for **each** project (`halo-format` and `halo-format-claude`):

| Field | Value |
|---|---|
| PyPI project name | `halo-format` / `halo-format-claude` |
| Owner | `halo-format` |
| Repository name | `halo` |
| Workflow name | `release.yml` |
| Environment name | `release` |

## How the versions stay in lockstep

- `ts/.changeset/config.json` has `fixed: [["@halo-format/halo", "@halo-format/claude"]]`, so the two
  npm packages always take the same version.
- The `version` script (`changeset version && node scripts/sync-python-version.mjs && pnpm install
  --lockfile-only`) copies that version into both `pyproject.toml` files, so the version PR bumps all
  four together.
- The release workflow **re-runs the sync** right before building the Python distributions, so the
  published sdist/wheel always carry the correct version even if the version PR's `pyproject.toml` edit
  (which lives outside the Changesets working directory) was not committed.

## Notes & troubleshooting

- **`@halo-format/conformance`** is the test harness and is `private: true`, so it is never published —
  Changesets only version-bumps it internally.
- **`@halo-format/claude` depends on `@halo-format/halo` via `workspace:*`.** `changeset publish`
  replaces the workspace protocol with the real version at publish time. After the first release, sanity
  check that the published `@halo-format/claude` lists a real `@halo-format/halo` version (not
  `workspace:*`).
- **`dist/` is git-ignored**, so the release job builds (`pnpm -r build`) before publishing.
- To preview what the next release will bump without changing anything: `cd ts && pnpm changeset status`.
