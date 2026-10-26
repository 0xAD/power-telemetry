#!/usr/bin/env python3
"""
Discover Tuya devices on the local network.

Usage:
    python scripts/scan.py

Prints IP, Device ID (gwId), protocol version for each Tuya device found.
This is read-only. The Local Key is NOT returned by the scan (protocol 3.3+).
"""
import sys
import tinytuya


def main():
    print("Scanning local network for Tuya devices (broadcast)...\n")
    devices = tinytuya.deviceScan(verbose=False)
    if not devices:
        print("No Tuya devices found on this subnet.")
        return
    for ip, info in devices.items():
        print(f"IP:          {ip}")
        print(f"  Device ID: {info.get('id')}")
        print(f"  Protocol:  {info.get('version')}")
        print(f"  Product:   {info.get('productKey')}")
        print(f"  Encrypted: {info.get('encrypt')}")
        print()


if __name__ == "__main__":
    sys.exit(main())
