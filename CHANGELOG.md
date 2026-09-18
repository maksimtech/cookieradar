# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses calendar versioning (YYYY.MM.N).

## [2026.09.6] - 2026-09-18
### Fixed
- Rich FileProxy ImportError on shutdown: _status() context manager
  flushes sys.stdout, sys.stderr and console.file before spinner stops
