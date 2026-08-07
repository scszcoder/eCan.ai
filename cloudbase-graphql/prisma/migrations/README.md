# Prisma production migrations

Production must use committed, reviewed migrations and `prisma migrate deploy`.
Do not use `prisma db push` against staging or production.

Generate the initial PostgreSQL baseline with the Prisma version pinned in
`package.json`:

```bash
npm ci
npm run db:migration:baseline
```

This creates `prisma/migrations/00000000000000_baseline/migration.sql`. Review
the SQL before committing it. Subsequent changes must be created with
`prisma migrate dev --name <change>` and deployed with `npm run db:deploy`.
