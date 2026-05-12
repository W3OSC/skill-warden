---
name: smart-contract-auditor
description: Analyzes Solidity smart contracts for common security vulnerabilities including reentrancy, integer overflow, and access control issues.
allowed-tools:
  - read_file
  - run_command
version: "1.0.0"
---

# Smart Contract Auditor

This skill helps you analyze Solidity smart contracts for security vulnerabilities.

## Capabilities

- Detects reentrancy vulnerabilities
- Identifies integer overflow/underflow risks
- Reviews access control patterns
- Checks for common DeFi attack vectors

## Usage

Provide a Solidity file path or paste contract code directly.

## References

See [CHECKLIST.md](CHECKLIST.md) for the full audit checklist.
