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
