# docs background behavior

Document/category model saves normalize slugs/order and reject category cycles. Asset validation happens before persistence.

There is no Celery lifecycle owned by this app. Public reads are ordinary HTTP requests over published-only querysets; asset serving is a security-sensitive media path.

## Tests as contracts

test_ordering.py protects deterministic document/category ordering. test_public_assets.py protects publication/capability and asset-serving rules.
