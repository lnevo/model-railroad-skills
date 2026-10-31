---
name: sts-docker
description: Guides running the Shipper-driven Traffic Simulator (STS) in Docker using the sts-docker project, covering compose services and profiles, environment variables, first-time database provisioning, backups and restores from the web app, rolling stock photos, and image upgrades. Use this skill when installing or starting STS in Docker, when editing its docker-compose.yml, when the database is empty or was wiped, when backing up, restoring or moving an STS database, when car photos are missing, or when upgrading the STS image.
---

# STS in Docker

STS is a PHP app on Apache with a MariaDB database. The compose file defines one database service and two alternative web services.

## Services and profiles

| Service | Profile | Source |
|---------|---------|--------|
| `db` | none, always runs | `mariadb:latest` |
| `web` | `build` | built from the local `Dockerfile` |
| `web_prebuilt` | `prebuilt` | `ghcr.io/aaron9589/shipper-driven-traffic-simulator:latest` |

Start exactly one web profile. Put `--profile` before `up`:

```bash
docker compose --profile prebuilt up -d
docker compose --profile build up -d --build
```

- Without a profile, only `db` starts.
- The profile name is `prebuilt`, not `prebuild`.
- Open `http://localhost:8980/sts/`, or whichever host port you mapped. Change the port on the left of `8980:80`.
- Keep the app on a private network. The REST API under `sts/api/` has no authentication.

## Environment

Set these on your web service:

| Variable | Compose default | Meaning |
|----------|-----------------|---------|
| `MYSQL_HOST` | `db` | database service name |
| `MYSQL_USER` | `sts_user` | database user |
| `MYSQL_PASSWORD` | `sts_password` | change this before first start |
| `MYSQL_DATABASE` | `sts_db3` | database name |
| `PROVISION_DATABASE` | `0` | `1` loads the schema at container start |

- Change `MYSQL_PASSWORD` from the public default before first start.
- Keep `MYSQL_USER`, `MYSQL_PASSWORD` and `MYSQL_DATABASE` identical on the web service and on `db`.
- Set the password on every web service you use, because each one has its own environment block.
- Keep `command: --sql_mode=""` on `db`. Strict mode breaks `pu_criteria.php`.
- Leave `MARIADB_RANDOM_ROOT_PASSWORD=yes` alone. The app connects as `MYSQL_USER`, and provisioning does too.

Any variable left unset falls back to the values in `sts/credentials.php`, whose host is `127.0.0.1`. That will not reach the `db` service.

## Provision the database

Do this once, for a new install:

1. Set `PROVISION_DATABASE=1` on your web service. The compose file ships `0`, so a new install starts with no tables until you do.
2. Start the stack.
3. Confirm the app opens at `/sts/`.
4. Set `PROVISION_DATABASE` back to `0`.
5. Run `up -d` again with your profile.

Why step 4 matters:

- `sts/create_sts_db3.sql` begins each table with `DROP TABLE IF EXISTS`, so running it again destroys your data.
- The run-once guard is a marker file, `/opt/sql.initialized`, inside the container. It survives a restart but is gone when the container is recreated.
- A new container with `PROVISION_DATABASE=1` therefore wipes the database. Upgrades recreate the container.

If provisioning fails, `start.sh` prints `MySQL command failed` and Apache starts anyway. The site loads with a bad database, so check the container log.

## Where data lives

Compose uses bind mounts, shown here relative to the compose file:

| Data | Host path | Mounted on |
|------|-----------|------------|
| Database | `../sts-docker-data/database/docker/sts/db` | both profiles, through `db` |
| Backups | `../sts-docker-data/backups` | `web`, `web_prebuilt` |
| Rolling stock photos | `../sts-docker-data/Rolling Stock photos` | `web` only |

- Add the photos volume to `web_prebuilt` yourself. As shipped, its photos live in the container and are lost when it is recreated:

  ```yaml
  - ../sts-docker-data/Rolling Stock photos:/var/www/html/sts/ImageStore/DB_Images/RollingStock/
  ```

- Make the host folders writable by the container's web user. The image gives those folders to `www-data`, but a bind mount brings the host's ownership.
- Expect the mounted backups folder to hide `backups/demo_line`, the sample backup in the image.
- Other generated images, including barcodes, QR codes and uploads under `ImageStore/DB_Images`, are not mounted.

## Back up

Use DB Maint > Create Backup.

- Enter a new name. Names are lowercased, and an existing name is refused.
- The app writes `backups/<name>` to the server, not to your browser. Download a copy from the Restore page.
- It also copies rolling stock photos to `backups/<name>_photos`, if there are any.
- The file is the app's own dump. `Remove Backup` deletes the file and its photos folder.
- Avoid `#` in any text field, such as remarks or names. The restore splits the file on `#`, and the backup does not escape it, so that value breaks the restore. The restore stops with an SQL error partway through, after some tables are already replaced. Test a restore while you can still fix the data.
- NULL values are saved as empty strings, so a restored value can differ from the original.

## Restore

Use DB Maint > Restore Backup. Prefer the listed backups over upload.

- Run Wipe Database first when the backup is from a different railroad, as the Restore page instructs.
- Any successful restore first empties the rolling stock, barcode, QR code and upload image folders. It then copies photos back only from `backups/<name>_photos`.
- A backup with no matching `_photos` folder leaves you with no car photos.
- **Upload & Restore deletes your photos.** The upload is saved as `uploaded_<timestamp>_<file>`, so no photo folder can match it. It also accepts only `.sql` files, and app backups have no extension unless you typed one.
- To restore on another computer, copy both `<name>` and `<name>_photos` into the host backups folder. Then pick the backup from the list.
- Barcodes and QR codes are cleared too. Regenerate them from their report pages.

## Photos

- Add photos in the car editor, and upload JPEG files. Every upload is saved with a `.jpg` name.
- Photos are named by database car ID, not reporting marks: `<id>.jpg` for image 1 and `<id>b.jpg` for image 2.
- Wipe Database also deletes rolling stock photos.

## Upgrade

1. Create a backup and copy it off the host folder.
2. Confirm `PROVISION_DATABASE=0`. This is the step that protects your data.
3. Update the service:

   ```bash
   docker compose --profile prebuilt pull
   docker compose --profile prebuilt up -d
   ```

   For a local build, update your source, then:

   ```bash
   docker compose --profile build up -d --build
   ```

4. Open the app. Schema changes run from `open_db()` on each page load, so there is no separate migration step. Do not rerun `create_sts_db3.sql`.

Know what moves:

- `latest` on the prebuilt image is published only when a release is created. Commits publish branch and SHA tags, so pin one of those if you need a fixed image.
- `mariadb:latest` also moves on `pull`. Pin a version if you do not want the database upgraded at the same time.
- A local build depends on `archive.debian.org`, because the `php:8.0-apache-buster` base is end of life.

Checked against: STS Docker project (fork of github.com/aaron9589/sts-docker), version 0.4.21, commit fa831c49871d12aef918ec64f3b55115bfdb5302. Fork-only session and workflow tooling is excluded.
