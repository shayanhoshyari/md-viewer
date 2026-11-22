"""Which files md-viewer shows, walks and treats as text, shared by the views and the commands."""

# Dot folders that are shown in the file tree and walked by `notes` and `links`; other dot folders are not.
KEPT_DOT_FOLDERS = {".claude", ".agents"}
# Names hidden from the file tree and directory listings.
EXCLUDE = {".DS_Store", ".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules"}
# File names and types the file tree lists.
TREE_FILE_NAMES = {"Makefile"}
TREE_FILE_EXTS = {".cjs", ".js", ".json", ".jsx", ".md", ".mjs", ".py", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
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
