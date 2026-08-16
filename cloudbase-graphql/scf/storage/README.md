# COS file storage

`reqFileOp` supports signed upload/download URLs plus server-side list/delete.
Every key is rewritten below `users/<sha256(owner)>/`; clients cannot select a
different owner or use absolute/parent paths.

Required environment variables:

- `COS_BUCKET`: full `bucket-name-APPID` value.
- `COS_REGION`: for example `ap-shanghai`.

Production should use an SCF execution role. Grant only the required COS
actions (`GetObject`, `PutObject`, `DeleteObject`, and `GetBucket`) on the one
runtime bucket. Do not place permanent secret keys in the deployed package or
frontend configuration. Configure bucket CORS to allow the CN application
origins, `PUT`/`GET`, and only the request headers the application uses.

The compatibility response remains a JSON string because Intl AppSync exposes
the field as `AWSJSON`.

## Prompt snapshots

Prompt create/update keeps PostgreSQL as the authoritative current state and
writes a JSON snapshot to native COS after a successful database mutation.
The default target is the environment's `COS_BUCKET` under:

`ecan-prompts/<owner>/<prompt-id>.json`

Set `PROMPTS_COS_BUCKET` to a full physical COS bucket name (including APPID),
`PROMPTS_COS_REGION`, or `PROMPTS_COS_PREFIX` to override the defaults. The
CloudBase PostgreSQL Storage bucket named `ecan-prompts` is a different storage
API and does not expose native COS object version IDs.

Enable versioning on the physical COS bucket to retain each overwrite as a new
version. When COS returns no `VersionId` because bucket versioning is disabled,
the handler also writes an immutable fallback object under
`ecan-prompts/<owner>/<prompt-id>/versions/<updated-at>.json`. Snapshot writes
are best-effort, matching the AWS prompt handler: a COS failure is logged but
does not roll back a successful PostgreSQL mutation. Prompt deletion removes
the database row only, preserving COS version history.
