"""Which files md-viewer treats as binary or as text."""

# File types served as files, never as text.
BINARY_EXTS = {".gif", ".ico", ".jpeg", ".jpg", ".pdf", ".png", ".svg", ".webp"}
# File types shown as source text.
SOURCE_EXTS = {
    ".cjs",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".pyi",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
