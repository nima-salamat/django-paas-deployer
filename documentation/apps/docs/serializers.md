# docs serializers

## CategorySerializer

Exposes id/name/slug/parent/parent_id/description/icon/order. slug may be omitted/blank because the model generates it. parent_id is derived read-only.

## DocumentSerializer

Exposes title/slug/description/category/category_name/icon/order/status/content and read-only timestamps/publication time plus nested read-only assets. content must be a string of Markdown no larger than 500 KB.

## DocumentCreateSerializer

Shares DocumentSerializer validation/fields through inheritance and is used where explicit create semantics are needed.

## DocumentAssetSerializer

Exposes id/document/status/name/alt/kind/mime_type/size/url/timestamps. kind/mime_type/size are read-only metadata derived from the uploaded file. url is derived from the UUID asset endpoint.

## Sensitive/validation contract

Serializers validate content size and shape, but publication permissions, category-cycle checks and file security remain in the API/model layer. Public serialization must not expose unpublished documents because the public queryset is already filtered.

Source: src/docs/serializers.py and apis.py.
