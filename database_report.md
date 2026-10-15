# SP Machines - Database Usage Report

Generated from the Django models and `LEGACY_MODELS` in `config/settings/base.py`.

Two databases are used:

- **default (SQLite - app data)**: application-only tables created and migrated by Django.
- **legacy (SQL Server - old VFP database)**: the old VFP tables. Django reads and writes them but does not create them (`managed = False`).

## Master (Items)

| Model | Table | Database | Managed |
|---|---|---|---|
| Item | `item` | legacy (SQL Server - old VFP database) | no |

## Master (Parties)

| Model | Table | Database | Managed |
|---|---|---|---|
| Party | `cust_mst` | legacy (SQL Server - old VFP database) | no |

## Master (Parts)

| Model | Table | Database | Managed |
|---|---|---|---|
| Part | `part-mst` | legacy (SQL Server - old VFP database) | no |

## Master (BOM)

| Model | Table | Database | Managed |
|---|---|---|---|
| BomComponent | `con-mst` | legacy (SQL Server - old VFP database) | no |
| BomSaComponent | `conms` | legacy (SQL Server - old VFP database) | no |

## Master (Supervisors)

| Model | Table | Database | Managed |
|---|---|---|---|
| Supervisor | `sup_mst` | legacy (SQL Server - old VFP database) | no |

## Master (Vendors / Units / Marketing / Reps / GL / GST)

| Model | Table | Database | Managed |
|---|---|---|---|
| Unit | `unit` | legacy (SQL Server - old VFP database) | no |
| MarketingManager | `mm_mst` | legacy (SQL Server - old VFP database) | no |
| Rep | `rep_mst` | legacy (SQL Server - old VFP database) | no |
| Ledger | `gled_mst` | legacy (SQL Server - old VFP database) | no |
| GstRate | `gst` | legacy (SQL Server - old VFP database) | no |

## Purchase Order

| Model | Table | Database | Managed |
|---|---|---|---|
| PurchaseOrderHeader | `pord_mst` | legacy (SQL Server - old VFP database) | no |
| PurchaseOrderItem | `order` | legacy (SQL Server - old VFP database) | no |
| PartRateHistory | `rt_mst` | legacy (SQL Server - old VFP database) | no |
| CreditorOut | `cr_out` | legacy (SQL Server - old VFP database) | no |
| MrnData | `mrn_dat` | legacy (SQL Server - old VFP database) | no |
| ItemMasterTransaction | `imaster` | legacy (SQL Server - old VFP database) | no |
| PurchaseOrderShareLink | `purchase_orders_purchaseordersharelink` | default (SQLite - app data) | yes |
| PendingLetterShareLink | `purchase_orders_pendinglettersharelink` | default (SQLite - app data) | yes |

## MRN

| Model | Table | Database | Managed |
|---|---|---|---|
| InvNo | `inv_no` | legacy (SQL Server - old VFP database) | no |
| MrnData | `mrn_dat` | legacy (SQL Server - old VFP database) | no |
| MrnShareLink | `mrn_mrnsharelink` | default (SQLite - app data) | yes |
| MrnAuditLog | `mrn_mrnauditlog` | default (SQLite - app data) | yes |

## Returnable Challan

| Model | Table | Database | Managed |
|---|---|---|---|
| InvNo | `inv_no` | legacy (SQL Server - old VFP database) | no |
| GchlHeader | `gchl_mst` | legacy (SQL Server - old VFP database) | no |
| GchlLine | `gchl_dat` | legacy (SQL Server - old VFP database) | no |

## Job Card

| Model | Table | Database | Managed |
|---|---|---|---|
| InvNo | `inv_no` | legacy (SQL Server - old VFP database) | no |
| JobCard | `new_job` | legacy (SQL Server - old VFP database) | no |
| JobLine | `imaster` | legacy (SQL Server - old VFP database) | no |
| StockBalance | `stock` | legacy (SQL Server - old VFP database) | no |

## Legacy tables used by more than one module

These are the links between modules: a write from one module is visible to the others.

| Table | Modules that use it |
|---|---|
| `imaster` | Job Card, Purchase Order |
| `inv_no` | Job Card, MRN, Returnable Challan |
| `mrn_dat` | MRN, Purchase Order |

## Relations between modules

- **Purchase Order -> Master:** PO lines use Items, Parties and Parts (`imaster`, `order` tables).
- **MRN -> Purchase Order:** MRN lines are written to `imaster` and update the PO received quantities (`order`).
- **MRN -> Master:** MRN uses Parties, Items and Parts for names, rates and stock.
- **Job Card -> Master:** job cards read Items, BOM (`con-mst`) and Parts; they reduce component stock.
- **Job Card -> MRN/imaster:** job issue and receive lines are written to `imaster` with status S and P.
- **Returnable Challan -> Master:** challans read Parties and Parts; they do not change stock.
- **MRN audit log:** `MrnAuditLog` in the app database records every MRN add, modify, close and delete.
