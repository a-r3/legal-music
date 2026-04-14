# Security Policy

## Legal use only

**legal-music is designed for legal use only.** We do not support:

- Piracy or copyright infringement
- DRM bypass or circumvention
- Unauthorized downloading from protected services (Spotify, Apple Music, YouTube Music, Deezer, Tidal, etc.)
- Stream decryption or credential harvesting
- Any other unauthorized content access

Violations of this policy may be reported to GitHub.

## Reporting security issues

If you discover a security vulnerability in legal-music:

1. **Do not open a public GitHub issue** — this could expose the vulnerability
2. Email the maintainers privately with:
   - Description of the vulnerability
   - Steps to reproduce (if applicable)
   - Potential impact
   - Any suggested fixes

3. Allow reasonable time for a patch before public disclosure

## Security considerations

### Safe by design

- legal-music only uses **read-only** operations on public sources
- No credentials are stored or transmitted
- No account access is attempted
- All network requests are HTTPS
- Downloaded files are not modified or re-encrypted

### Source verification

- Only known, legal music sources are supported
- Each source integration is reviewed for legal compliance
- New sources are vetted before inclusion

## Responsible disclosure

We take security seriously and appreciate responsible disclosure. Please give maintainers time to develop and release patches before public discussion.

---

For more information, see [CONTRIBUTING.md](CONTRIBUTING.md).
