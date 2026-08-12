# Releasing `@voqalize/client-react`

One package, one tag, no long-lived credentials.
[`.github/workflows/release-react-sdk.yml`](../../.github/workflows/release-react-sdk.yml)
runs the full web CI gate, builds the package, typechecks the source against the
oldest peers we claim to support, publishes to
[npm](https://www.npmjs.com/package/@voqalize/client-react) and opens a GitHub
release.

The tag is package-prefixed. This repo holds two publishable SDKs — the Python
brain SDK and this one — and they do **not** version in lockstep, so
`react-sdk-v*` and `python-sdk-v*` are separate series.

## Cutting a release

```sh
# 1. bump sdk/react/package.json          "version": "0.0.2"
# 2. add a matching "## 0.0.2" section to sdk/react/CHANGELOG.md
# 3. commit, then
git tag react-sdk-v0.0.2
git push origin main --follow-tags
```

The guard job refuses the tag if it disagrees with `package.json` or if the
changelog has no section for it — both failures are cheap here and expensive on
npm, where a version number can never be reused.

If the publish fails after CI passed, fix the cause and re-run: **Actions →
release react sdk → Run workflow**, picking the *tag* as the ref.

## Versioning

The public series starts at `0.0.1`. The `0.1.0` that sat in `package.json`
before it was never published — the applications that used this SDK copied its
source into their own tree — and starting the npm history at the bottom says
plainly that nothing is promised yet. While the package is `0.0.x`, treat every
release as potentially breaking and let consumers pin narrowly.

**Peer ranges are the promise that matters most, and they are deliberately
wide.** A library that demands the newest React and the newest pipecat is one
its would-be consumers copy instead of install — which is exactly how this
package ended up with two divergent forks of itself before it ever shipped. The
declared floor is React 18.2, `@pipecat-ai/client-js` 1.7,
`@pipecat-ai/client-react` 1.1 and `@pipecat-ai/small-webrtc-transport` 1.10: the
oldest combination anything actually *runs*, not the oldest that happens to
compile. The client-js floor is 1.7 rather than 1.5 because the transport pins
it, not because this code needs it — every peer's own range is part of ours.
The release job typechecks the source
against exactly those versions, so the range is a checked claim rather than a
number someone typed. Raise the floor only when the code genuinely needs a newer
API, and say so in the changelog — every bump is a consumer who has to move
first.

## One-time setup

npm accepts a short-lived OIDC token that GitHub mints for *this repo running
this workflow*, which is strictly better than an automation token in `secrets`:
it cannot be copied out, cannot be used from a fork, and expires in minutes. It
also stamps the published package with build provenance, so anyone can verify the
tarball came from this commit.

### 1. GitHub environment

**Settings → Environments → New environment**, named exactly `npm`. Leave it
unprotected, or add a required reviewer if you want a human to approve every
publish. The name matters — npm pins its trust to it below.

### 2. npm trusted publisher

Unlike PyPI, npm has **no pending-publisher flow**: a trusted publisher is
configured in a package's settings, so the package has to exist before it can be
attached. That makes the *first* publish a manual one — once, ever — and every
publish after it the workflow's. Which is why the tagged series starts at
`0.0.2`: pushing `react-sdk-v0.0.1` after publishing `0.0.1` by hand would fail
on a version npm will not let anyone reuse.

1. Log in as `sripathi-voqalize` — the account that already owns
   [`@voqalize/avatar`](https://www.npmjs.com/package/@voqalize/avatar) — and
   confirm the `@voqalize` scope exists.
2. From `sdk/react/`, run the same checks the release job would, then publish
   `0.0.1` by hand. This one artifact has no provenance attestation, because
   nothing but a trusted publisher can produce one:

   ```sh
   pnpm install --ignore-workspace
   pnpm typecheck && pnpm build
   npm publish --access public
   ```

3. On npmjs.com: **@voqalize/client-react → Settings → Trusted publisher → GitHub
   Actions**, filled in exactly:
   - Organization or user: `voqalize`
   - Repository: `voqalize`
   - Workflow filename: `release-react-sdk.yml`
   - Environment: `npm`
4. Set **Publishing access** to *Require two-factor authentication or an
   automation token*. With a trusted publisher configured the workflow needs
   neither, and this stops anything else from publishing with a stray token.
5. From then on, tag and let the workflow publish. Repeat step 2 only if the
   trusted publisher is ever removed.

The publish job runs on Node 22 and upgrades npm before publishing: trusted
publishing needs Node >=22.14 and npm >=11.5.1, and the runner ships an older npm
even on Node 22.

### Fallback: a token

If trusted publishing is blocked, the publish step takes an automation token with
a two-line change. Prefer OIDC — a token in `secrets` outlives the person who
created it.

```yaml
# .github/workflows/release-react-sdk.yml, npm job
      - name: publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: npm publish --provenance --access public dist/*.tgz
```

`--provenance` is explicit here and absent above on purpose: a trusted publisher
attaches the attestation itself, a token does not.

## What ships

One tarball: `dist/` (ESM + CJS + types + sourcemaps), the README, the changelog
and the licence. Nothing else — `files` in `package.json` is an allowlist, so the
source, the tsconfig and the tests stay out.

React and pipecat are **peers, never bundled**. A copy of React inside this
package would hand the host application a second renderer, and hooks across the
two throw "invalid hook call" at runtime with nothing in the build to explain it.
The release job asserts it: if `dist/index.js` stops *importing* each peer, the
publish fails.
