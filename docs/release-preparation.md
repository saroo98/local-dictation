# Privacy review and release preparation

Checked 2026-10-02. The owner requested meaningful commits and a public release,
then explicitly limited this phase to local commits while preparing a logo.
No push, tag, release or upload is authorized in this phase.

## Repository privacy review

The baseline scan covered all 170 tracked files, 345 distinct blobs reachable
from local branches, remote-tracking references and tags, and all reachable
commit metadata. It checked personal paths, owner identity, email addresses,
credential formats, private-key headers, credentials in URLs, credential
assignments and runtime/credential filenames. All three unique tracked images
in that history were inspected; no personal content or EXIF/text metadata was
found in those images. Pattern matches require manual review and are not a
guarantee that every possible secret can be recognized.

Confirmed findings:

- Personal machine paths were present in tests, browser fixtures, documentation
  and audit evidence. Current files now use synthetic fixture paths, portable
  installation paths and relative repository links.
- Audit records included unnecessary process/window identities, unrelated
  foreground diagnostics and personal file sizes/timestamps. Public records
  now omit these details and identify their redactions. Original records remain
  only in ignored local build output, outside publishable source.
- Private chat names and original screenshot/archive locations were removed
  from public notes. Application data defaults remain documented accurately.
- Existing Git author/committer metadata contains a personal email address.
  New commits use the repository owner's verified public GitHub identity and
  GitHub noreply address.
- The scan found no credential-format or credential-assignment matches and no
  tracked runtime settings, transcript history, logs, exports or private-key
  files. Remaining email matches in file contents are a synthetic `example.com`
  test address and public security-advisory mailing-list links.

Comparison against local transcript history also found no transcript text
matches in current files or reachable historical blobs. Personal transcript
text and the raw scan results are not included in this public report.

`.gitignore` also excludes local credentials, signing keys, model downloads,
exports and private agent metadata. Ignore rules protect future staging; they
do not erase data from earlier commits or provide an automatic secret detector.

## Historical privacy gate

**Publication remains blocked on historical cleanup.** Earlier commits retain
the original personal paths and author email. The public remote already
contains personal paths in historical `test_bubble_dictate.py` versions and the
same author email. A normal new commit or fast-forward push cannot remove them.
Do not publish the current branch history as private-free.

The smallest complete remedy is:

1. Preserve and verify a private backup of the complete current Git history
   outside the public checkout.
2. Sanitize the confirmed private content in every affected historical file
   version and replace personal author/committer metadata with the public
   GitHub identity. Preserve commit messages, ordering and meaningful changes.
3. Scan every object reachable from the resulting publication branch and
   compare its final tree with the reviewed source. Keep backup refs and raw
   audit records out of the published history.
4. Obtain explicit owner approval before replacing existing GitHub history.
   This changes existing commit IDs and requires a remote history replacement,
   beyond the current permission to make local commits.

No history rewrite or remote replacement has been performed in this phase.

## Validation of the current cleanup

The affected Python test files passed 123 tests; the affected bridge/model
frontend tests passed 12 tests. TypeScript and ESLint passed. All 229 checked
local Markdown links and all 22 JSON evidence files passed validation. Review
of the 15 redacted JSON records confirmed that 875 retained evidence values,
including outcomes, artifact identities and measurements, stayed unchanged.
This validates synthetic fixture and documentation changes, not new interactive
dictation or installer behavior. Full app checks from the earlier implementation
remain in [verification.md](verification.md).

## Installer release gates

- Receive and integrate the owner's logo, including native/tray/installer icons.
- Resolve the historical privacy gate above before any source push.
- Rebuild the final Windows installer from the reviewed source and verify its
  contents and checksums. Publish only the intended installer and checksum,
  never local profiles, raw audit backups, model caches or development output.
- Repeat relevant native acceptance after the final build. Keep physical
  interaction and clean-machine checks visibly unverified until exercised.
- Review release text, version, download links and licensing. The public
  repository currently has no declared license; do not invent one.
- Push, tag and publish only after the owner's hold is lifted and any required
  history-replacement authorization is explicit.

The README describes version 0.1.1 and points to the canonical GitHub releases
page. At this check the public repository had no published releases or tags.
No downloadable installer release is claimed before publication.
