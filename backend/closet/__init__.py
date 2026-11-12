"""Closet: a private, single-user wardrobe app."""

try:  # written by the release build; absent when running from source
    from ._build_version import VERSION as __version__
except ImportError:
    __version__ = "0.1.0-dev"

APP_NAME = "Closet"
