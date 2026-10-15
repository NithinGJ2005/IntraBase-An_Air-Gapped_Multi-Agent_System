# Database Integration Guide

## Prerequisites from IT

Before configuring production, IT must identify the database engine, approved SQLAlchemy driver, TLS/CA policy, read-only service account, network route, schema/data ownership, row-level policy, query timeout enforcement, and approved query catalog.

This project does not assume PostgreSQL, MySQL, SQL Server, or another engine. Set `DATABASE_URL` only after those decisions are made and add the corresponding driver to the approved internal package bundle.

## Safety model

The application executes only code-reviewed `QueryDefinition` entries. Every entry is a static `SELECT`, has a stable identifier, uses a Pydantic parameter schema, and requires `database:read`. There is no endpoint or tool for raw SQL, schema discovery, or write operations.

The database account must itself be read-only and least-privileged; application logic is not a replacement for database permissions. Add database-native statement timeout and row-level security policies during engine onboarding. The application additionally passes a timeout execution option, caps returned rows, and audits each decision by query ID.

`SAMPLE_QUERY_CATALOG` is synthetic and must never be pointed at production data without review.
