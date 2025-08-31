import os, csv, io, json, boto3, datetime, re
import pg8000.native as pg   # pure-Python postgres client (no native wheels)

s3 = boto3.client('s3')
secrets = boto3.client('secretsmanager')
SECRET_ARN = os.environ['DB_SECRET_ARN']

def parse_jdbc_url(url: str):
    # Accepts: jdbc:postgresql://host:port/db?params
    u = url.strip()
    if u.startswith("jdbc:"):
        u = u[5:]
    if u.startswith("postgresql://") or u.startswith("postgres://"):
        u = u.split("://", 1)[1]
    m = re.match(r'([^/?#:]+)(?::(\d+))?/(.+)', u)
    if not m:
        raise ValueError(f"Unsupported JDBC URL format: {url}")
    host = m.group(1)
    port = int(m.group(2) or 5432)
    dbname = m.group(3).split("?", 1)[0]
    return host, port, dbname

def get_conn():
    sec_raw = secrets.get_secret_value(SecretId=SECRET_ARN)['SecretString']
    sec = json.loads(sec_raw) if sec_raw and sec_raw.strip().startswith('{') else {}
    user = sec.get('username') or sec.get('user')
    pwd  = sec.get('password') or sec.get('pass')

    host = sec.get('host')
    port = int(sec.get('port', 5432)) if isinstance(sec.get('port', 5432), (int, str)) else 5432
    db   = sec.get('dbname') or sec.get('database')

    if not host:
        jdbc = sec.get('url') or sec.get('jdbcUrl') or sec.get('jdbc_url')
        if not jdbc:
            raise KeyError("DB secret missing 'host' and 'url'/'jdbcUrl'.")
        host, port, db = parse_jdbc_url(jdbc)

    if not all([user, pwd, host, port, db]):
        raise KeyError("DB secret missing one of required keys: username/password/host/port/dbname (or parseable url).")

    return pg.Connection(user=user, password=pwd, host=host, port=int(port), database=db, timeout=5)

def handler(event, context):
    rec = event['Records'][0]
    bucket = rec['s3']['bucket']['name']
    key = rec['s3']['object']['key']

    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj['Body'].read().decode('utf-8', errors='replace')

    rdr = csv.DictReader(io.StringIO(body))
    rows = []
    names = set()

    for r in rdr:
        name = (r.get('ingredient_name') or '').strip()
        if not name:
            continue
        unit = (r.get('unit') or '').strip().lower()
        retailer = (r.get('retailer') or '').strip() or None
        price = int(r['price_cents'])
        eff = (r.get('effective_date') or datetime.date.today().isoformat())
        names.add(name)
        rows.append((name, unit, retailer, price, eff))

    conn = get_conn()
    try:
        # Map names -> ids
        name_to_id = {}
        for n in names:
            res = conn.run("select id from ingredients where lower(name)=:1 limit 1", n.lower())
            if res:
                name_to_id[n.lower()] = res[0][0]

        upserted = 0
        missing = set()

        for name, unit, retailer, price, eff in rows:
            ing_id = name_to_id.get(name.lower())
            if not ing_id:
                missing.add(name); continue

            # Use the unique index name to avoid expression inference issues
            conn.run("""
                insert into ingredient_prices
                  (ingredient_id, unit, retailer, price_cents, effective_date, source)
                values (:1,:2,:3,:4,:5,'s3-import')
                on conflict on constraint uq_price_key
                do update set price_cents = excluded.price_cents, source = 's3-import'
            """, ing_id, unit, retailer, price, eff)
            upserted += 1

        conn.commit()
        return {"status":"ok","upserted":upserted,"missing":sorted(missing)}
    finally:
        conn.close()
