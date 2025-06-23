#!/usr/bin/env python
"""
Validation script to verify all required dependencies are installed correctly.
This script can be used in the Dockerfile to validate the environment before starting the application.
"""
import importlib.util
import sys
import os

# List of critical packages that must be installed
CRITICAL_PACKAGES = [
    "pythonjsonlogger",
    "opencensus",
    "opencensus.ext.azure",
    "opencensus.ext.logging",
    "opencensus.ext.fastapi",
    "psutil",
    "fastapi",
    "pydantic",
    "uvicorn"
]

def check_package_installed(package_name):
    """Check if a package is installed and importable"""
    try:
        if '.' in package_name:
            # For packages with dots (submodules), use importlib directly
            parent_pkg, _, _ = package_name.partition('.')
            if importlib.util.find_spec(parent_pkg) is None:
                return False
            return importlib.util.find_spec(package_name) is not None
        else:
            # For top-level packages
            return importlib.util.find_spec(package_name) is not None
    except ImportError:
        return False

def main():
    """Main validation function"""
    print("=== Validating Deployment Environment ===")
    
    all_installed = True
    missing_packages = []
    
    # Check each critical package
    for package in CRITICAL_PACKAGES:
        is_installed = check_package_installed(package)
        status = "INSTALLED" if is_installed else "MISSING"
        print(f"Checking {package}: {status}")
        
        if not is_installed:
            all_installed = False
            missing_packages.append(package)
    
    # Print overall validation status
    print("\n=== Validation Results ===")
    if all_installed:
        print("✅ All critical packages are installed.")
    else:
        print(f"❌ Missing {len(missing_packages)} critical packages:")
        for pkg in missing_packages:
            print(f"   - {pkg}")
        print("\nContainer environment validation failed.")
        sys.exit(1)
    
    print("\n=== Environment Info ===")
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    
    # Print available environment variables related to Azure
    print("\n=== Azure Environment Variables ===")
    azure_vars = [var for var in os.environ if any(keyword in var.upper() for keyword in 
                                               ['AZURE', 'WEBSITE', 'CONTAINER'])]
    for var in sorted(azure_vars):
        value = os.environ[var]
        # Redact sensitive values
        if any(keyword in var.upper() for keyword in ['KEY', 'SECRET', 'PASSWORD', 'CONN']):
            value = "****REDACTED****"
        print(f"{var}={value}")

    print("\n=== Validation Complete ===")

if __name__ == "__main__":
    main()
