#!/usr/bin/env python3
"""Generate Morphe's source descriptor from an uploaded, verified release asset."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile


def build_metadata(release, bundle, repository, version, patch_list):
    expected_release_prefix = f"https://github.com/{repository}/releases/tag/"
    if not release["html_url"].startswith(expected_release_prefix):
        raise ValueError("Release does not belong to this repository")
    if release["draft"] or release["prerelease"]:
        raise ValueError("Source feed must reference a published stable release")
    if patch_list.get("version") != version:
        raise ValueError("Patch list version does not match the built project")
    names = [patch["name"] for patch in patch_list["patches"]]
    if len(names) != 8 or "Local Stockfish Analysis" not in names:
        raise ValueError("Generated patch list is incomplete")
    with zipfile.ZipFile(bundle) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8")
    manifest_versions = [line.split(":", 1)[1].strip() for line in manifest.splitlines() if line.startswith("Version:")]
    if manifest_versions != [version]:
        raise ValueError("Bundle manifest version does not match the source feed")
    assets = [asset for asset in release["assets"] if asset["name"] == bundle.name]
    if len(assets) != 1:
        raise ValueError("Expected exactly one uploaded matching bundle asset")
    asset = assets[0]
    expected_download_url = f"https://github.com/{repository}/releases/download/{release['tag_name']}/{bundle.name}"
    if asset["browser_download_url"] != expected_download_url:
        raise ValueError("Bundle download URL does not belong to this repository/release")
    if asset["state"] != "uploaded" or asset["size"] != bundle.stat().st_size:
        raise ValueError("Remote bundle upload is incomplete or has a different size")
    with bundle.open("rb") as file:
        expected_digest = "sha256:" + hashlib.file_digest(file, "sha256").hexdigest()
    if asset.get("digest") != expected_digest:
        raise ValueError("Remote bundle digest does not match the checked local artifact")
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    created_at = published.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    return {
        "created_at": created_at,
        "description": f"Patches {version}",
        "download_url": asset["browser_download_url"],
        "signature_download_url": "",
        "version": version,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--patch-list", type=Path, default=Path("patches-list.json"))
    parser.add_argument("--output", type=Path, default=Path("patches-bundle.json"))
    args = parser.parse_args()
    result = build_metadata(
        json.loads(args.release_json.read_text()), args.bundle, args.repository,
        args.version, json.loads(args.patch_list.read_text()),
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Verified source feed: {result['version']} -> {result['download_url']}")


if __name__ == "__main__":
    main()
