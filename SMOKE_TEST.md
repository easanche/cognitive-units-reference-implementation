# Smoke test

The source file is frozen to the paper-version implementation. Do not edit it for the first public release.

## 1. Verify source integrity

Expected SHA-256:

```text
70ceaef97dde911a65fa5d0df23983128747e97680cbf1c85d6e79afd4916cf2  appendix_b_reference_impl.py
```

Linux/macOS:

```bash
sha256sum appendix_b_reference_impl.py
```

Windows PowerShell:

```powershell
Get-FileHash .\appendix_b_reference_impl.py -Algorithm SHA256
```

## 2. Create an isolated environment

```bash
python -m venv .venv
```

Activate the environment and install the dependency:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Execute the reference implementation

```bash
python appendix_b_reference_impl.py
```

Expected result: the process exits with code `0` and no assertion failure.

## Validated preparation environment

During preparation of Revision 1, the exact frozen module completed successfully with:

- Python 3.13.5
- Pydantic 2.13.4

The manuscript target remains Python 3.11+ / Pydantic 2.x.
