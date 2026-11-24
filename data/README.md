# Local Data Staging & Fingerprints

Raw datasets, satellite granules, and large binary archives are intentionally excluded from Git via [`.gitignore`](../.gitignore). Stage local inputs under `data/raw/` (created locally on demand).

## Primary Reference Datasets

| Filename | Source | License / Terms | Verified SHA-256 |
|---|---|---|---|
| `GLORIA-2022.zip` | Lehmann et al. (2023), [PANGAEA.948492](https://doi.org/10.1594/PANGAEA.948492) | CC BY 4.0 | `f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14` |
| `PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc` | NASA PACE OCI L2 AOP ([HyperCoast tutorial release](https://github.com/opengeos/datasets/releases/download/hypercoast/PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc) / [NASA OB.DAAC](https://pace.oceansciences.org/access_pace_data.htm)) | Public domain / NASA Earthdata | `db38c89499f33603de850e1b321e1adbdbcd0609ebc7c532050c8d16d183e98e` |

## Expected Local Layout

```text
data/
├── README.md          # Tracked manifest and checksum reference
├── raw/               # Gitignored: unmodified upstream archives and granules
├── interim/           # Gitignored: intermediate filtered/joined tables
└── processed/         # Gitignored: analysis-ready cohorts with saved split IDs
```

## Verification (PowerShell / Bash)

PowerShell:
```powershell
Get-FileHash data\raw\GLORIA-2022.zip -Algorithm SHA256
Get-FileHash data\raw\PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc -Algorithm SHA256
```

Bash:
```bash
sha256sum data/raw/GLORIA-2022.zip data/raw/PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc
```
