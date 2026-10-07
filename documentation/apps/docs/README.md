# docs

## Purpose

docs is the product documentation content/API domain. It stores product documents, categories and assets that the running application serves.

## Why this boundary exists

Product documentation has publication, ordering and media-security lifecycles. Those are application data and are deliberately separate from engineering architecture memory in root documentation/.

## Responsibilities

DocumentCategory hierarchy; Document publication/order; DocumentAsset validation and serving; public docs API; admin document/category/asset API.

## Non-responsibilities

Engineering architecture notes live in documentation/. Wagtail admin framework integration belongs to cms.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [serializers.md](serializers.md)
- [background.md](background.md)
- [tests.md](tests.md)

## Security

Public reads are published-only. Admin mutation uses docs.manage policy. Assets are size/MIME/image validated; capability URLs and publication state determine public exposure.

## Invariants

1. Markdown content is application data; repository documentation is separate.
2. Category trees cannot form cycles.
3. Published state controls public visibility.
4. Invalid bearer headers must not break intentionally public reads.

## Reading order

models.md -> api.md -> serializers.md -> tests.md.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)

## Detailed contracts

- [Detailed API reference](api-reference.md)
