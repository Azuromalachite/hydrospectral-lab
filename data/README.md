# Local Data Staging & Checksums

Raw datasets, satellite granules, and large binary archives stay outside Git (enforced by [`.gitignore`](../.gitignore) and [`tools/check_repo_hygiene.py`](../tools/check_repo_hygiene.py)). Canonical machine-readable provenance lives in [`manifests/sources/`](../manifests/README.md), while local filesystem locations are configured in gitignored `config/local_paths.yaml` (copied from [`config/local_paths.example.yaml`](../config/local_paths.example.yaml)).

## Reference Datasets Recorded at Handoff

| Source ID | Filename | Upstream Source | License / Terms | Expected SHA-256 |
| --- | --- | --- | --- | --- |
| `src.gloria-2022` | `GLORIA-2022.zip` | Lehmann et al. (2023), [PANGAEA.948492](https://doi.org/10.1594/PANGAEA.948492) | CC BY 4.0 | `f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14` |
| `src.pace-oci-20240730-nrt` | `PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc` | NASA PACE OCI L2 AOP ([HyperCoast release](https://github.com/opengeos/datasets/releases/download/hypercoast/PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc) / [OB.DAAC](https://pace.oceansciences.org/access_pace_data.htm)) | Public domain / NASA Earthdata | `db38c89499f33603de850e1b321e1adbdbcd0609ebc7c532050c8d16d183e98e` |

Set `digest_verified: true` in the corresponding `manifests/sources/*.yaml` file only after recomputing and matching the SHA-256 hash on local storage:

PowerShell:
```powershell
Get-FileHash path\to\GLORIA-2022.zip -Algorithm SHA256
Get-FileHash path\to\PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc -Algorithm SHA256
```

Bash:
```bash
sha256sum path/to/GLORIA-2022.zip path/to/PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc
```
