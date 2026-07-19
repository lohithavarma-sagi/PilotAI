# BL Invoice Generation

In-house invoice generator for the Banking Labs Excel upload flow. Admin users upload the invoice Excel, the app validates master data from SQLite, generates one or more invoice PDFs, and keeps full upload/invoice history.

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

Default login:

```text
username: admin
password: admin123
```

Create a new admin user after first login and stop using the default password.

## Excel Upload Format

Use **Download Template** in the app. The upload sheet must contain these columns:

```text
InvoiceDate, InvoiceMonth, BankingLabsLocation, Customer, ResourceName, Task, Currency, Rate, Hours, InvoiceType, LTO, PONumber
```

Notes:

- `BankingLabsLocation`, `Customer`, and `Task` are resolved from master data.
- `Customer` may be the external customer code, customer name, or the template dropdown value like `2 - Bank of Montreal`.
- `LTO` is optional. If present, it is shown on the invoice PDF.
- Invoices are grouped by invoice date, location, customer, currency, PO number, and LTO.

## Data Storage

By default the app stores runtime data under:

```text
data/
```

This includes:

- `blinvoice.sqlite3`
- uploaded Excel files
- generated PDFs
- `secret.key` for session signing

Override paths with:

```bash
export BLINVOICE_DATA_DIR=/opt/blinvoice/data
export BLINVOICE_DB=/opt/blinvoice/data/blinvoice.sqlite3
```

## EC2 Deployment

Example for Ubuntu on EC2:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv nginx
sudo mkdir -p /opt/blinvoice
sudo chown ubuntu:ubuntu /opt/blinvoice
```

Example for Amazon Linux 2023 on EC2 (`venv` ships inside the base `python3` package, so there is no separate `python3-venv` package to install):

```bash
sudo yum install -y python3 python3-pip nginx
sudo mkdir -p /opt/blinvoice
sudo chown ec2-user:ec2-user /opt/blinvoice
```

Copy this project to `/opt/blinvoice`, then:

```bash
cd /opt/blinvoice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
BLINVOICE_HOST=127.0.0.1 BLINVOICE_PORT=8000 python app.py
```

For a persistent service:

```bash
sudo cp deploy/blinvoice.service /etc/systemd/system/blinvoice.service
sudo systemctl daemon-reload
sudo systemctl enable --now blinvoice
sudo systemctl status blinvoice
```

For public access through a domain or public IP, use Nginx as a reverse proxy.

On Ubuntu (uses the `sites-available`/`sites-enabled` convention):

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/blinvoice
sudo ln -s /etc/nginx/sites-available/blinvoice /etc/nginx/sites-enabled/blinvoice
sudo nginx -t
sudo systemctl reload nginx
```

On Amazon Linux (no `sites-available` directory; config files are auto-included from `conf.d`):

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/blinvoice.conf
sudo nginx -t
sudo systemctl reload nginx
```

Open EC2 security group inbound ports:

- `80` for HTTP
- `443` for HTTPS when TLS is configured
- Do not expose port `8000` publicly; keep it bound to `127.0.0.1`.

## Production Notes

- Put the app behind HTTPS before real invoice data is used.
- Replace the default admin password immediately.
- Back up `/opt/blinvoice/data` regularly. The SQLite DB, uploaded Excel files, and generated PDFs are all stored there.
- If the EC2 username is not `ubuntu`, update `deploy/blinvoice.service`.
- Update `server_name` in `deploy/nginx.conf` to your domain name or public IP.
