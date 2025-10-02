# Domain Availability Checker

This directory contains scripts for checking domain availability using the Domainr API.

## Files

- `checkdomains.sh` - Main script to check domain availability using Domainr API
- `checkdomains_whois.sh` - Alternative script using whois for domain checking
- `domains_videos.txt` - List of video-related domain names to check
- `domains_pictures.txt` - List of picture-related domain names to check
- `.env` - Environment variables (API keys)
- `.env.example` - Example environment file

## Usage

```bash
# Check domains from a file
cat domains_videos.txt | ./checkdomains.sh

# Check domains from stdin
echo "example.com" | ./checkdomains.sh
```

## Setup

1. Copy `.env.example` to `.env`
2. Add your Domainr API key to `.env`
3. Make scripts executable: `chmod +x *.sh`
