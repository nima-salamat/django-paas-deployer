# Documentation subsystem

Documentation is Markdown-first. The database stores Markdown source as plain text; the React application renders a restricted, HTML-escaped subset of Markdown. Admins edit on the left and see live preview on the right.

## Information architecture

`DocumentCategory` is a self-referencing tree. A category can have any number of children, so navigation can be organized as `Django -> Tutorials -> Deployment` without flattening the hierarchy. Documents belong to a category.

## Assets

`DocumentAsset` is a server-managed library for images, video, audio and generic files. Admin upload/list/reassign/delete operations are authenticated with `docs.manage`. Draft-only and unattached assets are private; assets attached to published documents are served from the public `/api/docs/assets/<uuid>/` resource URL. The authenticated admin preview endpoint is `/api/docs/admin/assets/<uuid>/` and is used for draft/library previews.

The public asset endpoint is read-only from the public perspective: its GET path never requires a JWT, while PATCH/DELETE on the same resource remain protected. Asset IDs are UUIDs and files are stored under the dedicated `docs/assets/` upload path, so the public route cannot be used as a generic file browser.

## Security

Raw HTML is not part of the Markdown authoring model. URLs are restricted to `https://`, `http://` and internal paths. Generic files are downloaded rather than interpreted as HTML. Frontend preview uses escaped Markdown, not `dangerouslySetInnerHTML` from user-authored raw HTML.

## Editor helper

The React `MarkdownEditor` provides a VS Code-style helper with snippets for headings, emphasis, links, images, code fences, lists, quotes, files, audio and video. The asset picker searches the already uploaded library and can insert a ready-to-use Markdown reference.
